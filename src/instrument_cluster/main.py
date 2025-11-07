import datetime

import pygame

from .config import Config, ConfigManager
from .states.dashboard_state import DashboardState
from .states.state_manager import StateManager


def run(conf: Config) -> int:
    pygame.init()

    screen = pygame.display.set_mode((conf.width, conf.height))
    dashboard = DashboardState()
    state_manager = StateManager(screen, dashboard)

    running = True
    take_screenshot = False

    clock = pygame.time.Clock()
    fps = 60

    while running:
        dt = clock.tick(fps) / 1000
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    take_screenshot = True
            state_manager.handle_event(event)
        state_manager.update(dt)
        dirty_rects = state_manager.draw(screen)
        if dirty_rects:
            pygame.display.update(dirty_rects)

        if take_screenshot:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"IC_{timestamp}.png"
            pygame.image.save(screen.convert(24), filename)
            take_screenshot = False

    pygame.quit()
    return 0


def main() -> int:
    config = ConfigManager.get_config()
    return run(config)


if __name__ == "__main__":
    raise SystemExit(main())
