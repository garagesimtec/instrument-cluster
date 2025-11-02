from __future__ import annotations

from typing import List, Optional

import pygame

from ..states.state import State
from ..states.state_types import SupportsStateChange


class StateManager(SupportsStateChange):
    def __init__(self, initial_state: Optional[State] = None):
        self._stack: List[State] = []
        if initial_state is not None:
            self.push_state(initial_state)

    @property
    def current_state(self) -> Optional[State]:
        return self._stack[-1] if self._stack else None

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Dispatch an event to states from top to bottom until handled.

        Iterates the stack in reverse (top-first). For each state:
            - Calls `state.handle_event(event)` and coerces the result to `bool`.
            - Stops at the first state that returns truthy and returns True.

        Args:
            event: a pygame.event.Event object.

        Returns:
            True if any state handled the event; otherwise False.
        """
        for state in reversed(self._stack):
            if bool(state.handle_event(event)):
                return True
        return False

    def update(self, dt: float):
        """Update states in stack order using a snapshot for stability.

        Strategy:
            - Take a shallow snapshot of the current stack to avoid issues if
              callbacks mutate the stack during iteration.
            - For each state in the snapshot:
                * Skip if it has been removed from the live stack.
                * Call `state.update(dt)`; exceptions are caught and suppressed
                  so a misbehaving state does not break the loop.

        Args:
            dt: Time delta since the last update (unit in seconds).
        """
        if not self._stack:
            return
        snapshot = list(self._stack)

        for s in snapshot:
            if s not in self._stack:
                continue
            try:
                s.update(dt)
            except Exception:
                # Misbehaving state's update shouldn't brake the loop
                pass

    def draw(self, surface: pygame.surface.Surface):
        if self._stack:
            # Only the top state draws,
            # overlays control their visuals!
            self._stack[-1].draw(surface)

    def change_state(self, new_state: State):
        if self._stack:
            top = self._stack.pop()
            try:
                top.exit()
            except Exception:
                pass
        self.push_state(new_state)

    def push_state(self, state: State):
        """
        Push a new state on top. Pause the previous top (do NOT exit), so it
        can keep running in the background if it opts in.
        """
        top = self.current_state
        if top is not None:
            try:
                top.on_pause()
            except Exception:
                pass
        state.state_manager = self
        self._stack.append(state)
        state.enter()

    def pop_state(self):
        if not self._stack:
            return
        top = self._stack.pop()

        try:
            top.exit()
        except Exception:
            pass
        if self._stack:
            try:
                state = self._stack[-1]
                state.on_resume()
            except Exception:
                pass
