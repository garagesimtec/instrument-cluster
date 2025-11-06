from pygame.sprite import LayeredDirty

from ..config import ConfigManager
from ..states.setup_state import SetupState
from ..states.state import State
from ..states.state_manager import StateManager
from ..ui.colors import Color
from ..ui.constants import (
    BUTTON_HEIGHT,
    FOOTER_BUTTONGROUP_MARGIN,
    FOOTER_BUTTONGROUP_X,
)
from ..ui.events import (
    BUTTON_SETUP_LONGPRESSED,
    BUTTON_SETUP_PRESSED,
    BUTTON_SETUP_RELEASED,
)
from ..ui.utils import FontFamily, load_font
from ..ui.widgets.base.button import Button, ButtonEvents


class DashboardState(State):
    def __init__(self, state_manager: StateManager = None):
        super().__init__(state_manager)

        self.setup = Button(
            rect=(
                FOOTER_BUTTONGROUP_X,
                ConfigManager.get_config().height
                - BUTTON_HEIGHT
                - FOOTER_BUTTONGROUP_MARGIN,
                100,
                BUTTON_HEIGHT,
            ),
            text="Setup",
            text_color=Color.WHITE.rgb(),
            text_gap=0,
            text_visible=True,
            text_position="bottom",
            events=ButtonEvents(
                pressed=BUTTON_SETUP_PRESSED,
                released=BUTTON_SETUP_RELEASED,
                long_pressed=BUTTON_SETUP_LONGPRESSED,
            ),
            font=load_font(size=32, family=FontFamily.PIXEL_TYPE),
            antialias=False,
            icon="\ue8b8",
            icon_color=Color.WHITE.rgb(),
            icon_size=34,
            icon_position="center",
            icon_gap=0,
            content_align="center",
            padding=(0, 0),
            icon_cell_width=36,
        )

    def background_color(self):
        return Color.BLACK.rgb()

    def draw_static_background(self, bg):
        pass

    def create_group(self):
        return LayeredDirty([self.setup])

    def enter(self, screen):
        super().enter(screen)

    def draw(self, surface):
        self.group.clear(surface, self.background)
        dirty = self.group.draw(surface)
        return dirty or []

    def update(self, dt: float):
        self.setup.update(dt)

    def handle_event(self, event):
        self.setup.handle_event(event)

        if event.type == BUTTON_SETUP_RELEASED:
            self.state_manager.push_state(SetupState(self.state_manager))
            return True
        if event.type == BUTTON_SETUP_LONGPRESSED:
            pass
            return True
        return False
