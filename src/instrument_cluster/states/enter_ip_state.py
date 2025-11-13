from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from pygame.sprite import LayeredDirty

from ..config import ConfigManager
from ..ip4 import get_ip_prefill
from ..states.enter_url_state import EnterURLState
from ..states.state_manager import StateManager
from ..ui.colors import Color
from ..ui.constants import (
    BUTTON_DIMENSIONS,
    BUTTON_GRID_OFFSET,
    BUTTONS_PER_ROW,
    HEADER_BACKBUTTON_POSITION,
    HEADER_BACKBUTTON_SIZE,
    HEADER_TITLE_TOPLEFT,
    NUMPAD_OFFSET,
    RECENT_BUTTONS_DIMENSIONS,
    RECENT_BUTTONS_GRID_OFFSET,
    RECENT_BUTTONS_OFFSET,
    RECENT_BUTTONS_PER_ROW,
    RECENT_CONNECTIONS_POSITION,
)
from ..ui.events import (
    BUTTON_BACK_PRESSED,
    BUTTON_BACK_RELEASED,
    ENTER_IP_DEL_BUTTON_PRESSED,
    ENTER_IP_DEL_BUTTON_RELEASED,
    ENTER_IP_KEYPAD_BUTTON_PRESSED,
    ENTER_IP_KEYPAD_BUTTON_RELEASED,
    ENTER_IP_OK_BUTTON_PRESSED,
    ENTER_IP_OK_BUTTON_RELEASED,
)
from ..ui.utils import FontFamily, load_font
from ..ui.widgets.base.button import Button, ButtonEvents, ButtonGroup
from ..ui.widgets.base.label import Label
from ..ui.widgets.base.line import Line
from ..ui.widgets.base.textfield import TextField

# from .enter_url_state import EnterURLState
from .setup_state import SetupState
from .state import State

if TYPE_CHECKING:
    pass


class EnterIPState(State):
    def __init__(
        self,
        state_manager: StateManager = None,
        recent_connected: list[str] | None = None,
    ):
        super().__init__()
        self.state_manager = state_manager
        recent_connected = recent_connected or []
        self.button_group: ButtonGroup = ButtonGroup()
        labels = list("123456789#0.")

        back_button = Button(
            rect=(*HEADER_BACKBUTTON_POSITION, *HEADER_BACKBUTTON_SIZE),
            text="x",
            text_visible=False,
            text_gap=0,
            events=ButtonEvents(
                pressed=BUTTON_BACK_PRESSED,
                released=BUTTON_BACK_RELEASED,
            ),
            font=load_font(size=50, family=FontFamily.PIXEL_TYPE),
            antialias=True,
            icon="\ue5cd",
            icon_color=Color.WHITE.rgb(),
            icon_size=50,
            icon_position="center",
            icon_gap=0,
        )
        del_button = Button(
            rect=(416, 142, 110, 76),
            text="<",
            text_visible=False,
            text_gap=0,
            events=ButtonEvents(
                pressed=ENTER_IP_DEL_BUTTON_PRESSED,
                released=ENTER_IP_DEL_BUTTON_RELEASED,
            ),
            font=load_font(size=36, family=FontFamily.PIXEL_TYPE),
            text_color=Color.LIGHT_RED.rgb(),
            antialias=True,
            icon="\ue14a",
            icon_size=46,
            icon_position="center",
            icon_gap=0,
            padding=(0, 0),
            icon_cell_width=36,
            pressed_gradient=(Color.RPM_DARK_RED.rgb(), Color.BLACK.rgb()),
            border_top_right_radius=4,
            border_bottom_right_radius=4,
        )

        ok_button = Button(
            rect=(424, 398, 100, 164),
            text="OK",
            text_visible=False,
            text_gap=0,
            events=ButtonEvents(
                pressed=ENTER_IP_OK_BUTTON_PRESSED,
                released=ENTER_IP_OK_BUTTON_RELEASED,
            ),
            font=load_font(size=50, family=FontFamily.PIXEL_TYPE),
            text_color=Color.GREEN.rgb(),
            antialias=True,
            icon="\ue5ca",
            icon_size=46,
            icon_position="center",
            icon_gap=0,
            padding=(0, 0),
            icon_cell_width=36,
            pressed_gradient=(Color.DARK_GREEN.rgb(), Color.BLACK.rgb()),
        )

        self.button_group.extend_buttons(
            self._button_grid_generator(
                labels,
                BUTTONS_PER_ROW,
                BUTTON_GRID_OFFSET,
                NUMPAD_OFFSET,
                BUTTON_DIMENSIONS,
            )
        )

        self.button_group.extend_buttons(
            self._button_grid_generator(
                recent_connected[0:3],
                RECENT_BUTTONS_PER_ROW,
                RECENT_BUTTONS_GRID_OFFSET,
                RECENT_BUTTONS_OFFSET,
                RECENT_BUTTONS_DIMENSIONS,
            )
        )
        self.button_group.add(back_button)
        self.button_group.add(del_button)
        self.button_group.add(ok_button)

        self.border_thickness = 2
        self.border_radius = 4

        self.title_label = Label(
            text="Enter  Playstation  IP",
            font=load_font(size=64, family=FontFamily.PIXEL_TYPE),
            color=Color.WHITE.rgb(),
            pos=HEADER_TITLE_TOPLEFT,
            center=False,
        )

        self.horizontal_line = Line()

        self.recent_label = Label(
            text="Recent connections",
            font=load_font(size=46, family=FontFamily.PIXEL_TYPE),
            color=Color.WHITE.rgb(),
            pos=RECENT_CONNECTIONS_POSITION,
            center=True,
            antialias=False,
            visible=len(ConfigManager.get_config().recent_connected) > 0,
        )
        self.textfield = TextField(
            text=get_ip_prefill(),
            font=load_font(size=36, family=FontFamily.NOTOSANS_REGULAR),
            color=Color.WHITE.rgb(),
            pos=(62, 142),
            width=356,
            height=76,
        )

    def background_color(self):
        return Color.BLACK.rgb()

    def draw_static_background(self, bg):
        self.horizontal_line.draw(bg)

    def create_group(self):
        return LayeredDirty(
            [
                self.title_label,
                self.recent_label,
                self.textfield,
                *self.button_group.sprites(),
            ]
        )

    def enter(self, screen):
        super().enter(screen)

    def draw(self, surface):
        self.group.clear(surface, self.background)
        dirty = self.group.draw(surface)
        return dirty or []

    def handle_event(self, event):
        self.button_group.handle_event(event)
        self.textfield.handle_event(event)

        # Consume relevant PRESSED events
        if event.type in (
            BUTTON_BACK_PRESSED,
            BUTTON_BACK_RELEASED,
            ENTER_IP_KEYPAD_BUTTON_PRESSED,
            ENTER_IP_KEYPAD_BUTTON_RELEASED,
            ENTER_IP_DEL_BUTTON_PRESSED,
            ENTER_IP_DEL_BUTTON_RELEASED,
            ENTER_IP_OK_BUTTON_PRESSED,
            ENTER_IP_OK_BUTTON_RELEASED,
        ):
            if event.type == BUTTON_BACK_RELEASED:
                return self.on_back_released(event)

            if event.type in (
                ENTER_IP_KEYPAD_BUTTON_RELEASED,
                ENTER_IP_DEL_BUTTON_RELEASED,
            ):
                return self.on_keypad_released(event)

            if event.type == ENTER_IP_OK_BUTTON_RELEASED:
                return self.on_ok_released()
            return True
        return False  # not handled here

    def on_back_released(self, event):
        self.state_manager.change_state(SetupState(self.state_manager))
        return True

    def on_ok_released(self):
        ip = self.textfield.text.strip()
        if not self.is_valid_ipv4(ip):
            return True

        cfg = ConfigManager.get_config()
        setattr(cfg, "playstation_ip", ip)

        self.state_manager.change_state(EnterURLState(self.state_manager))
        ConfigManager.last_connected(ip)
        return True

    def on_keypad_released(self, event):
        label = getattr(event, "label", None)
        if not label:
            return True
        tf = self.textfield
        txt = tf.text

        if label == ".":
            if txt.count(".") < 3 and "." not in txt[-1:]:
                tf.set_text(txt + ".")
        elif label == "<":
            tf.set_text(txt[:-1])
            tf.cursor_position = min(tf.cursor_position, len(tf.text))
        elif label == "#":
            pass
        else:
            if len(label) >= 7:
                tf.set_text(label)
                self.on_ok_released()
                return True
            else:
                tf.set_text(txt + label)
                tf.cursor_position = len(tf.text)

        tf.dirty = 1
        return True

    def is_valid_ipv4(self, ip_str):
        parts = ip_str.split(".")
        if len(parts) != 4:
            return False
        for part in parts:
            if part == "":
                return False
            if len(part) > 1 and part.startswith("0"):
                return False
            try:
                num = int(part)
            except ValueError:
                return False
            if num < 0 or num > 255:
                return False
        return True

    def update(self, dt):
        super().update(dt)
        self.textfield.update(dt)

    def _button_grid_generator(
        self,
        labels: Iterable[str],
        buttons_per_row: int,
        grid_offset: tuple[int, int],
        global_offset: tuple[int, int],
        button_size: tuple[int, int],
    ) -> list[Button]:
        return [
            Button(
                rect=(
                    i % buttons_per_row * grid_offset[0] + global_offset[0],
                    i // buttons_per_row * grid_offset[1] + global_offset[1],
                    button_size[0],
                    button_size[1],
                ),
                text=val,
                icon=None,
                events=ButtonEvents(
                    pressed=ENTER_IP_KEYPAD_BUTTON_PRESSED,
                    released=ENTER_IP_KEYPAD_BUTTON_RELEASED,
                ),
                event_data={"label": val},
                font=load_font(size=34, family=FontFamily.NOTOSANS_REGULAR),
                antialias=True,
            )
            for i, val in enumerate(labels or [])
        ]
