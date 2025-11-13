import pygame
from pygame.sprite import DirtySprite

from ...telemetry.models import TelemetryFrame
from ..colors import Color
from ..utils import FontFamily, load_font


class SpeedWidget(DirtySprite):
    """
    Bordered panel with a header text and a centered dynamic value underneath.
    Redraws only when the dynamic value changes.
    """

    def __init__(
        self,
        rect: tuple[int, int, int, int],
        *,
        anchor: str = "center",  # "topleft" or "center"
        header_text: str = "Speed",
        bg_color: tuple[int, int, int] = Color.BLACK.rgb(),
        text_color: tuple[int, int, int] = Color.WHITE.rgb(),
        border_color: tuple[int, int, int] = Color.LIGHT_GREY.rgb(),
        border_width: int = 2,
        border_radius: int = 4,
        show_border: bool = True,
        header_margin: int = 10,  # brings `header_text` down by x pixels
        antialias: bool = True,
    ):
        super().__init__()
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
        self.font_value = load_font(size=120, family=FontFamily.D_DIN_EXP_BOLD)
        self.header_text = header_text
        self.value_offset_y = 16
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

        self._last_speed_str = None
        self._render_border_and_header()  # border and header are static
        self.set_speed("0")  # initial placeholder
        self.visible = 1
        self.dirty = 2

    def _ensure_digit_cache(self):
        key = (id(self.font_value), self.text_color, self.antialias)
        if key == self._digit_key:
            return
        self._digit_surf = {
            d: self.font_value.render(d, self.antialias, self.text_color)
            for d in "0123456789"
        }
        self._digit_h = max(s.get_height() for s in self._digit_surf.values())
        self._advance = max(s.get_width() for s in self._digit_surf.values())
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

    def _render_value(self, speed_str: str):
        self._ensure_digit_cache()
        inner_left = self.border_width
        inner_right = self.w - self.border_width
        inner_top = max(self._header_bottom + self.header_margin, self.border_width)
        inner_bottom = self.h - self.border_width
        area = pygame.Rect(
            inner_left, inner_top, inner_right - inner_left, inner_bottom - inner_top
        )
        # clear
        pygame.draw.rect(self.image, self.bg_color, area)

        # center the whole strip
        n = len(speed_str)
        total_w = n * self._advance + max(0, n - 1) * self.digit_gap
        x = area.centerx - total_w // 2
        y = area.centery - self.value_offset_y - self._digit_h // 2

        for ch in speed_str:
            surf = self._digit_surf.get(ch)
            if surf is None:
                # render on the fly
                surf = self.font_value.render(ch, self.antialias, self.text_color)
            # center this glyph inside its slot
            gx = x + (self._advance - surf.get_width()) // 2
            gy = y + (self._digit_h - surf.get_height()) // 2
            self.image.blit(surf, (gx, gy))
            x += self._advance + self.digit_gap

    def set_speed(self, speed: int):
        speed_str = "0" if speed is None else str(speed)
        old = self._last_speed_str

        if speed_str != old:
            self._last_speed_str = speed_str
            self._render_value(speed_str)
            self.dirty = 1

    def update(self, packet: TelemetryFrame | None, dt: float):
        flags = getattr(packet, "flags", None)
        car_on_track = bool(getattr(flags, "car_on_track", False))
        if car_on_track:
            v = int((getattr(packet, "car_speed", 0.0) or 0.0) * 3.6)
            digits = f"{v:d}"
        else:
            digits = f"{0:d}"

        self.set_speed(digits)
