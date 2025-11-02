from abc import ABC, abstractmethod
from typing import Optional

import pygame

from ..states.state_types import SupportsStateChange


class State(ABC):
    def __init__(self, state_manager: Optional[SupportsStateChange] = None):
        self.state_manager = state_manager
        self._listeners = []
        self._pending_transition = None

    @abstractmethod
    def handle_event(self, event) -> bool:
        """
        Handle all widget events here.
        Return True if the event is consumed and should not propagate.
        """
        return False

    @abstractmethod
    def draw(self, surface: pygame.surface.Surface):
        """
        Draw all widgets on surface
        """
        pass

    def enter(self):
        """
        Add extra listeners, start actions
        """

    def exit(self):
        """
        Remove extra listeners, cleanup
        """

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
