from typing import Optional

import pygame
from pygame.sprite import DirtySprite

from ...telemetry.feed import Feed
from ...telemetry.models import TelemetryFrame
from ..colors import Color
from ..utils import FontFamily, load_font


class PredictedLapWidget(DirtySprite):
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
        header_text: str = "Predicted   Lap",
        bg_color: tuple[int, int, int] = Color.BLACK.rgb(),
        text_color: tuple[int, int, int] = Color.WHITE.rgb(),
        border_color: tuple[int, int, int] = Color.LIGHT_GREY.rgb(),
        border_width: int = 2,
        border_radius: int = 4,
        show_border: bool = True,
        header_margin: int = 8,  # brings `header_text` down by x pixels
        antialias: bool = True,
    ):
        super().__init__()

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
        self._digit_key = None  # tracks cache validity

        self.image = pygame.Surface((self.w, self.h), pygame.SRCALPHA).convert_alpha()
        self.rect = self.image.get_rect(topleft=(tlx, tly))

        self._last_time_str = None
        self._render_border_and_header()  # border and header are static
        self.set_lap(0.0)  # initial placeholder
        self.visible = 1
        self.dirty = 2

    def _ensure_digit_cache(self):
        key = (id(self.font_value), self.text_color, self.antialias)
        if key == self._digit_key:
            return

        chars = ".:0123456789"
        self._digit_surf = {
            ch: self.font_value.render(ch, self.antialias, self.text_color)
            for ch in chars
        }
        self._digit_h = max(s.get_height() for s in self._digit_surf.values())
        self._advance = max(s.get_width() for s in self._digit_surf.values())

        # here we need a per-char slot width
        # digits will have full slot but punctuation a narrower
        punct_scale = 0.6  # tweak 0.35–0.6 to taste
        self._adv = {}
        for ch in chars:
            if ch in ".:":
                slot = int(
                    max(self._digit_surf[ch].get_width(), self._advance * punct_scale)
                )
            else:
                slot = self._advance
            self._adv[ch] = slot

        self._digit_key = key

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

        # store header bottom to position value nicely later
        self._header_bottom = header_rect.bottom

    def _render_value(self, value: str):
        self._ensure_digit_cache()

        # compute value area
        inner_left = self.border_width
        inner_right = self.w - self.border_width
        inner_top = max(self._header_bottom + self.header_margin, self.border_width)
        inner_bottom = self.h - self.border_width
        area = pygame.Rect(
            inner_left, inner_top, inner_right - inner_left, inner_bottom - inner_top
        )

        pygame.draw.rect(self.image, self.bg_color, area)

        # NEW: total width from per-char advances
        advances = [self._adv.get(ch, self._advance) for ch in value]
        total_w = sum(advances) + max(0, len(value) - 1) * self.digit_gap

        x = area.centerx - total_w // 2
        y = area.centery - self.value_offset_y - self._digit_h // 2

        for i, ch in enumerate(value):
            slot_w = advances[i]
            surf = self._digit_surf.get(ch)
            if surf is None:
                surf = self.font_value.render(ch, self.antialias, self.text_color)

            # center glyph inside its (possibly narrower) slot
            gx = x + (slot_w - surf.get_width()) // 2
            gy = y + (self._digit_h - surf.get_height()) // 2
            self.image.blit(surf, (gx, gy))

            x += slot_w + self.digit_gap

    def set_lap(self, time: Optional[float] = None):
        time_str = self.format_mm_ss_hh(time) if time is not None else ""

        if time_str != self._last_time_str:
            self._last_time_str = time_str
            self._render_value(time_str)
            self.dirty = 1

    def format_mm_ss_hh(self, seconds: float) -> str:
        cs = max(0, int(seconds * 100))
        m = cs // 6000
        s = (cs // 100) % 60
        hh = cs % 100
        return f"{m:02d}:{s:02d}.{hh:02d}"

    def reset(self) -> None:
        self.set_lap(1.0)

    def update(self, packet: TelemetryFrame | None, dt: float):
        lap_count = packet.lap_count

        if lap_count == 0 or lap_count is None:
            self.reset()
            return

        if not (packet.last_lap_time == 0 or packet.last_lap_time is None):
            last_lap_time = float(packet.last_lap_time * 1e-3)
            delta = self.feed.delta_s if self.feed.has_delta else 0.0

            predicted_lap_time = last_lap_time + delta

            self.set_lap(predicted_lap_time)
