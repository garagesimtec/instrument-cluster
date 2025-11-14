import pygame
from pygame.sprite import DirtySprite

from ...telemetry.models import TelemetryFrame
from ..colors import Color
from ..constants import LAP_WIDGET_OFFSET_Y
from ..utils import FontFamily, load_font


class LapWidget(DirtySprite):
    """
    Bordered panel with a header text and a centered dynamic value underneath.
    Redraws only when the dynamic value changes.
    """

    def __init__(
        self,
        rect: tuple[int, int, int, int],
        *,
        anchor: str = "topleft",  # "topleft" or "center"
        header_text: str = "Lap",
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
        self.font_value = load_font(size=50, family=FontFamily.D_DIN_EXP_BOLD)
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

        self.image = pygame.Surface((self.w, self.h), pygame.SRCALPHA).convert_alpha()
        self.rect = self.image.get_rect(topleft=(tlx, tly))

        self._last_lap_str = None
        self._render_border_and_header()  # border and header are static
        self.set_current_lap(-1)  # initial placeholder
        self.visible = 1
        self.dirty = 2

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

    def _render_value(self, gear_str: str):
        inner_left = self.border_width
        inner_right = self.w - self.border_width
        inner_top = max(self._header_bottom + self.header_margin, self.border_width)
        inner_bottom = self.h - self.border_width

        value_area = pygame.Rect(
            inner_left,
            inner_top,
            inner_right - inner_left,
            inner_bottom - inner_top,
        )

        pygame.draw.rect(self.image, self.bg_color, value_area)

        value_surf = self.font_value.render(gear_str, self.antialias, self.text_color)
        value_rect = value_surf.get_rect(
            center=(self.w // 2, (self.h // 2) + LAP_WIDGET_OFFSET_Y)
        )

        self.image.blit(value_surf, value_rect)

    def set_current_lap(self, lap: int):
        lap_str = str(lap)

        if lap_str != self._last_lap_str:
            self._last_lap_str = lap_str
            self._render_value(lap_str)
            self.dirty = 1

    def update(self, packet: TelemetryFrame | None, dt: float):
        flags = getattr(packet, "flags", None)
        car_on_track = bool(getattr(flags, "car_on_track", False))
        if car_on_track:
            lap = int(getattr(packet, "lap_count", 0) or 0)
        else:
            lap = 0
        self.set_current_lap(lap)
