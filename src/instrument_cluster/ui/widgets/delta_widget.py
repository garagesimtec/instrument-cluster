import math
import os
import time
from array import array
from typing import Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pygame
from pygame.sprite import DirtySprite
from scipy.interpolate import PchipInterpolator
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

        # delta easing
        self._disp_delta = None
        self._anim_start = None
        self._anim_target = None
        self._anim_t = 0.0
        self.delta_anim_duration = 0.4  # seconds (0.5–1.0 works well)
        self.delta_change_eps = 0.02  # s; ignore tiny target changes

        self._last_s = None
        self._last_seg_idx = None
        self.max_lateral_m = 12.0  # reject updates when car is too far from path
        self.max_s_jump_m = 30.0  # cap how far s can jump in one frame
        self.max_backtrack_m = 5.0  # allow tiny backtrack, clamp bigger ones

        # prevent "teleport"
        self._max_dist_m = 60.0  # tune: 40–80 m
        self._max_dist_sq = self._max_dist_m * self._max_dist_m

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

        for attr in (
            "_tref_spline",
            "_seg_mid_kdtree",
            "_ref_s",
            "_ref_t",
            "_lap_len_m",
        ):
            if hasattr(self, attr):
                setattr(self, attr, None)

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

                # plot reference lap for debugging
                # self.save_reference_plots()

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
                    d2 = dx * dx + dz * dz
                    if d2 >= self._min_dist_sq and d2 <= self._max_dist_sq:
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

    def _project_to_s(self, qx: float, qz: float) -> Optional[float]:
        """
        Project (qx,qz) onto nearest path segment; return curvilinear s (meters).
        """
        if getattr(self, "_seg_mid_kdtree", None) is None:
            return None

        # pick nearest segment by midpoint
        dist, idx = self._seg_mid_kdtree.query((qx, qz), k=1)
        i = int(idx)

        # check neighbors i-1 and i+1 for safety
        cand = [i]
        if i > 0:
            cand.append(i - 1)
        if i + 1 < self._seg_px.shape[0]:
            cand.append(i + 1)

        qx = float(qx)
        qz = float(qz)
        best_s = None
        best_d2 = float("inf")

        for j in cand:
            px = self._seg_px[j]
            pz = self._seg_pz[j]
            dx = self._seg_dx[j]
            dz = self._seg_dz[j]
            L = self._seg_L[j]
            if L <= 1e-6:
                continue

            # project onto segment, clamp t to [0,1]
            vx = qx - px
            vz = qz - pz
            t = (vx * dx + vz * dz) / (L * L)
            t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)

            # foot point & distance
            fx = px + t * dx
            fz = pz + t * dz
            d2 = (qx - fx) * (qx - fx) + (qz - fz) * (qz - fz)

            if d2 < best_d2:
                best_d2 = d2
                best_s = float(self._seg_s0[j] + t * L)

        best_s, best_d2, best_idx = None, float("inf"), None
        for j in cand:
            # ... project onto segment ...
            if d2 < best_d2:
                best_d2 = d2
                best_s = float(self._seg_s0[j] + t * L)
                best_idx = j
        if best_s is None:
            return None
        return best_s, math.sqrt(best_d2), best_idx

    def _build_reference_from_current(self) -> None:
        n = len(self._xs)
        if n < 2:
            return

        # 2D path as numpy
        xs = np.frombuffer(self._xs, dtype=np.float32, count=n).copy()
        zs = np.frombuffer(self._zs, dtype=np.float32, count=n).copy()
        ts = np.frombuffer(self._times, dtype=np.float32, count=n).copy()

        # cumulative distance s along the lap (meters)
        dx = np.diff(xs)
        dz = np.diff(zs)
        seg_len = np.hypot(dx, dz)
        s = np.concatenate(([0.0], np.cumsum(seg_len)))

        # Drop zero-length segments to keep s strictly increasing
        keep = np.concatenate(([True], seg_len > 1e-3))
        xs, zs, ts, s = xs[keep], zs[keep], ts[keep], s[keep]

        # Store reference lookups
        self._ref_s = s.astype(np.float32)  # shape (M,)
        self._ref_t = ts.astype(np.float32)  # shape (M,)
        self._lap_len_m = float(self._ref_s[-1])  # total lap length (meters)

        #
        # for monotone behavior use
        #
        # from scipy.interpolate import PchipInterpolator
        #
        # and
        #
        # PchipInterpolator(self._ref_s, self._ref_t, extrapolate=True)
        #

        # self._tref_spline = CubicSpline(
        #     self._ref_s, self._ref_t, bc_type="natural", extrapolate=True
        # )

        self._tref_spline = PchipInterpolator(
            self._ref_s, self._ref_t, extrapolate=True
        )

        # Precompute segment data + KDTree of segment midpoints
        px = xs[:-1]
        pz = zs[:-1]  # segment start points
        dx = np.diff(xs)
        dz = np.diff(zs)  # segment vectors
        L = np.hypot(dx, dz)
        valid = L > 1e-6
        self._seg_px = px[valid]
        self._seg_pz = pz[valid]
        self._seg_dx = dx[valid]
        self._seg_dz = dz[valid]
        self._seg_L = L[valid]
        self._seg_s0 = self._ref_s[:-1][valid]  # s at segment start
        mids = np.column_stack(
            (self._seg_px + 0.5 * self._seg_dx, self._seg_pz + 0.5 * self._seg_dz)
        )
        self._seg_mid_kdtree = KDTree(mids, leafsize=self._kd_leafsize)

        # Keep original (x,z,t) too if you want, but KDTree on points is no longer required
        self._best_pts_np = np.column_stack((xs, zs))
        self._best_times_np = ts

    def _current_vs_reference(self, qpos: Tuple[float, float]) -> Optional[float]:
        if not hasattr(self, "_ref_s") or self._ref_s is None or self._ref_s.size < 2:
            return None

        proj = self._project_to_s(qpos[0], qpos[1])
        if proj is None:
            return None
        s_raw, d_perp, seg_idx = proj

        # 1) reject clearly off-track projections for this frame
        if d_perp > self.max_lateral_m:
            # keep last s (freeze), if we have one; else drop the update
            if self._last_s is None:
                return None
            s = self._last_s
        else:
            s = s_raw

        # 2) clamp s to lap domain
        lap_len = getattr(self, "_lap_len_m", float(self._ref_s[-1]))
        s = min(max(0.0, s), lap_len)

        # 3) continuity clamps vs last s
        if self._last_s is not None:
            ds = s - self._last_s
            # cap forward/backward jump size
            if ds > self.max_s_jump_m:
                s = self._last_s + self.max_s_jump_m
            elif ds < -self.max_backtrack_m:
                s = self._last_s - self.max_backtrack_m

        # commit state
        self._last_s = s
        self._last_seg_idx = seg_idx

        # 4) get reference time and compute delta
        t_ref = float(self._tref_spline(s))  # or np.interp(...)
        return float(self._lap_time_s - t_ref)

    def _has_lap_reference(self) -> bool:
        return (
            getattr(self, "_ref_s", None) is not None
            and getattr(self, "_ref_t", None) is not None
            and self._ref_s.size >= 2
            and getattr(self, "_tref_spline", None) is not None
            and getattr(self, "_seg_mid_kdtree", None) is not None
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
        for attr in (
            "_tref_spline",
            "_seg_mid_kdtree",
            "_ref_s",
            "_ref_t",
            "_lap_len_m",
        ):
            if hasattr(self, attr):
                setattr(self, attr, None)

    def save_reference_plots(
        self,
        save_dir: str = ".",
        also_plot_time_vs_distance: bool = True,
    ) -> dict:
        """
        Save reference plots as PNGs.
        Returns dict with file paths. Requires a built reference.
        """

        if getattr(self, "_best_pts_np", None) is None or self._best_pts_np.size == 0:
            raise RuntimeError("No reference path available. Build it first.")

        # Gather metadata
        lap_idx = int(getattr(self, "_lap_index", -1))
        n_pts = int(self._best_pts_np.shape[0])
        lap_len_m = float(getattr(self, "_lap_len_m", 0.0) or 0.0)
        ref_time_s = float(getattr(self, "_best_time_s", float("nan")))
        ts = time.strftime("%Y%m%d-%H%M%S")

        base = (
            f"ref_lap{lap_idx}_len{int(round(lap_len_m))}m_"
            f"pts{n_pts}_t{ref_time_s:.3f}s_{ts}"
        )

        os.makedirs(save_dir, exist_ok=True)
        paths = {}

        # --- Plot XY path ---
        xs = self._best_pts_np[:, 0]
        zs = self._best_pts_np[:, 1]

        fig, ax = plt.subplots(dpi=150)
        ax.plot(xs, zs)
        ax.scatter([xs[0]], [zs[0]])  # start/finish marker
        ax.set_aspect("equal")
        ax.set_xlabel("x [m]")
        ax.set_ylabel("z [m]")
        ax.set_title("Reference Path (x vs z)")

        out_xy = os.path.join(save_dir, f"{base}_path.png")
        fig.savefig(out_xy, bbox_inches="tight")
        plt.close(fig)
        paths["path_png"] = out_xy

        # --- Optional: t(s) ---
        if also_plot_time_vs_distance:
            if (
                getattr(self, "_ref_s", None) is None
                or getattr(self, "_ref_t", None) is None
            ):
                raise RuntimeError(
                    "No reference time/distance arrays. Build reference first."
                )

            fig2, ax2 = plt.subplots(dpi=150)
            ax2.plot(self._ref_s, self._ref_t)
            ax2.set_xlabel("distance s [m]")
            ax2.set_ylabel("reference time t [s]")
            ax2.set_title("Reference Time vs Distance")

            out_ts = os.path.join(save_dir, f"{base}_t_vs_s.png")
            fig2.savefig(out_ts, bbox_inches="tight")
            plt.close(fig2)
            paths["t_vs_s_png"] = out_ts

        return paths
