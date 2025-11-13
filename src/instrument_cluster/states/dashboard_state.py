from typing import Optional

from pygame.sprite import LayeredDirty

from ..backlight import Backlight
from ..config import Config, ConfigManager
from ..logger import Logger
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
    FOOTER_BUTTONGROUP_Y,
)
from ..ui.events import (
    BUTTON_SETUP_LONGPRESSED,
    BUTTON_SETUP_PRESSED,
    BUTTON_SETUP_RELEASED,
)
from ..ui.utils import FontFamily, load_font
from ..ui.widgets.base.button import Button, ButtonEvents
from ..ui.widgets.delta_time_widget import DeltaTimeWidget
from ..ui.widgets.fastest_lap_time_widget import FastestLapTimeWidget
from ..ui.widgets.gear_widget import GearWidget
from ..ui.widgets.lap_time_widget import LapTimeWidget
from ..ui.widgets.lap_widget import LapWidget
from ..ui.widgets.predicted_lap_time_widget import PredictedLapTimeWidget
from ..ui.widgets.speed_widget import SpeedWidget


class DashboardState(State):
    def __init__(
        self,
        state_manager: StateManager = None,
        telemetry: Optional[TelemetryFrame] = None,
    ):
        super().__init__(state_manager)
        self.logger = Logger(__class__.__name__).get()

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
                FOOTER_BUTTONGROUP_Y,
                110,
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
            padding=(0, 8, 0, 0),  # 8 px gap to the upper border
            icon_cell_width=34,
        )

        self.ui.add(self.setup)

        width = ConfigManager.get_config().width

        gear_widget = GearWidget(rect=(width // 2, 388, 186, 232), show_border=False)
        speed_widget = SpeedWidget(rect=(width // 2, 100, 220, 160), show_border=False)
        lap_widget = LapWidget(
            rect=(
                922,
                FOOTER_BUTTONGROUP_Y - FOOTER_BUTTONGROUP_MARGIN,
                90,
                BUTTON_HEIGHT + FOOTER_BUTTONGROUP_MARGIN,
            ),
            show_border=True,
        )
        bestlap_widget = FastestLapTimeWidget(rect=(186, 68, 352, 92))
        lastlap_widget = LapTimeWidget(rect=(870, 440, 286, 92))

        feed = Feed()
        predictedlap_widget = PredictedLapTimeWidget(
            rect=(186, 163, 352, 92), feed=feed
        )
        delta_widget = DeltaTimeWidget(rect=(870, 344, 286, 92), feed=feed)

        self.widgets.add(
            gear_widget,
            speed_widget,
            bestlap_widget,
            predictedlap_widget,
            lastlap_widget,
            delta_widget,
            lap_widget,
        )

    def background_color(self):
        return Color.BLACK.rgb()

    def draw_static_background(self, bg):
        pass

    def create_group(self):
        # combine layers: widgets under UI
        self.group = LayeredDirty()
        for spr in self.widgets.sprites():
            self.group.add(spr, layer=0)
        for spr in self.ui.sprites():
            self.group.add(spr, layer=1)
        return self.group

    def enter(self, screen):
        super().enter(screen)
        self.telemetry.start()

        bl = Backlight()
        if bl.available():
            bl.set_percent(ConfigManager.get_config().brightness)

    def exit(self):
        self.telemetry.stop()
        super().exit()

    def on_resume(self):
        self._reconfigure_telemetry_if_needed()

    def on_pause(self):
        pass

    def draw(self, surface):
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

    def _reconfigure_telemetry_if_needed(self):
        """Swap TelemetrySource if the persisted mode changed (e.g., DEMO <-> UDP)."""
        cfg = ConfigManager.get_config()
        desired_mode = TelemetryMode(cfg.telemetry_mode)

        if desired_mode == self._last_mode:
            return

        try:
            self.telemetry.stop()
        except Exception:
            pass

        try:
            self.telemetry = TelemetrySource(
                mode=desired_mode,
                host=cfg.udp_host,
                port=cfg.udp_port,
            )
            self.telemetry.start()
            self._last_mode = desired_mode
            self.logger.info(f"Telemetry mode switched to {desired_mode.name}")
        except Exception as e:
            self.logger.error(f"Failed to switch telemetry to {desired_mode}: {e}")
