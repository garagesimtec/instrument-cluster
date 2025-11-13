from __future__ import annotations

from typing import Optional

from pygame.sprite import LayeredDirty

from ..backlight import Backlight
from ..config import ConfigManager
from ..states.state_manager import StateManager
from ..telemetry.mode import TelemetryMode
from ..ui.colors import Color
from ..ui.constants import (
    HEADER_BACKBUTTON_POSITION,
    HEADER_BACKBUTTON_SIZE,
    HEADER_TITLE_TOPLEFT,
)
from ..ui.events import (
    BRIGHTNESS_DOWN_PRESSED,
    BRIGHTNESS_DOWN_RELEASED,
    BRIGHTNESS_UP_PRESSED,
    BRIGHTNESS_UP_RELEASED,
    BUTTON_BACK_PRESSED,
    BUTTON_BACK_RELEASED,
    TELEMETRY_MODE_PRESSED,
    TELEMETRY_MODE_RELEASED,
    TELEMETRY_MODE_SELECTED,
)
from ..ui.utils import FontFamily, load_font
from ..ui.widgets.base.button import Button, ButtonEvents
from ..ui.widgets.base.dropdown import Dropdown
from ..ui.widgets.base.label import Label
from ..ui.widgets.base.line import Line
from .state import State


class SetupState(State):
    STEP_PERCENT = 10
    y = 200
    OPTIONS = [TelemetryMode.DEMO, TelemetryMode.UDP]

    def __init__(self, state_manager: StateManager | None = None):
        super().__init__(state_manager)

        self.title_label = Label(
            text="System  settings",
            font=load_font(size=68, family=FontFamily.PIXEL_TYPE),
            color=Color.WHITE.rgb(),
            pos=HEADER_TITLE_TOPLEFT,
            center=False,
        )
        self.back_button = Button(
            rect=(*HEADER_BACKBUTTON_POSITION, *HEADER_BACKBUTTON_SIZE),
            text="x",
            text_color=Color.WHITE.rgb(),
            text_gap=0,
            text_visible=False,
            events=ButtonEvents(
                pressed=BUTTON_BACK_PRESSED,
                released=BUTTON_BACK_RELEASED,
            ),
            font=load_font(size=50, family=FontFamily.PIXEL_TYPE),
            antialias=True,
            icon="\ue166",
            icon_color=Color.WHITE.rgb(),
            icon_size=54,
            icon_position="center",
            icon_gap=0,
        )

        self.horizontal_line = Line()

        self._backlight = Backlight()
        self.brightness_percent_value = ConfigManager.get_config().brightness
        self.brightness_percent_label = Label(
            text=f"{self.brightness_percent_value} %",
            font=load_font(size=48, family=FontFamily.PIXEL_TYPE),
            color=Color.WHITE.rgb(),
            pos=(444, SetupState.y + 15),
            center=True,
        )
        self._error: Optional[str] = None
        self.brightness_label = Label(
            text="Brightness",
            font=load_font(size=48, family=FontFamily.PIXEL_TYPE),
            color=Color.WHITE.rgb(),
            pos=(50, SetupState.y),
            center=False,
        )
        self.minus_button = Button(
            rect=(280, SetupState.y - 30, 80, 80),
            text="-",
            icon="\ue15b",
            icon_size=46,
            icon_position="center",
            text_visible=False,
            events=ButtonEvents(
                pressed=BRIGHTNESS_DOWN_PRESSED,
                released=BRIGHTNESS_DOWN_RELEASED,
            ),
            font=load_font(size=76, family=FontFamily.PIXEL_TYPE),
            text_color=Color.WHITE.rgb(),
            antialias=True,
        )
        self.plus_button = Button(
            rect=(520, SetupState.y - 30, 80, 80),
            text="+",
            icon="\ue145",
            icon_size=46,
            icon_position="center",
            text_visible=False,
            events=ButtonEvents(
                pressed=BRIGHTNESS_UP_PRESSED,
                released=BRIGHTNESS_UP_RELEASED,
            ),
            font=load_font(size=76, family=FontFamily.PIXEL_TYPE),
            text_color=Color.WHITE.rgb(),
            antialias=True,
        )

        self.telemetry_label = Label(
            text="Telemetry",
            font=load_font(size=48, family=FontFamily.PIXEL_TYPE),
            color=Color.WHITE.rgb(),
            pos=(50, SetupState.y + 140),
            center=False,
        )
        self._mode: Optional[TelemetryMode] = TelemetryMode(
            ConfigManager.get_config().telemetry_mode
        )
        self.telemetry_mode_dropdown = Dropdown(
            rect=(280, SetupState.y + 150 - 30, 320, 80),
            options=SetupState.OPTIONS,
            events=ButtonEvents(
                pressed=TELEMETRY_MODE_PRESSED,
                released=TELEMETRY_MODE_RELEASED,
                selected=TELEMETRY_MODE_SELECTED,
            ),
            font=load_font(size=40, family=FontFamily.PIXEL_TYPE),
            selected_index=SetupState.OPTIONS.index(self._mode),
        )

    def background_color(self):
        return Color.BLACK.rgb()

    def draw_static_background(self, bg):
        self.horizontal_line.draw(bg)

    def create_group(self):
        return LayeredDirty(
            [
                self.title_label,
                self.back_button,
                self.brightness_label,
                self.plus_button,
                self.minus_button,
                self.brightness_percent_label,
                self.telemetry_label,
                self.telemetry_mode_dropdown,
            ]
        )

    def enter(self, screen):
        super().enter(screen)

        if self._backlight.available():
            backlight_value = self._backlight.get_percent()
            if backlight_value is not None:
                self.brightness_percent_value = backlight_value
                self.brightness_percent_label.set_text(
                    f"{self.brightness_percent_value} %"
                )
                self._error = None
            else:
                # self.brightness_percent.set_text(None)
                self._error = "Failed to read value."
        else:
            # self.brightness_percent.set_text(None)
            self._error = "No device found."

    def handle_event(self, event):
        self.back_button.handle_event(event)
        self.plus_button.handle_event(event)
        self.minus_button.handle_event(event)
        self.telemetry_mode_dropdown.handle_event(event)

        if event.type == BUTTON_BACK_RELEASED:
            return self.on_back_released(event)
        if event.type == BRIGHTNESS_DOWN_RELEASED:
            self.adjust_brightness(-SetupState.STEP_PERCENT)
            return True
        if event.type == BRIGHTNESS_UP_RELEASED:
            self.adjust_brightness(+SetupState.STEP_PERCENT)
            return True
        if event.type in (TELEMETRY_MODE_PRESSED, TELEMETRY_MODE_RELEASED):
            return True  # swallow so it doesn’t retrigger handle_event on the dropdown
        if event.type == TELEMETRY_MODE_SELECTED:
            if event.mode is TelemetryMode.UDP:
                self._mode = TelemetryMode.UDP
                from .enter_ip_state import EnterIPState

                self.state_manager.change_state(
                    EnterIPState(
                        state_manager=self.state_manager,
                        recent_connected=(
                            ConfigManager.get_config().recent_connected or []
                        ),
                    )
                )
                return True
            else:
                ConfigManager.set_telemetry_mode(TelemetryMode.DEMO)
                self._mode = TelemetryMode.DEMO
                return True
        return False

    def update(self, dt):
        super().update(dt)

    def draw(self, surface):
        self.group.clear(surface, self.background)
        dirty = self.group.draw(surface)
        return dirty or []

    def on_back_released(self, event):
        persisted_brightness = ConfigManager.get_config().brightness
        if persisted_brightness != self.brightness_percent_value:
            ConfigManager.set_brightness_percent(self.brightness_percent_value)
        self.state_manager.pop_state()
        return True

    def adjust_brightness(self, delta_percent: int):
        tentative_value = max(
            10,
            min(
                100,
                int(self.brightness_percent_value) + delta_percent,
            ),
        )

        # Only update internal state and label if write succeeds
        if self._backlight.set_percent(tentative_value):
            self.brightness_percent_value = tentative_value
            self.brightness_percent_label.set_text(f"{self.brightness_percent_value} %")
            self._error = None
        else:
            self._error = "Failed to write brightness."
