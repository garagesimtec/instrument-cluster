from __future__ import annotations

import pygame
from pygame.sprite import LayeredDirty

from ..addons.installer import (
    DEFAULT_TARBALL_URL,
    InstallResult,
    install_from_url,
    service_status,
)
from ..config import ConfigManager
from ..states.state_manager import StateManager
from ..telemetry.mode import TelemetryMode
from ..ui.colors import Color
from ..ui.constants import HEADER_TITLE_TOPLEFT
from ..ui.events import (
    BUTTON_BACK_PRESSED,
    BUTTON_BACK_RELEASED,
    INSTALL_PRESSED,
    INSTALL_RELEASED,
)
from ..ui.utils import FontFamily, load_font
from ..ui.widgets.base.button import Button, ButtonEvents, ButtonGroup
from ..ui.widgets.base.label import Label
from ..ui.widgets.base.line import Line
from ..ui.widgets.base.textfield import TextField
from .state import State


class EnterURLState(State):
    """
    Enter the granturismo tarball URL and install it.

    - TextField prefilled with DEFAULT_TARBALL_URL
    - 'Download' and 'Cancel' buttons
    - On Download:
        * downloads/extracts tarball into /opt/granturismo
        * installer writes /etc/default/simdash-proxy and enables/starts the unit
          (on macOS, service control is 'unavailable' but install still succeeds)
        * telemetry mode switched to UDP, then return to Settings
    """

    def __init__(self, state_manager: StateManager = None):
        super().__init__(state_manager)
        self._error: str | None = None
        self._status: str | None = None

        self._w, self._h = (
            ConfigManager.get_config().width,
            ConfigManager.get_config().height,
        )

        self.title_label = Label(
            text="UDP Telemetry",
            font=load_font(size=64, family=FontFamily.PIXEL_TYPE),
            color=Color.WHITE.rgb(),
            pos=HEADER_TITLE_TOPLEFT,
            center=False,
        )

        self.horizontal_line = Line()

        self.textfield = TextField(
            text=DEFAULT_TARBALL_URL,
            font=load_font(size=24, family=FontFamily.PIXEL_TYPE),
            color=Color.WHITE.rgb(),
            pos=(self._w // 8, self._h // 4),
            width=840,
            height=60,
            border_color=Color.GREY.rgb(),
        )

        self.download_button = Button(
            rect=(self._w // 2 - 220, self._h // 2 - 40, 200, 70),
            text="Install",
            text_visible=True,
            font=load_font(size=40, family=FontFamily.PIXEL_TYPE),
            antialias=True,
            events=ButtonEvents(
                pressed=INSTALL_PRESSED,
                released=INSTALL_RELEASED,
            ),
        )
        self.cancel_button = Button(
            rect=(self._w // 2, self._h // 2 - 40, 200, 70),
            text="Cancel",
            text_visible=True,
            font=load_font(size=40, family=FontFamily.PIXEL_TYPE),
            antialias=True,
            events=ButtonEvents(
                pressed=BUTTON_BACK_PRESSED,
                released=BUTTON_BACK_RELEASED,
            ),
        )

        self.btns = ButtonGroup()
        self.btns.add(self.download_button)
        self.btns.add(self.cancel_button)

    def background_color(self):
        return Color.BLACK.rgb()

    def draw_static_background(self, bg):
        self.horizontal_line.draw(bg)

    def create_group(self):
        return LayeredDirty(
            [
                self.title_label,
                self.textfield,
                *self.btns.sprites(),
            ]
        )

    def enter(self, screen):
        super().enter(screen)

    def draw(self, surface):
        self.group.clear(surface, self.background)
        dirty = self.group.draw(surface)
        return dirty or []

    def handle_event(self, event) -> bool:
        self.btns.handle_event(event)
        self.textfield.handle_event(event)

        if event.type in (BUTTON_BACK_PRESSED, INSTALL_PRESSED):
            return True  # consume

        if event.type == BUTTON_BACK_RELEASED:
            from .setup_state import SetupState

            self.state_manager.change_state(SetupState(self.state_manager))
            return True  # consume

        if event.type == INSTALL_RELEASED:
            self._perform_install()
            return True  # consume

        if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
            self._perform_install()
            return True  # consume

        if event.type == pygame.MOUSEBUTTONUP:
            if self.download_button.rect.collidepoint(event.pos):
                self._perform_install()
                return True  # consume

        return False

    def _perform_install(self):
        # Read URL and PS IP from config
        url = (self.textfield.text or "").strip() or DEFAULT_TARBALL_URL
        cfg = ConfigManager.get_config()
        ps_ip = (getattr(cfg, "playstation_ip", "") or "").strip()
        if not ps_ip:
            self._error = "PS5 IP not set. Enter it first."
            return

        try:
            self._status = "Downloading and installing…"
            res: InstallResult = install_from_url(
                url=url,
                ps_ip=ps_ip,
                sha256=None,
                jsonl_output="udp://127.0.0.1:5600",
            )
        except Exception as e:
            self._error = f"Install failed: {e}"
            self._status = None
            return

        if not res.ok:
            self._error = res.message or "Install failed."
            self._status = None
            return

        # set mode to UDP and go back to Dashboard
        ConfigManager.set_telemetry_mode(TelemetryMode.UDP)
        self._status = f"Installed. Proxy status: {service_status()}"

        from ..telemetry.source import TelemetrySource
        from .dashboard_state import DashboardState

        telemetry = TelemetrySource(
            mode=ConfigManager.get_config().telemetry_mode,
            host=ConfigManager.get_config().udp_host,
            port=ConfigManager.get_config().udp_port,
        )

        self.state_manager.pop_state()  # pops EnterURLState

        cur = self.state_manager.current_state
        if isinstance(cur, DashboardState):
            cur.set_telemetry(telemetry, update_config=False)
        else:
            from .dashboard_state import DashboardState

            self.state_manager.change_state(
                DashboardState(state_manager=self.state_manager, telemetry=telemetry)
            )

    def update(self, dt):
        super().update(dt)
        self.textfield.update(dt)

    # def draw(self, surface):
    #     surface.fill(Color.BLACK.rgb())
    #     self.title_label.draw(surface)

    #     self.textfield.draw(surface)
    #     self.btns.draw(surface)

    #     if self._status:
    #         s_font = load_font(size=28, family=FontFamily.PIXEL_TYPE)
    #         s_txt = s_font.render(self._status, False, Color.WHITE.rgb())
    #         s_rect = s_txt.get_rect(
    #             center=(self._w // 2, self.textfield.rect.bottom + 40)
    #         )
    #         surface.blit(s_txt, s_rect.topleft)

    #     if self._error:
    #         e_font = load_font(size=28, family=FontFamily.PIXEL_TYPE)
    #         e_txt = e_font.render(self._error, False, Color.LIGHTEST_RED.rgb())
    #         e_rect = e_txt.get_rect(
    #             center=(self._w // 2, self.textfield.rect.bottom + 180)
    #         )
    #         surface.blit(e_txt, e_rect.topleft)
