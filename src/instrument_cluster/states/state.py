from abc import ABC, abstractmethod
from typing import Optional

import pygame

from ..states.state_types import SupportsStateChange


class State(ABC):
    def __init__(self, state_manager: Optional[SupportsStateChange] = None):
        self.state_manager = state_manager
        self.screen: pygame.Surface | None = None
        self.background: pygame.Surface | None = None
        self.group = None
        self._pending_transition = None

    def background_color(self) -> tuple[int, int, int]:
        return (0, 0, 0)

    def draw_static_background(self, bg: pygame.Surface) -> None:
        """Draw lines, frames onto background once."""
        pass

    def create_group(self):
        """Return a LayeredDirty with sprites or None."""
        return None

    @abstractmethod
    def handle_event(self, event) -> bool:
        """
        Handle all widget events here.
        Return True if the event is consumed and should not propagate.
        """
        return False

    @abstractmethod
    def draw(self, surface: pygame.Surface):
        """
        Incremental dirty draw; states override.
        """
        return []

    def enter(self, screen: pygame.Surface):
        self.screen = screen

        self.background = pygame.Surface(screen.get_size()).convert()
        self.background.fill(self.background_color())

        # Let the concrete state add static stuff
        self.draw_static_background(self.background)

        # Initial blit, StateManager.full_paint() will repaint anyway
        screen.blit(self.background, (0, 0))

        # Build sprite group (DirtySprites only)
        self.group = self.create_group()

        # Ask manager to do a full update once
        return [screen.get_rect()]

    def exit(self):
        """
        Remove extra listeners, cleanup
        """
        pass

    def full_paint(self, surface: pygame.Surface):
        """Paint whole background + sprites once."""
        if self.background is not None:
            surface.blit(self.background, (0, 0))

        group = getattr(self, "group", None)
        if group:
            # Force all sprites to redraw on this pass
            for sprite in group.sprites():
                sprite.dirty = 1

            group.clear(surface, self.background)
            group.draw(surface)

    def update(self, dt: float):
        """
        Update animation, etc.
        """
        if self.process_delayed_transition(self.state_manager):
            return

    def on_pause(self):
        pass

    def on_resume(self):
        pass

    def request_delayed_transition(self, next_state, delay_seconds):
        trigger_time = pygame.time.get_ticks() / 1000.0 + delay_seconds
        self._pending_transition = (next_state, trigger_time)

    def process_delayed_transition(self, state_manager: SupportsStateChange):
        """Call this from the state_manager or each state's update() every frame."""
        if self._pending_transition:
            _, trigger_time = self._pending_transition
            now = pygame.time.get_ticks() / 1000.0
            if now >= trigger_time:
                next_state, _ = self._pending_transition
                self._pending_transition = None
                state_manager.change_state(next_state)
                return True  # Transition occurred
        return False
