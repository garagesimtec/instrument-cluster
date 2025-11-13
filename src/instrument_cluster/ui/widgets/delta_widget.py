import math
from typing import Optional, Tuple

import numpy as np
import pygame
from pygame.sprite import DirtySprite

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
        # store kd leafsize for later

        self._kd_leafsize = int(kd_leafsize)

        # per-lap capture buffers
        self._xs: list[float] = []
        self._zs: list[float] = []
        self._times: list[float] = []

        # last recorded world pos (for step gating)
        self._last_vx: Optional[float] = None
        self._last_vz: Optional[float] = None

        # step gates: avoid oversampling & teleports
        self._min_step_m = 5.0
        self._min_step_sq = self._min_step_m * self._min_step_m
        self._max_step_m = 60.0
        self._max_step_sq = self._max_step_m * self._max_step_m

        # reference & projection state (filled by _build_reference_from_current)
        self._ref_s = None
        self._ref_t = None
        self._tref_spline = None
        self._seg_mid_kdtree = None
        self._lap_len_m = 0.0

        # continuity for s
        self._last_s: Optional[float] = None

        # easing state
        self._disp_delta = None
        self._anim_start = None
        self._anim_target = None
        self._anim_t = 0.0
        self.delta_anim_duration = 0.3
        self.delta_change_eps = 0.02

    @property
    def lap_index(self):
        return self._lap_index

    @lap_index.setter
    def lap_index(self, value):
        if value != self._lap_index:
            self._lap_index = value
            # reset per-lap capture only (do NOT clear the built reference here)
            self._lap_time_s = 0.0
            self._xs.clear()
            self._zs.clear()
            self._times.clear()
            self._last_vx = None
            self._last_vz = None
            self._last_s = None
            # leave _ref_s/_tref_spline/_seg_mid_kdtree intact

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
            if self.lap_index > 0:
                self._build_reference_from_current()
                self.logger.info(
                    "Built ref: pts=%d, lap_len=%.1f m, spline=%s, segs=%d",
                    self._ref_s.size,
                    self._lap_len_m,
                    type(self._tref_spline).__name__,
                    int(getattr(self, "_seg_px", np.array([])).size),
                )

            # new lap
            self.lap_index = lap_count

        running = (not paused) and (not loading) and (self.lap_index > 0)

        if running:
            self._lap_time_s += dt

            if pos is not None:
                vx, vz = float(pos.x), float(pos.z)
                if self._last_vx is None:
                    # first sample of the lap
                    self._last_vx, self._last_vz = vx, vz
                    self._xs.append(vx)
                    self._zs.append(vz)
                    self._times.append(self._lap_time_s)
                else:
                    dx = vx - self._last_vx
                    dz = vz - self._last_vz
                    d2 = dx * dx + dz * dz
                    # only keep sufficiently spaced points, but reject teleports
                    if self._min_step_sq <= d2 <= self._max_step_sq:
                        self._last_vx, self._last_vz = vx, vz
                        self._xs.append(vx)
                        self._zs.append(vz)
                        self._times.append(self._lap_time_s)

        if self._has_lap_reference() and self.lap_index >= 2 and pos is not None:
            raw_delta = self._current_vs_reference((pos.x, pos.z))
            if raw_delta is not None:
                # start a new animation if target moved meaningfully
                if self._disp_delta is None:
                    self._disp_delta = float(raw_delta)
                    self._anim_target = float(raw_delta)
                    self._anim_start = float(raw_delta)
                    self._anim_t = 0.0
                elif (
                    abs(raw_delta - (self._anim_target or raw_delta))
                    > self.delta_change_eps
                ):
                    self._anim_start = float(self._disp_delta)
                    self._anim_target = float(raw_delta)
                    self._anim_t = 0.0

                # advance easing
                self._anim_t = min(
                    1.0, self._anim_t + (dt / max(1e-3, self.delta_anim_duration))
                )
                # cosine ease-in-out
                s = 0.5 - 0.5 * math.cos(math.pi * self._anim_t)
                self._disp_delta = self._anim_start + s * (
                    self._anim_target - self._anim_start
                )

                # show smoothed value
                self.feed.delta_s = self._disp_delta
                self.feed.has_delta = True
                self.set_delta(self._disp_delta)
        else:
            # clear state on losing reference/new session
            self.set_delta()
            self._disp_delta = None
            self._anim_start = None
            self._anim_target = None
            self._anim_t = 0.0

    def _project_to_s(self, qx: float, qz: float) -> Optional[tuple[float, float, int]]:
        """
        Project (qx,qz) onto the nearest reference path segment.
        Returns (s_along_path_m, lateral_distance_m, segment_index).
        """
        kdt = getattr(self, "_seg_mid_kdtree", None)
        if kdt is None:
            return None

        # nearest midpoint + its immediate neighbors
        dist, idx = kdt.query((qx, qz), k=1)
        i = int(idx)

        seg_px = getattr(self, "_seg_px", None)
        if seg_px is None or seg_px.size == 0:
            return None

        cand = [i]
        if i > 0:
            cand.append(i - 1)
        if i + 1 < seg_px.shape[0]:
            cand.append(i + 1)

        seg_px = self._seg_px
        seg_pz = self._seg_pz
        seg_dx = self._seg_dx
        seg_dz = self._seg_dz
        seg_L = self._seg_L
        seg_s0 = self._seg_s0

        qx = float(qx)
        qz = float(qz)
        best_s, best_d2, best_idx = None, float("inf"), None

        for j in cand:
            L = float(seg_L[j])
            if L <= 1e-6:
                continue

            px, pz = float(seg_px[j]), float(seg_pz[j])
            dx, dz = float(seg_dx[j]), float(seg_dz[j])

            vx, vz = qx - px, qz - pz
            t = (vx * dx + vz * dz) / (L * L)
            if t < 0.0:
                t = 0.0
            elif t > 1.0:
                t = 1.0

            fx, fz = px + t * dx, pz + t * dz
            d2 = (qx - fx) * (qx - fx) + (qz - fz) * (qz - fz)

            if d2 < best_d2:
                best_d2 = d2
                best_s = float(seg_s0[j] + t * L)
                best_idx = j

        if best_s is None:
            return None
        return best_s, math.sqrt(best_d2), int(best_idx)

    def _build_reference_from_current(self) -> None:
        """
        Build distance-indexed reference from the just-finished lap:
        - compute cumulative distance s
        - build monotone t_ref(s) with PCHIP
        - precompute segment data + KDTree(midpoints) for fast projection
        """
        xs = np.asarray(getattr(self, "_xs", []), dtype=np.float32)
        zs = np.asarray(getattr(self, "_zs", []), dtype=np.float32)
        ts = np.asarray(getattr(self, "_times", []), dtype=np.float32)

        if xs.size < 2:
            return

        # segment lengths and cumulative distance
        dx = np.diff(xs)
        dz = np.diff(zs)
        seg_len = np.hypot(dx, dz)
        s = np.concatenate(([0.0], np.cumsum(seg_len))).astype(np.float32)

        # drop zero-length segments to keep s strictly increasing
        keep = np.concatenate(([True], seg_len > 1e-3))
        xs, zs, ts, s = xs[keep], zs[keep], ts[keep], s[keep]

        if s.size < 2:
            return

        # store reference arrays
        self._ref_s = s
        self._ref_t = ts
        self._lap_len_m = float(s[-1])

        # monotone time vs distance (no overshoot)
        from scipy.interpolate import PchipInterpolator

        self._tref_spline = PchipInterpolator(
            self._ref_s, self._ref_t, extrapolate=True
        )

        # precompute segment geometry and KDTree of midpoints
        px = xs[:-1]
        pz = zs[:-1]
        vx = np.diff(xs)
        vz = np.diff(zs)
        L = np.hypot(vx, vz)
        valid = L > 1e-6

        self._seg_px = px[valid]
        self._seg_pz = pz[valid]
        self._seg_dx = vx[valid]
        self._seg_dz = vz[valid]
        self._seg_L = L[valid]
        self._seg_s0 = self._ref_s[:-1][valid]

        mids = np.column_stack(
            (self._seg_px + 0.5 * self._seg_dx, self._seg_pz + 0.5 * self._seg_dz)
        )

        from scipy.spatial import cKDTree as KDTree

        leaf = int(getattr(self, "_kd_leafsize", 16))
        self._seg_mid_kdtree = KDTree(mids, leafsize=leaf)

        # (optional) handy for plotting/debug
        self._best_pts_np = np.column_stack((xs, zs))

    def _current_vs_reference(self, qpos: Tuple[float, float]) -> Optional[float]:
        """
        Delta = current lap time - reference time at same distance s along the lap.
        Handles first lock-on at lap start, then applies lateral and continuity gates.
        """
        # reference ready?
        if not self._has_lap_reference():
            return None

        proj = self._project_to_s(float(qpos[0]), float(qpos[1]))
        if proj is None:
            return None
        s_raw, d_perp, seg_idx = proj

        lap_len = float(getattr(self, "_lap_len_m", self._ref_s[-1]))
        s_raw = max(0.0, min(s_raw, lap_len))

        # continuity state (with safe defaults)
        last_s = getattr(self, "_last_s", None)
        max_lat = float(getattr(self, "max_lateral_m", 12.0))
        max_fwd = float(getattr(self, "max_s_jump_m", 30.0))
        max_back = float(getattr(self, "max_backtrack_m", 5.0))

        # first lock of the lap: accept projection, resolve SF ambiguity
        if last_s is None:
            s = s_raw
            if self._lap_time_s <= 2.0 and s > 0.75 * lap_len:
                s = 0.0
            self._last_s = s
            self._last_seg_idx = seg_idx
            t_ref = float(self._tref_spline(self._last_s))
            return float(self._lap_time_s - t_ref)

        # normal frames: lateral gate → continuity clamps
        if d_perp > max_lat:
            s = last_s  # freeze
        else:
            s = s_raw

        ds = s - last_s
        if ds > max_fwd:
            s = last_s + max_fwd
        elif ds < -max_back:
            s = last_s - max_back

        # commit and compute delta
        self._last_s = s
        self._last_seg_idx = seg_idx
        t_ref = float(self._tref_spline(self._last_s))
        return float(self._lap_time_s - t_ref)

    def _has_lap_reference(self) -> bool:
        """
        Reference exists if we have:
        - distance/time arrays (size >= 2)
        - a time-vs-distance interpolator
        - a KDTree of segment midpoints for projection
        """
        ref_s = getattr(self, "_ref_s", None)
        ref_t = getattr(self, "_ref_t", None)
        spline = getattr(self, "_tref_spline", None)
        kdt = getattr(self, "_seg_mid_kdtree", None)
        return (
            ref_s is not None
            and ref_t is not None
            and isinstance(ref_s, np.ndarray)
            and isinstance(ref_t, np.ndarray)
            and ref_s.size >= 2
            and ref_t.size >= 2
            and spline is not None
            and kdt is not None
        )

    def reset(self) -> None:
        self.logger.info("reset()")
        self.set_delta()
        self.lap_index = -1
