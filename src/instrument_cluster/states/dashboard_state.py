from instrument_cluster.config import ConfigManager

from ..states.state import State
from ..states.state_manager import StateManager
from ..ui.colors import Color
from ..ui.constants import FOOTER_BUTTONGROUP_MARGIN, FOOTER_BUTTONGROUP_X
from ..ui.events import BUTTON_SETUP_PRESSED, BUTTON_SETUP_RELEASED
from ..ui.utils import FontFamily, load_font
from ..ui.widgets.base.button import Button, ButtonGroup


class DashboardState(State):
    def __init__(self, state_manager: StateManager = None):
        super().__init__(state_manager)

        setup = Button(
            rect=(0, 0, 100, 70),
            text="Setup",
            text_color=Color.WHITE.rgb(),
            text_gap=0,
            text_visible=True,
            event_type_pressed=BUTTON_SETUP_PRESSED,
            event_type_released=BUTTON_SETUP_RELEASED,
            font=load_font(size=32, family=FontFamily.PIXEL_TYPE),
            antialias=False,
            icon="\ue8b8",
            icon_color=Color.WHITE.rgb(),
            icon_size=30,
            icon_position="center",
            icon_gap=0,
            content_align="center",
            padding=(0, 0),
            icon_cell_width=36,
        )

        self.buttons = ButtonGroup(
            [setup],
            position=(
                FOOTER_BUTTONGROUP_X,
                ConfigManager.get_config().height
                - setup.rect.height
                - FOOTER_BUTTONGROUP_MARGIN,
            ),
        )

    def draw(self, surface):
        surface.fill(Color.BLACK.rgb())
        self.buttons.draw(surface)

    def update(self, dt: float):
        self.buttons.update(dt)

    def handle_event(self, event):
        self.buttons.handle_event(event)

        if event.type == BUTTON_SETUP_RELEASED:
            from ..states.setup_state import SetupState

            self.state_manager.push_state(SetupState(self.state_manager))
            return True
        return False
