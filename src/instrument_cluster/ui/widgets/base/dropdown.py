import pygame

from ...colors import Color
from .button import AbstractButton, Button, ButtonState


class Dropdown(Button):
    def __init__(
        self,
        rect,
        options,
        events,
        event_data=None,
        selected_index=0,
        font=None,
        text_color=None,
    ):
        super().__init__(
            rect=rect,
            text=f"{options[selected_index].name}".title(),
            events=events,
            event_data=event_data,
            font=font,
            text_color=text_color or Color.WHITE.rgb(),
        )
        self.options = list(options)
        self.selected_index = selected_index
        self._expanded = False
        self._option_height = self.rect.h
        self._bg_color = Color.BLACK.rgb()
        self._base_size = self.rect.size  # (w, h) when collapsed
        self._option_height = self._base_size[1]

        # menu capture state for select-on-release
        self._menu_active_index = None  # which item was pressed
        self._menu_active_pid = None  # pointer id (0 mouse, finger_id touch)

    # --- core dropdown logic ---
    def _toggle(self):
        self._expanded = not self._expanded
        self.dirty = 1  # tell LayeredDirty to redraw
        self._on_visual_change()
        print("Dropdown toggled:", self._expanded)

    def _collapse(self):
        if self._expanded:
            self._expanded = False
            self._on_visual_change()

    def set_selected_index(self, idx, fire_event=False):
        self.selected_index = idx
        value = self.options[idx] if 0 <= idx < len(self.options) else None
        label = getattr(value, "name", str(value))
        print(
            f"[Dropdown] selected_index={idx}, mode={value} ({label})",
            flush=True,
        )  # DEBUG
        self._text = str(label).title()
        self._expanded = False
        self.dirty = 1
        self._on_visual_change()
        if fire_event and self.events.selected:
            data = dict(self.event_data or {})
            data.update({"selected_index": idx, "mode": value})
            pygame.event.post(pygame.event.Event(self.events.selected, data))

    def _expanded_menu_geometry(self):
        """Return (menu_rect, [item_rects]) in SCREEN coordinates.
        Menu starts immediately below the *collapsed* face, even when rect is enlarged."""
        face_w, face_h = self._base_size
        menu_top = self.rect.y + face_h  # NOT self.rect.bottom
        h = self._option_height
        total_h = h * len(self.options)
        menu_rect = pygame.Rect(self.rect.x, menu_top, face_w, total_h)
        items = [
            pygame.Rect(self.rect.x, menu_top + i * h, face_w, h)
            for i in range(len(self.options))
        ]
        return menu_rect, items

    def handle_event(self, event):
        # ensure capture attrs exist (defensive against hot-reloads)
        if not hasattr(self, "_menu_active_index"):
            self._menu_active_index = None
        if not hasattr(self, "_menu_active_pid"):
            self._menu_active_pid = None

        ptr_down = (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN)
        ptr_up = (pygame.MOUSEBUTTONUP, pygame.FINGERUP)
        ptr_evt = ptr_down + ptr_up + (pygame.MOUSEMOTION, pygame.FINGERMOTION)

        if event.type not in ptr_evt:
            super().handle_event(event)
            return

        # normalize pointer + coords
        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            pid = 0
        else:
            pid = getattr(event, "finger_id", None)

        xy = AbstractButton._event_xy(event)
        if xy is None:
            super().handle_event(event)
            return
        x, y = xy

        # collapsed face rect only (top area), independent of expanded size
        base_w, base_h = self._base_size
        base_rect = pygame.Rect(self.rect.x, self.rect.y, base_w, base_h)

        # ----- MENU INTERCEPT: handle menu first when expanded -----
        if getattr(self, "_expanded", False):
            menu_rect, item_rects = self._expanded_menu_geometry()

            # PRESS in menu (but not on face): start capture and consume
            if event.type in ptr_down:
                if menu_rect.collidepoint(x, y) and not base_rect.collidepoint(x, y):
                    self._menu_active_index = None
                    for i, r in enumerate(item_rects):
                        if r.collidepoint(x, y):
                            self._menu_active_index = i
                            self._menu_active_pid = pid
                            break
                    return  # consume menu press

                # press outside both menu and face -> collapse & consume
                if not (menu_rect.collidepoint(x, y) or base_rect.collidepoint(x, y)):
                    self._expanded = False
                    self._menu_active_index = None
                    self._menu_active_pid = None
                    self.dirty = 1
                    self._on_visual_change()
                    return
                # press on face while expanded -> let Button show gradient; fall through

            # RELEASE: select only if same pointer + same item
            if event.type in ptr_up and self._menu_active_pid == pid:
                if self._menu_active_index is not None:
                    idx = self._menu_active_index
                    if 0 <= idx < len(item_rects) and item_rects[idx].collidepoint(
                        x, y
                    ):
                        self.set_selected_index(idx, fire_event=True)  # prints & posts
                        self._menu_active_index = None
                        self._menu_active_pid = None
                        return
                # clear capture; collapse if released outside both
                self._menu_active_index = None
                self._menu_active_pid = None
                if not (menu_rect.collidepoint(x, y) or base_rect.collidepoint(x, y)):
                    self._expanded = False
                    self.dirty = 1
                    self._on_visual_change()
                    return
            # otherwise: let Button handle face press/release/gradient

        # ----- BUTTON FACE: delegate to base and toggle on RELEASE inside face -----
        prev_state = self.state
        super().handle_event(event)

        if prev_state == ButtonState.PRESSED and self.state == ButtonState.RELEASED:
            if base_rect.collidepoint(x, y):
                # face click toggles open/close
                self._expanded = not self._expanded
                # clear any stale menu capture when closing
                if not self._expanded:
                    self._menu_active_index = None
                    self._menu_active_pid = None
                self.dirty = 1
                self._on_visual_change()
                return

    def _on_visual_change(self):
        """
        Rebuild the sprite image/rect for LayeredDirty.
        - Collapsed: image = base button (size = _base_size)
        - Expanded : image = base button + menu items stacked below (taller surface)
        """
        # First build the base button surface via Button (this sets self.image to button-only)
        # and also ensures caches/pressed gradient, etc.
        # Force rect back to base size before composing the base button.
        self.rect.size = self._base_size
        super()._on_visual_change()  # -> self.image is the composed button (base height)

        if not self._expanded or not self.options:
            # collapsed: keep base image/rect
            self.dirty = 1
            return

        # We are expanded: extend the image downward with menu items
        base_img = self.image
        base_w, base_h = base_img.get_size()
        h = self._option_height
        menu_h = h * len(self.options)

        extended = pygame.Surface((base_w, base_h + menu_h), pygame.SRCALPHA)
        # draw base button at top
        extended.blit(base_img, (0, 0))

        border_color = self._compute_border_color()  # same as Button's border color
        sep_color = (100, 100, 100)

        for i, opt in enumerate(self.options):
            y = base_h + i * h
            is_last = i == len(self.options) - 1
            is_selected = i == self.selected_index

            # bg = Color.DARK_GREY.rgb() if is_selected else Color.BLACK.rgb()
            bg = Color.BLACK.rgb()

            rect = pygame.Rect(0, y, base_w, h)

            if is_last:
                # --- fill with rounded bottom corners only ---
                pygame.draw.rect(
                    extended,
                    bg,
                    rect,
                    0,
                    border_radius=0,
                    border_bottom_left_radius=4,
                    border_bottom_right_radius=4,
                )
                # --- 2px border with the same rounded bottom corners ---
                pygame.draw.rect(
                    extended,
                    border_color,
                    rect,
                    2,
                    border_radius=0,
                    border_bottom_left_radius=4,
                    border_bottom_right_radius=4,
                )
            else:
                # --- square fill and square 2px border ---
                pygame.draw.rect(extended, bg, rect, 0)
                pygame.draw.rect(extended, border_color, rect, 2)

                # optional thin separator at the bottom of non-last items (inside the border)
                pygame.draw.line(
                    extended, sep_color, (2, y + h - 1), (base_w - 3, y + h - 1), 1
                )

            # label
            label = opt.name if hasattr(opt, "name") else str(opt)
            ts = self.font.render(label.title(), self.antialias, self.color)
            extended.blit(ts, (20, y + (h - ts.get_height()) // 2))

        # Swap in the extended image and grow the rect so LayeredDirty will blit the whole menu
        self.image = extended
        self.rect.size = extended.get_size()
        self.dirty = 1

    # --- draw ---
    def draw(self, surface):
        # Let LayeredDirty blit self.image at self.rect; this is also fine if you call manually
        surface.blit(self.image, self.rect)
