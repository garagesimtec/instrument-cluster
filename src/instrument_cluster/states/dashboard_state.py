from typing import Optional

from pygame.sprite import LayeredDirty

from ..backlight import Backlight
from ..config import Config, ConfigManager
from ..states.setup_state import SetupState
from ..states.state import State
from ..states.state_manager import StateManager
from ..telemetry.feed import Feed
from ..telemetry.mode import TelemetryMode
from ..telemetry.models import TelemetryFrame
from ..telemetry.source import TelemetrySource
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
from ..ui.widgets.bestlap_widget import BestLapWidget
from ..ui.widgets.delta_widget import DeltaWidget
from ..ui.widgets.gear_widget import GearWidget
from ..ui.widgets.lap_widget import LapWidget
from ..ui.widgets.predictedlap_widget import PredictedLapWidget
from ..ui.widgets.speed_widget import SpeedWidget


class DashboardState(State):
    def __init__(
        self,
        state_manager: StateManager = None,
        telemetry: Optional[TelemetryFrame] = None,
    ):
        super().__init__(state_manager)

        # -----------------------------------------------
        # T E L E M E T R Y
        # -----------------------------------------------
        cfg: Config = ConfigManager.get_config()
        self._last_mode: TelemetryMode = TelemetryMode(cfg.telemetry_mode)

        if telemetry is None:
            mode = TelemetryMode(cfg.telemetry_mode)
            self.telemetry = TelemetrySource(
                mode=mode,
                host=cfg.udp_host,
                port=cfg.udp_port,
            )
        else:
            self.telemetry = telemetry

        self.packet = None

        self.ui = LayeredDirty()
        self.widgets = LayeredDirty()

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
            text_position="top",
            events=ButtonEvents(
                pressed=BUTTON_SETUP_PRESSED,
                released=BUTTON_SETUP_RELEASED,
                long_pressed=BUTTON_SETUP_LONGPRESSED,
            ),
            font=load_font(size=32, family=FontFamily.PIXEL_TYPE),
            antialias=True,
            icon="\ue8b8",
            icon_color=Color.WHITE.rgb(),
            icon_size=34,
            icon_position="center",
            icon_gap=0,
            content_align="center",
            padding=(0, 6, 0, 0),  # 6 px gap to the upper border
            icon_cell_width=34,
        )

        self.ui.add(self.setup)

        gear_widget = GearWidget(
            rect=(
                ConfigManager.get_config().width // 2,
                400,
                186,
                232,
            ),
            show_border=False,
        )

        speed_widget = SpeedWidget(
            rect=(
                ConfigManager.get_config().width // 2,
                100,
                220,
                160,
            )
        )

        bestlap_widget = BestLapWidget(
            rect=(
                186,
                68,
                352,
                92,
            )
        )

        lastlap_widget = LapWidget(rect=(870, 440, 286, 92))

        feed = Feed()
        predictedlap_widget = PredictedLapWidget(rect=(186, 162, 352, 92), feed=feed)
        diff_widget = DeltaWidget(rect=(870, 340, 286, 92), feed=feed)

        self.widgets.add(
            gear_widget,
            speed_widget,
            bestlap_widget,
            predictedlap_widget,
            lastlap_widget,
            diff_widget,
        )

    def background_color(self):
        return Color.BLACK.rgb()

    def draw_static_background(self, bg):
        pass

    def create_group(self):
        # keep for compatibility if something else relies on .group
        # combine layers: widgets under UI
        self.group = LayeredDirty()
        for spr in self.widgets.sprites():
            self.group.add(spr, layer=0)
        for spr in self.ui.sprites():
            self.group.add(spr, layer=1)
        return self.group

    def enter(self, screen):
        super().enter(screen)
        try:
            bl = Backlight()
            if bl.available():
                bl.set_percent(ConfigManager.get_config().brightness)
        except Exception:
            pass

    def draw(self, surface):
        # clear both groups against same background
        self.widgets.clear(surface, self.background)
        self.ui.clear(surface, self.background)

        dirty = []
        dirty.extend(self.widgets.draw(surface))
        dirty.extend(self.ui.draw(surface))

        return dirty or []

    def update(self, dt: float):
        super().update(dt)
        # get fresh telemetry frame once per tick
        packet = None
        try:
            packet = self.telemetry.latest()
        except Exception:
            packet = None

        # update telemetry-driven widgets with (packet, dt)
        self.widgets.update(packet, dt)

        # update UI controls with (dt) only
        self.ui.update(dt)

    def handle_event(self, event):
        self.setup.handle_event(event)

        if event.type == BUTTON_SETUP_RELEASED:
            self.state_manager.push_state(SetupState(self.state_manager))
            return True
        if event.type == BUTTON_SETUP_LONGPRESSED:
            return True
        return False
