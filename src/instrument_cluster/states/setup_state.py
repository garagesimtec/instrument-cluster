from __future__ import annotations

from ..config import ConfigManager
from ..ui.colors import Color
from ..ui.constants import HEADER_TITLE_TOPLEFT
from ..ui.events import BUTTON_BACK_PRESSED, BUTTON_BACK_RELEASED
from ..ui.utils import FontFamily, load_font
from ..ui.widgets.base.button import Button
from ..ui.widgets.base.label import Label
from ..ui.widgets.base.line import Line
from .state import State
from .state_manager import StateManager


class SetupState(State):
    def __init__(self, state_manager):
        super().__init__()
        self.state_manager: StateManager = state_manager

        self.title_label = Label(
            text="System settings",
            font=load_font(size=64, family=FontFamily.PIXEL_TYPE),
            color=Color.WHITE.rgb(),
            pos=HEADER_TITLE_TOPLEFT,
            center=False,
        )

        self.back_button = Button(
            rect=(ConfigManager.get_config().width - 90, 10, 70, 70),
            text="x",
            text_color=Color.WHITE.rgb(),
            text_gap=0,
            text_visible=False,
            event_type_pressed=BUTTON_BACK_PRESSED,
            event_type_released=BUTTON_BACK_RELEASED,
            font=load_font(size=50, family=FontFamily.PIXEL_TYPE),
            antialias=True,
            icon="\ue166",
            icon_color=Color.WHITE.rgb(),
            icon_size=46,
            icon_position="center",
            icon_gap=0,
        )

        self.horizontal_line = Line()

    def enter(self):
        super().enter()

    def handle_event(self, event):
        self.back_button.handle_event(event)

        if event.type == BUTTON_BACK_RELEASED:
            return self.on_back_released(event)

        return False

    def draw(self, surface):
        surface.fill(Color.BLACK.rgb())

        self.title_label.draw(surface)
        self.horizontal_line.draw(surface)
        self.back_button.draw(surface)

    def on_back_released(self, event):
        self.state_manager.pop_state()
        return True

    def update(self, dt):
        super().update(dt)
