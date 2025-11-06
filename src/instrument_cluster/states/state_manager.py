from __future__ import annotations

from typing import List, Optional

import pygame

from ..states.state import State
from ..states.state_types import SupportsStateChange


class StateManager(SupportsStateChange):
    def __init__(self, screen: pygame.Surface, initial_state: Optional[State] = None):
        self._screen = screen
        self._stack: List[State] = []
        self._pending_rects: list[pygame.Rect] = []

        if initial_state is not None:
            self.push_state(initial_state)

    @property
    def current_state(self) -> Optional[State]:
        return self._stack[-1] if self._stack else None

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Dispatch event to base state stack."""
        # handle base states top to bottom
        for state in reversed(self._stack):
            try:
                if bool(state.handle_event(event)):
                    return True
            except Exception as e:
                print(e)
        return False

    def update(self, dt: float):
        """Update base states (snapshot) and all overlays."""
        try:
            self.current().update(dt)
        except Exception:
            # Misbehaving state's update shouldn't break the loop
            pass

    def current(self):
        return self._stack[-1]

    def draw(self, surface: pygame.Surface):
        s = self.current()
        if not s:
            return []

        # If we have queued “full rects”, paint base + overlays once, then return those rects
        if getattr(self, "_pending_rects", None):
            try:
                s.full_paint(surface)  # base state
            except Exception as e:
                print("full_paint error:", e)
            rects = self._pending_rects
            self._pending_rects = []
            return rects

        # Normal incremental: base first, then overlays
        rects: list[pygame.Rect] = []
        r = s.draw(surface)
        if r:
            rects.extend(r)
        return rects

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
            except Exception as e:
                print(e)
        state.state_manager = self
        self._stack.append(state)
        try:
            rects = state.enter(self._screen) or [self._screen.get_rect()]
            self._pending_rects = list(rects)
        except Exception as e:
            print(e)

    def pop_state(self):
        if not self._stack:
            return
        top = self._stack.pop()

        try:
            top.exit()
        except Exception:
            pass
        if self._stack:
            state = self._stack[-1]
            try:
                state.on_resume()
            finally:
                self._pending_rects = [self._screen.get_rect()]
