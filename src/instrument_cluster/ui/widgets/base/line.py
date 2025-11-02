import pygame

from ...colors import Color


class Line:
    def __init__(
        self,
        start_pos=(0, 90),
        length=1024,
        color=Color.BLUE.rgb(),
        width=2,
        horizontal=True,
    ):
        """
        A simple widget that draws a straight line.

        Args:
            start_pos (tuple): (x, y) starting position of the line.
            length (int): Length of the line in pixels.
            color (tuple): RGB color of the line.
            width (int): Thickness of the line in pixels.
            horizontal (bool): True for horizontal, False for vertical.
        """
        self.start_pos = start_pos
        self.length = length
        self.color = color
        self.width = width
        self.horizontal = horizontal

    def draw(self, surface):
        """Draw the line on the given surface."""
        x, y = self.start_pos
        if self.horizontal:
            end_pos = (x + self.length, y)
        else:
            end_pos = (x, y + self.length)

        pygame.draw.line(surface, self.color, self.start_pos, end_pos, self.width)
