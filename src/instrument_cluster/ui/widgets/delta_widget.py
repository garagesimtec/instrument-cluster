import math
from array import array
from typing import Optional, Tuple

import numpy as np
import pygame
from pygame.sprite import DirtySprite
from scipy.spatial import cKDTree as KDTree

from ...logger import Logger
from ...telemetry.feed import Feed
from ...telemetry.models import TelemetryFrame
from ..colors import Color
from ..utils import FontFamily, load_font


class DeltaWidget(DirtySprite):
    """
    Bordered panel with a header text and a centered dynamic value underneath.
    Redraws only when the dynamic value changes.
    """

    def __init__(
        self,
        rect: tuple[int, int, int, int],
        feed: Feed,
        *,
        anchor: str = "center",  # "topleft" or "center"
        header_text: str = "Time   Delta",
        bg_color: tuple[int, int, int] = Color.BLACK.rgb(),
        text_color: tuple[int, int, int] = Color.WHITE.rgb(),
        border_color: tuple[int, int, int] = Color.LIGHT_GREY.rgb(),
        border_width: int = 2,
        border_radius: int = 4,
        show_border: bool = True,
        header_margin: int = 8,  # brings `header_text` down by x pixels
        antialias: bool = True,
        kd_leafsize: int = 16,
    ):
        super().__init__()

        self.logger = Logger(__class__.__name__).get()
        self.feed = feed

        px, py, self.w, self.h = rect

        # place widget based on anchor
        if anchor == "center":
            tlx = px - self.w // 2
            tly = py - self.h // 2
        elif anchor == "topleft":
            tlx = px
            tly = py
        else:
            raise ValueError(f"Unsupported anchor: {anchor}")

        self.font_header = load_font(size=32, family=FontFamily.PIXEL_TYPE)
        self.font_value = load_font(size=64, family=FontFamily.D_DIN_EXP)
        self.header_text = header_text
        self.value_offset_y = 4
        self.bg_color = bg_color
        self.text_color = text_color
        self.border_color = border_color
        self.border_width = border_width
        self.border_radius = border_radius
        self.show_border = show_border
        self.header_margin = header_margin
        self.antialias = antialias

        self.digit_gap = -2

        self.image = pygame.Surface((self.w, self.h), pygame.SRCALPHA).convert_alpha()
        self.rect = self.image.get_rect(topleft=(tlx, tly))

        self._last_value_str = None

        self._render_border_and_header()
        self.set_delta()
        self.visible = 1
        self.dirty = 2

        self._lap_index = -1

        # timing
        self._lap_time_s: float = 0.0
        self._best_time_s: float = float("inf")

        # kd-tree
        self._kdtree = None
        self._kd_leafsize = int(kd_leafsize)
        self._min_dist_m = 5.0  # 1–5 m
        self._min_dist_sq = self._min_dist_m * self._min_dist_m

        self._xs = array("f")
        self._zs = array("f")
        self._times = array("f")
        self._last_vx = None
        self._last_vz = None

        self._best_pts_np = None
        self._best_times_np = None

        self.max_nn_radius = 15

        # update delta every x seconds
        self._delta_timer = 0.0
        self._last_delta_value = None
        self.delta_update_period = 0.15  # seconds
        self._last_ref_idx = None
        # max allowed index jump along the reference
        self._max_ref_jump = 30

    @property
    def lap_index(self):
        return self._lap_index

    @lap_index.setter
    def lap_index(self, value):
        if value != self._lap_index:
            self._lap_index = value
            self._lap_time_s = 0.0
            self._xs.clear()
            self._zs.clear()
            self._times.clear()
            self._last_vx = None
            self._last_vz = None

            if hasattr(self, "_ema_ref_time"):
                delattr(self, "_ema_ref_time")

    def _get_digit_metrics(self, color: tuple[int, int, int]):
        # cache of digit atlases keyed by (font_id, antialias, color_rgb)
        if not hasattr(self, "_digit_cache"):
            self._digit_cache = {}
        key = (id(self.font_value), bool(self.antialias), color)
        cached = self._digit_cache.get(key)
        if cached is not None:
            return cached

        chars = ".:0123456789"
        surf = {ch: self.font_value.render(ch, self.antialias, color) for ch in chars}
        h = max(s.get_height() for s in surf.values())
        advance = max(s.get_width() for s in surf.values())

        punct_scale = 0.6  # narrower slot for '.' and ':'
        adv = {}
        for ch in chars:
            if ch in ".:":
                slot = int(max(surf[ch].get_width(), advance * punct_scale))
            else:
                slot = advance
            adv[ch] = slot

        packed = {"surf": surf, "h": h, "advance": advance, "adv": adv}
        self._digit_cache[key] = packed
        return packed

    def _render_border_and_header(self):
        self.image.fill(self.bg_color)

        if self.show_border:
            pygame.draw.rect(
                self.image,
                self.border_color,
                self.image.get_rect(),
                self.border_width,
                self.border_radius,
            )

        # header centered at top
        header_surf = self.font_header.render(
            self.header_text, self.antialias, self.text_color
        )
        header_rect = header_surf.get_rect(midtop=(self.w // 2, self.header_margin))
        self.image.blit(header_surf, header_rect)

        self._header_bottom = header_rect.bottom

    def _render_value(self, value_str: str, color: tuple[int, int, int]):
        metrics = self._get_digit_metrics(color)
        surf_map = metrics["surf"]
        digit_h = metrics["h"]
        advance_map = metrics["adv"]

        # area
        inner_left = self.border_width
        inner_right = self.w - self.border_width
        inner_top = max(self._header_bottom + self.header_margin, self.border_width)
        inner_bottom = self.h - self.border_width
        area = pygame.Rect(
            inner_left, inner_top, inner_right - inner_left, inner_bottom - inner_top
        )

        pygame.draw.rect(self.image, self.bg_color, area)

        # total width from per-char advances
        advances = [advance_map.get(ch, metrics["advance"]) for ch in value_str]
        total_w = sum(advances) + max(0, len(value_str) - 1) * self.digit_gap

        x = area.centerx - total_w // 2
        y = area.centery - self.value_offset_y - digit_h // 2

        for i, ch in enumerate(value_str):
            slot_w = advances[i]
            ch_surf = surf_map.get(ch)
            if ch_surf is None:
                ch_surf = self.font_value.render(ch, self.antialias, color)
            gx = x + (slot_w - ch_surf.get_width()) // 2
            gy = y + (digit_h - ch_surf.get_height()) // 2
            self.image.blit(ch_surf, (gx, gy))
            x += slot_w + self.digit_gap

    def set_delta(self, value: Optional[float] = None):
        value_str, color = self._format_delta(value)

        if value_str != self._last_value_str:
            self._last_value_str = value_str
            self._render_value(value_str, color)
            self.dirty = 1

    def _format_delta(self, value: Optional[float]):
        if value is None or not math.isfinite(value):
            return "", self.text_color

        color = Color.GREEN.rgb() if value < 0.0 else Color.LIGHT_RED.rgb()
        txt = f"{abs(value):05.2f}"  # zero-padded seconds with two decimal
        return txt, color

    def update(self, packet: TelemetryFrame | None, dt: float):
        dt = float(dt or 0.0)
        flags = getattr(packet, "flags", None)
        paused = bool(getattr(flags, "paused", False))
        loading = bool(getattr(flags, "loading_or_processing", False))
        lap_count = int(getattr(packet, "lap_count", 0) or 0)
        pos = getattr(packet, "position", None)

        if lap_count in (0, None):
            if self.lap_index != -1:
                self.reset()
            return

        if lap_count != self.lap_index:
            if self.lap_index > 0 and len(self._xs) > 0:
                prev_time = self._lap_time_s
                # always build "last lap" reference and optionally track best
                self._build_reference_from_current()
                self._best_time_s = min(self._best_time_s, prev_time)

            # new lap
            self.lap_index = lap_count

        running = (not paused) and (not loading) and (self.lap_index > 0)

        if running:
            self._lap_time_s += dt

            if pos is not None:
                vx, vz = float(pos.x), float(pos.z)
                if self._last_vx is None:
                    self._last_vx, self._last_vz = vx, vz
                    self._xs.append(vx)
                    self._zs.append(vz)
                    self._times.append(self._lap_time_s)
                else:
                    dx = vx - self._last_vx
                    dz = vz - self._last_vz
                    if (dx * dx + dz * dz) >= self._min_dist_sq:
                        self._last_vx, self._last_vz = vx, vz
                        self._xs.append(vx)
                        self._zs.append(vz)
                        self._times.append(self._lap_time_s)

        if self._has_lap_reference() and self.lap_index >= 2:
            delta = self._current_vs_reference((pos.x, pos.z))
            if delta is not None:
                self._delta_timer += dt
                if (
                    self._last_delta_value is None
                    or self._delta_timer >= self.delta_update_period
                ):
                    self._last_delta_value = delta
                    self._delta_timer = 0.0
                    self.feed.delta_s = delta
                    self.feed.has_delta = True
                    self.set_delta(delta)
        else:
            self.set_delta()
            self._delta_timer = 0.0
            self._last_delta_value = None

    def _current_vs_reference(self, qpos: Tuple[float, float]) -> Optional[float]:
        """Delta of current lap time - reference time at nearby reference positions.

        Strategy:
        =========

        - Prefer neighbors within a fixed radius.
        - Use median of up to 5 closest.
        - EMA for frame-to-frame smoothness.
        - If no trustworthy neighbors in frame, fall back to last trustworthy time.
        """
        if (
            self._kdtree is None
            or self._best_times_np is None
            or self._best_times_np.size == 0
        ):
            return None

        # find a few nearby candidates
        dist, idxs = self._kdtree.query(
            qpos, k=5, distance_upper_bound=self.max_nn_radius
        )
        idxs = np.atleast_1d(idxs)
        idxs = idxs[np.isfinite(dist)] if np.ndim(dist) else [idxs]

        if len(idxs) == 0:
            return None

        # enforce continuity: choose the nearest index close to last_ref_idx
        if self._last_ref_idx is not None:
            diffs = np.abs(idxs - self._last_ref_idx)
            idx = (
                int(idxs[np.argmin(diffs)])
                if np.min(diffs) <= self._max_ref_jump
                else int(idxs[0])
            )
        else:
            idx = int(idxs[0])

        self._last_ref_idx = idx
        ref_time = float(self._best_times_np[idx])
        return float(self._lap_time_s - ref_time)

    def _build_reference_from_current(self) -> None:
        n = len(self._xs)
        if n == 0:
            return

        xs = np.frombuffer(self._xs, dtype=np.float32, count=n).copy()
        zs = np.frombuffer(self._zs, dtype=np.float32, count=n).copy()
        ts = np.frombuffer(self._times, dtype=np.float32, count=n).copy()

        self._best_pts_np = np.column_stack((xs, zs))  # (N, 2)
        self._best_times_np = ts

        self._kdtree = KDTree(self._best_pts_np, leafsize=self._kd_leafsize)

    def _has_lap_reference(self) -> bool:
        return (
            self._kdtree is not None
            and self._best_times_np is not None
            and self._best_times_np.size > 0
        )

    def reset(self) -> None:
        self.logger.info("reset()")
        self.set_delta()
        self.lap_index = -1

        # reset relevant variables
        self._lap_time_s = 0.0
        self._xs.clear()
        self._zs.clear()
        self._times.clear()
        self._last_vx = None
        self._last_vz = None
        self._best_time_s = float("inf")
        self._best_pts_np = None
        self._best_times_np = None
        self._kdtree = None
