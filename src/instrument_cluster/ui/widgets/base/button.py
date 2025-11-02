from enum import Enum, auto
from typing import Literal, Optional, Tuple

import pygame

from ...colors import Color
from ...utils import FontFamily, load_font
from .container import Container

"""Lightweight button widgets for Pygame with text+icon layout.

This module provides:
- `AbstractButton`: input/state handling (mouse + touch), no visuals.
- `ButtonGroup`: convenience container for multiple buttons.
- `Button`: a concrete rectangular button that can render text and an
  optional icon (e.g., Material Symbols glyphs from a TTF) with flexible
  positioning, gap, padding, and alignment.

The rendering uses Pygame Surfaces only—no external UI libs.

Performance:
- Caches rendered text/icon Surfaces.
- Caches computed layout positions.
- Caches a composed button Surface (border + content).
Rebuilds occur only when inputs that affect visuals change.
"""


class ButtonState(Enum):
    IDLE = auto()
    PRESSED = auto()
    RELEASED = auto()


class AbstractButton:
    """Base class for buttons with unified mouse/touch handling.

    Tracks a simple state machine (IDLE -> PRESSED -> RELEASED) and normalizes
    input from both the mouse and touch events. Subclasses must override
    :meth:`draw`.

    Args:
        rect: Button rectangle (x, y, w, h).
        event_type_pressed: Pygame event type to post on *first* press
            (e.g., `pygame.USEREVENT + 1`).
        event_type_released: Pygame event type to post on release *inside*
            the button (e.g., `pygame.USEREVENT + 2`).
        event_data: Optional dict added as event attributes when posting
            pressed/released events.
    """

    def __init__(
        self,
        rect,
        event_type_pressed: pygame.event.EventType,
        event_type_released: pygame.event.EventType,
        event_data=None,
    ):
        self.rect = pygame.Rect(rect)
        self.event_type_pressed = event_type_pressed
        self.event_type_released = event_type_released
        self.event_data = event_data or {}
        self.state = ButtonState.IDLE

        # Track which pointer currently "owns" the press:
        # - None: no active press
        # - 0: mouse
        # - finger_id (int): specific touch finger
        self._active_pointer = None

        self._pressed_time = 0.0
        self.auto_reset_released = True  # one-tick RELEASED state

    def draw(self, surface):
        """Draw the button.

        Must be implemented by subclasses.

        Args:
            surface: Destination surface (usually the screen).
        """
        raise NotImplementedError("draw() must be overridden.")

    def is_pressed(self):
        return self.state == ButtonState.PRESSED

    def is_released(self):
        return self.state == ButtonState.RELEASED

    @staticmethod
    def _screen_size():
        surf = pygame.display.get_surface()
        return surf.get_size() if surf else (0, 0)

    @staticmethod
    def _event_xy(event):
        """
        Return pixel (x, y) for either mouse or touch events.
        - MOUSE*  -> event.pos
        - FINGER* -> (event.x * w, event.y * h)
        """
        if event.type in (
            pygame.MOUSEBUTTONDOWN,
            pygame.MOUSEBUTTONUP,
            pygame.MOUSEMOTION,
        ):
            return event.pos
        if event.type in (pygame.FINGERDOWN, pygame.FINGERUP, pygame.FINGERMOTION):
            w, h = AbstractButton._screen_size()
            return int(event.x * w), int(event.y * h)
        return None

    def is_inside_xy(self, x, y):
        return self.rect.collidepoint(x, y)

    def is_inside(self, event):
        xy = self._event_xy(event)
        return False if xy is None else self.is_inside_xy(*xy)

    def handle_event(self, event):
        # Normalize to a "pointer id":
        # - mouse -> 0
        # - touch -> event.finger_id
        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            pid = 0
        elif event.type in (pygame.FINGERDOWN, pygame.FINGERUP):
            pid = getattr(event, "finger_id", None)
        else:
            return

        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN):
            if self.is_inside(event):
                if self.state != ButtonState.PRESSED:
                    pygame.event.post(
                        pygame.event.Event(self.event_type_pressed, self.event_data)
                    )
                self.state = ButtonState.PRESSED
                self._active_pointer = pid

        elif event.type in (pygame.MOUSEBUTTONUP, pygame.FINGERUP):
            if self.state == ButtonState.PRESSED and self._active_pointer == pid:
                if self.is_inside(event):
                    pygame.event.post(
                        pygame.event.Event(self.event_type_released, self.event_data)
                    )
                    self.state = ButtonState.RELEASED
                else:
                    self.state = ButtonState.IDLE
                self._active_pointer = None

    def update(self, dt: float) -> None:
        """Keeps a running timer while pressed."""
        if self.state == ButtonState.PRESSED:
            self._pressed_time += dt
        else:
            self._pressed_time = 0.0

        # ButtonState.RELEASED lasts exactly one update tick
        if self.state == ButtonState.RELEASED and self.auto_reset_released:
            self.state = ButtonState.IDLE


class ButtonGroup(Container):
    """A positioned container that manages multiple buttons."""

    def __init__(
        self,
        buttons: list[AbstractButton] | None = None,
        position: tuple | None = (0, 0),
        visible: bool = True,
    ):
        super().__init__(x=position[0], y=position[1], is_visible=visible)
        if buttons:
            self.add(*buttons)

    def add_button(self, button: AbstractButton) -> None:
        self.add(button)

    def extend_buttons(self, buttons: list[AbstractButton]) -> None:
        self.add(*buttons)


class Button(AbstractButton):
    """A rectangular Pygame button that can render **text** and an **icon**.

    This class centers or aligns a two-element layout (icon + text) within the
    button rectangle, with configurable ordering, spacing, padding, and anchor.

    Args:
        rect: Button rectangle (x, y, w, h).
        text: Label string to render.
        event_type_pressed: Pygame event type to post on press.
        event_type_released: Pygame event type to post on valid release.
        event_data: Optional dict attached to posted events.
        font: `pygame.font.Font` for the text; if `None`, a default is loaded.
        color: RGB tuple for the text and (by default) icon.
        antialias: Whether to antialias text/icon glyphs. Defaults to False.

        icon: Optional **glyph string** for the icon (e.g., Material Symbols
            codepoint like `"\ue8b8"`). If `None`, only text is drawn.
        icon_size: Optional integer pixel size to render the icon font. If your
            implementation supports this, use it to create/resize `icon_font`.
            (If omitted, the size of `icon_font` or `font` is used.)
        icon_font: Optional font used for the icon. If `None`, falls back to
            a Material Symbols font loaded via `load_font`.
        icon_color: RGB color for the icon; defaults to `color`.
        icon_position: Where the **icon** sits *relative to the text* **when
            `text_position` is not provided**. One of `"left"`, `"right"`,
            `"top"`, `"center"` or `"bottom"`. Default: `"left"`.

        icon_gap: Fallback spacing between icon and text, in pixels. See the
            **Gap precedence** section below.
        text_visible: If False, the label will not be drawn (icon-only mode),
            but `text` can still carry a value for events/logging.
        text_position: Explicit position of the **text** relative to the **icon**.
            One of `"left"`, `"right"`, `"top"`, `"bottom"`. If provided,
            it overrides `icon_position` semantics. If `None`, text defaults to
            the **opposite side** of `icon_position` (for `"center"`, defaults
            to `"bottom"`).
        text_gap: Preferred spacing between text and icon, in pixels. If set,
            it **overrides** `icon_gap`.

        content_align: Anchor for the combined **icon+text** block inside the
            inner (padded) rect. One of `"center"` (default), `"left"`, `"right"`,
            `"top"`, `"bottom"`. Use `"left"` to align multiple buttons so their
            icons/text begin at the same x-position.
        padding: Extra space *inside* `rect` around the content. Can be:
            - `int`: uniform padding on all sides
            - `(x, y)`: horizontal and vertical padding
            - `(l, t, r, b)`: per-side padding
        icon_cell_width: If set, reserves a **fixed width slot** for the icon.
            This keeps icons vertically centered while ensuring all labels start
            at the same x across different buttons, regardless of text width.

    Gap precedence:
        The spacing between the icon and text is determined by:
            `gap = text_gap if text_gap is not None else icon_gap`
        - Set `text_gap` when you want per-button control (it **wins**).
        - Omit `text_gap` to fall back to `icon_gap` (useful as a default).
        - If both are omitted, an internal default is used.

    Rendering:
        The button draws a rounded rectangle border whose color changes while
        pressed, then renders the icon/text Surfaces and blits them according
        to the layout rules above.
    """

    def __init__(
        self,
        rect,
        text,
        event_type_pressed,
        event_type_released,
        event_data=None,
        font=None,
        text_color=None,
        antialias=None,
        *,
        icon: Optional[str] = None,
        icon_size: Optional[int] = 32,
        icon_font: Optional[pygame.font.Font] = None,
        icon_color: Optional[tuple[int, int, int]] = None,
        icon_position: Literal["left", "right", "top", "bottom", "center"] = "left",
        icon_gap: int = 8,
        text_visible: bool = True,
        text_position: Optional[Literal["left", "right", "top", "bottom"]] = None,
        text_gap: Optional[int] = None,
        content_align: Literal["center", "left", "right", "top", "bottom"] = "center",
        padding: Tuple[int, int, int, int] | Tuple[int, int] | int = 0,
        icon_cell_width: Optional[int] = None,  # fixed slot for icon (px)
        bg_color: Optional[tuple[int, int, int]] = None,
        pressed_gradient: Optional[
            tuple[tuple[int, int, int], tuple[int, int, int]]
        ] = (Color.DARK_BLUE.rgb(), Color.BLACK.rgb()),
        gradient_dir: Literal["vertical", "horizontal"] = "vertical",
    ):
        super().__init__(rect, event_type_pressed, event_type_released, event_data)
        if event_data is None:
            self.event_data = {"label": text}
        self._text = text
        self.font = font or load_font(size=32, family=FontFamily.PIXEL_TYPE)
        self.color = text_color or Color.WHITE.rgb()
        self.antialias = bool(antialias) if antialias is not None else False

        self.icon = icon
        self.icon_size = icon_size
        self.icon_font = icon_font or load_font(
            size=self.icon_size,
            family=FontFamily.MATERIAL_SYMBOLS,
        )
        self.icon_color = icon_color or self.color
        self.icon_position = icon_position
        self.icon_gap = max(0, int(icon_gap))

        self.text_visible = text_visible
        self.text_position = text_position
        self.text_gap = None if text_gap is None else max(0, int(text_gap))

        self.content_align = content_align
        self.padding = padding
        self.icon_cell_width = icon_cell_width
        self.bg_color = bg_color
        self.pressed_gradient = pressed_gradient
        self.gradient_dir = gradient_dir

        # cache for gradient surfaces
        self._grad_cache = {
            "key": None,
            "surf": None,
        }

        self._cache = {
            "text_key": None,
            "text_surf": None,
            "icon_key": None,
            "icon_surf": None,
            "layout_key": None,
            "pos": None,  # (icon_x, icon_y, text_x, text_y) absolute coords
            "compose_key": None,
            "composed": None,  # pygame.Surface (size == self.rect.size)
        }

    def _font_fingerprint(self, f: pygame.font.Font) -> tuple:
        return (id(f), f.get_height(), f.get_ascent(), f.get_descent())

    def _compute_border_color(self):
        return (
            Color.BLUE.rgb()
            if self.is_pressed() and self.color == Color.WHITE.rgb()
            else self.color
            if self.is_pressed() and self.color
            else Color.LIGHT_GREY.rgb()
        )

    @staticmethod
    def _normalize_padding(p):
        """Normalize `padding` into a 4-tuple `(left, top, right, bottom)`."""
        if isinstance(p, int):
            return (p, p, p, p)
        if isinstance(p, (tuple, list)):
            if len(p) == 2:
                return (p[0], p[1], p[0], p[1])
            if len(p) == 4:
                return tuple(p)
        return (0, 0, 0, 0)

    def _inner_rect(self) -> pygame.Rect:
        pl, pt, pr, pb = self._normalize_padding(self.padding)
        return pygame.Rect(
            self.rect.x + pl,
            self.rect.y + pt,
            self.rect.w - pl - pr,
            self.rect.h - pt - pb,
        )

    def _gap(self) -> int:
        return self.text_gap if self.text_gap is not None else self.icon_gap

    def _ensure_text_surface(self):
        key = (
            self._text,
            self.color,
            self.antialias,
            self._font_fingerprint(self.font),
        )
        if key != self._cache["text_key"]:
            self._cache["text_surf"] = self.font.render(
                self._text, self.antialias, self.color
            )
            self._cache["text_key"] = key
        return self._cache["text_surf"]

    def _ensure_icon_surface(self):
        if not self.icon:
            # Ensure stale cache cleared
            if self._cache["icon_key"] is not None:
                self._cache["icon_key"] = None
                self._cache["icon_surf"] = None
            return None
        fnt = self.icon_font or self.font
        key = (self.icon, self.icon_color, self.antialias, self._font_fingerprint(fnt))
        if key != self._cache["icon_key"]:
            self._cache["icon_surf"] = fnt.render(
                self.icon, self.antialias, self.icon_color
            )
            self._cache["icon_key"] = key
        return self._cache["icon_surf"]

    def _resolve_text_relative_pos(self) -> str:
        """Return where TEXT goes relative to ICON."""
        if self.icon_position == "center":
            return self.text_position or "bottom"
        opposite = {"left": "right", "right": "left", "top": "bottom", "bottom": "top"}
        return self.text_position or opposite[self.icon_position]

    def _ensure_layout(self, text_surf, icon_surf):
        """Compute (and cache) absolute positions of icon/text top-lefts.

        Returns:
            (icon_x, icon_y, text_x, text_y) — any may be None if not present.
        """
        inner = self._inner_rect()
        gap = self._gap()
        rel = self._resolve_text_relative_pos()

        text_sz = text_surf.get_size() if text_surf is not None else (0, 0)
        icon_sz = icon_surf.get_size() if icon_surf is not None else (0, 0)

        layout_key = (
            self.rect.x,
            self.rect.y,
            self.rect.w,
            self.rect.h,
            inner.x,
            inner.y,
            inner.w,
            inner.h,
            self.content_align,
            self.icon_position,
            rel,
            gap,
            self.icon_cell_width,
            self.text_visible,
            text_sz,
            icon_sz,
        )

        if layout_key == self._cache["layout_key"]:
            return self._cache["pos"]

        # TEXT-ONLY (no icon content)
        if icon_surf is None:
            # Original behavior: center text in the full rect (not inner).
            tr = text_surf.get_rect(center=self.rect.center)
            pos = (None, None, tr.x, tr.y)

        # ICON-ONLY
        elif (
            (not self.text_visible)
            or (self._text == "")
            or (text_surf.get_width() == 0)
        ):
            iw, ih = icon_sz
            ca = self.content_align
            # position within INNER rect (respects padding)
            if ca == "left":
                icon_x = inner.left
                icon_y = inner.centery - ih // 2
            elif ca == "right":
                icon_x = inner.right - iw
                icon_y = inner.centery - ih // 2
            elif ca == "top":
                icon_x = inner.centerx - iw // 2
                icon_y = inner.top
            elif ca == "bottom":
                icon_x = inner.centerx - iw // 2
                icon_y = inner.bottom - ih
            else:
                icon_x = inner.centerx - iw // 2
                icon_y = inner.centery - ih // 2
            pos = (icon_x, icon_y, None, None)

        else:
            # ICON + TEXT
            tw, th = text_sz
            iw, ih = icon_sz
            slot_w = self.icon_cell_width or iw

            if self.icon_position == "center":
                # Build a combined block and anchor via content_align
                if rel in ("left", "right"):
                    total_w = iw + gap + tw
                    total_h = max(ih, th)

                    # horizontal anchor
                    if self.content_align == "left":
                        block_x = inner.left
                    elif self.content_align == "right":
                        block_x = inner.right - total_w
                    else:
                        block_x = inner.left + (inner.w - total_w) // 2

                    # vertical anchor
                    if self.content_align == "top":
                        block_y = inner.top
                    elif self.content_align == "bottom":
                        block_y = inner.bottom - total_h
                    else:
                        block_y = inner.top + (inner.h - total_h) // 2

                    if rel == "right":  # icon then text
                        icon_x = block_x
                        text_x = block_x + iw + gap
                    else:  # text then icon
                        text_x = block_x
                        icon_x = block_x + tw + gap

                    icon_y = block_y + (total_h - ih) // 2
                    text_y = block_y + (total_h - th) // 2

                else:
                    # "top" or "bottom": stack vertically
                    total_h = ih + gap + th
                    total_w = max(iw, tw)

                    # horizontal anchor
                    if self.content_align == "left":
                        block_x = inner.left
                    elif self.content_align == "right":
                        block_x = inner.right - total_w
                    else:
                        block_x = inner.left + (inner.w - total_w) // 2

                    # vertical anchor
                    if self.content_align == "top":
                        block_y = inner.top
                    elif self.content_align == "bottom":
                        block_y = inner.bottom - total_h
                    else:
                        block_y = inner.top + (inner.h - total_h) // 2

                    if rel == "bottom":  # icon then text
                        icon_y = block_y
                        text_y = block_y + ih + gap
                    else:  # text then icon
                        text_y = block_y
                        icon_y = block_y + th + gap

                    icon_x = block_x + (total_w - iw) // 2
                    text_x = block_x + (total_w - tw) // 2

                pos = (icon_x, icon_y, text_x, text_y)

            else:
                # Non-centered icon_position path
                if rel in ("left", "right"):
                    total_w = (
                        (tw + gap + slot_w) if rel == "right" else (slot_w + gap + tw)
                    )
                    if self.content_align == "left":
                        start_x = inner.left
                    elif self.content_align == "right":
                        start_x = inner.right - total_w
                    else:
                        start_x = inner.left + (inner.w - total_w) // 2

                    center_y = inner.centery

                    if rel == "right":  # icon then text
                        icon_x = start_x
                        text_x = start_x + slot_w + gap
                    else:  # text then icon
                        text_x = start_x
                        icon_x = start_x + tw + gap

                    icon_y = center_y - ih // 2
                    text_y = center_y - th // 2

                    pos = (icon_x, icon_y, text_x, text_y)

                else:
                    total_h = (th + gap + ih) if rel == "bottom" else (ih + gap + th)

                    if self.content_align == "top":
                        start_y = inner.top
                    elif self.content_align == "bottom":
                        start_y = inner.bottom - total_h
                    else:
                        start_y = inner.top + (inner.h - total_h) // 2

                    center_x = inner.centerx

                    if rel == "bottom":  # icon then text
                        icon_y = start_y
                        text_y = start_y + ih + gap
                    else:  # text then icon
                        text_y = start_y
                        icon_y = start_y + th + gap

                    icon_x = center_x - iw // 2
                    text_x = center_x - tw // 2

                    pos = (icon_x, icon_y, text_x, text_y)

        self._cache["layout_key"] = layout_key
        self._cache["pos"] = pos
        return pos

    def _ensure_composite(self, text_surf, icon_surf, pos):
        """Create or reuse a composed Surface with border + content."""
        border_color = self._compute_border_color()
        icon_x, icon_y, text_x, text_y = pos

        compose_key = (
            tuple(self.rect.size),
            border_color,
            self.icon_position,
            self.text_position,
            self._gap(),
            self.content_align,
            self.padding,
            self.icon_cell_width,
            self.text_visible,
            (
                self._text,
                self.color,
                self.antialias,
                text_surf.get_size() if text_surf else (0, 0),
            ),
            (
                self.icon,
                self.icon_color,
                self.antialias,
                icon_surf.get_size() if icon_surf else (0, 0),
            ),
            pos,  # includes absolute positions; recomposite if these change
        )

        if (
            compose_key == self._cache["compose_key"]
            and self._cache["composed"] is not None
        ):
            return self._cache["composed"]

        composed = pygame.Surface(self.rect.size, pygame.SRCALPHA)

        # Background fill (pressed = gradient)
        if self.is_pressed() and self.pressed_gradient:
            c1, c2 = self.pressed_gradient
            horizontal = self.gradient_dir == "horizontal"
            grad = self._get_gradient_surface(
                self.rect.size, c1, c2, horizontal, radius=4
            )
            composed.blit(grad, (0, 0))
        elif self.bg_color is not None:
            pygame.draw.rect(
                composed, self.bg_color, composed.get_rect(), border_radius=4
            )

        # Border
        pygame.draw.rect(
            composed, border_color, composed.get_rect(), width=2, border_radius=4
        )

        # Content (convert absolute positions to local coords in composed surface)
        if icon_surf is not None and icon_x is not None:
            composed.blit(icon_surf, (icon_x - self.rect.x, icon_y - self.rect.y))
        if text_surf is not None and text_x is not None:
            composed.blit(text_surf, (text_x - self.rect.x, text_y - self.rect.y))

        self._cache["compose_key"] = compose_key
        self._cache["composed"] = composed
        return composed

    @staticmethod
    def _lerp(a: int, b: int, t: float) -> int:
        return a + int((b - a) * t)

    @staticmethod
    def _rounded_mask(size: Tuple[int, int], radius: int = 4) -> pygame.Surface:
        w, h = size
        m = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(m, (255, 255, 255, 255), m.get_rect(), border_radius=radius)
        return m

    def _get_gradient_surface(
        self,
        size: Tuple[int, int],
        c1: Tuple[int, int, int],
        c2: Tuple[int, int, int],
        horizontal: bool,
        radius: int = 4,
    ) -> pygame.Surface:
        key = (size, c1, c2, horizontal, radius)
        if key == self._grad_cache["key"] and self._grad_cache["surf"] is not None:
            return self._grad_cache["surf"]

        w, h = size
        grad = pygame.Surface((w, h), pygame.SRCALPHA)

        if horizontal:
            # one vertical strip per x
            for x in range(w):
                t = x / max(1, w - 1)
                r = self._lerp(c1[0], c2[0], t)
                g = self._lerp(c1[1], c2[1], t)
                b = self._lerp(c1[2], c2[2], t)
                pygame.draw.line(grad, (r, g, b), (x, 0), (x, h - 1))
        else:
            # one horizontal strip per y
            for y in range(h):
                t = y / max(1, h - 1)
                r = self._lerp(c1[0], c2[0], t)
                g = self._lerp(c1[1], c2[1], t)
                b = self._lerp(c1[2], c2[2], t)
                pygame.draw.line(grad, (r, g, b), (0, y), (w - 1, y))

        if radius and radius > 0:
            mask = self._rounded_mask((w, h), radius)
            grad.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)

        self._grad_cache["key"] = key
        self._grad_cache["surf"] = grad
        return grad

    def draw(self, surface):
        """Render the button onto `surface`, using caches where possible."""

        text_surf = self._ensure_text_surface()
        icon_surf = self._ensure_icon_surface()

        pos = self._ensure_layout(text_surf, icon_surf)

        composed = self._ensure_composite(text_surf, icon_surf, pos)
        surface.blit(composed, self.rect)

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, value):
        self._text = value
