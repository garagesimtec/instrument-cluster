import pygame

from .config import Config, ConfigManager
from .states.dashboard_state import DashboardState
from .states.state_manager import StateManager


def run(conf: Config) -> int:
    pygame.init()

    screen = pygame.display.set_mode((conf.width, conf.height))
    dashboard = DashboardState()
    state_manager = StateManager(dashboard)
    dashboard.state_manager = state_manager
    running = True
    clock = pygame.time.Clock()
    fps = 60

    while running:
        dt = clock.tick(fps) / 1000
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            state_manager.handle_event(event)
        state_manager.update(dt)
        state_manager.draw(screen)
        pygame.display.flip()

    pygame.quit()
    return 0


def main() -> int:
    config = ConfigManager.get_config()
    return run(config)


if __name__ == "__main__":
    raise SystemExit(main())
