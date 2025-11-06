import pygame
from pygame.sprite import DirtySprite

from ...colors import Color


class Label(DirtySprite):
    def __init__(
        self,
        text,
        font: pygame.font.Font = None,
        color: tuple[int, int, int] = Color.WHITE.rgb(),
        pos: tuple[int, int] = (0, 0),
        center: bool = True,
        antialias: bool = True,
    ):
        super().__init__()
        self._text = None
        self.font = font
        self.color = color
        self.pos = pos
        self.center = center
        self.antialias = antialias
        self.set_text(text)
        self.dirty = 1  # ensures initial draw
        self.visible = 1  # sprite will be drawn

    @property
    def text(self):
        return self._text

    def set_text(self, text: str):
        if text != self._text:
            self._text = text
            self.image = self.font.render(text, self.antialias, self.color)
            self.image = self.image.convert_alpha()

            if self.center:
                self.rect = self.image.get_rect(center=self.pos)
            else:
                self.rect = self.image.get_rect(topleft=self.pos)
            self.dirty = 1
