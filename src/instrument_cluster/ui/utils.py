from __future__ import annotations

from enum import Enum
from importlib.resources import as_file, files

import pygame

_font_cache: dict[tuple[FontFamily, int], pygame.font.Font] = {}


def load_font(size: int, family: FontFamily) -> pygame.font.Font:
    key = (family, size)
    if key in _font_cache:
        return _font_cache[key]

    font_res = files("instrument_cluster").joinpath(family.relpath)
    with as_file(font_res) as font_path:
        font = pygame.font.Font(str(font_path), size)

    _font_cache[key] = font
    return font


class FontFamily(Enum):
    PIXEL_TYPE = ("pixeltype", "pixeltype")
    MATERIAL_SYMBOLS = ("material_symbols", "material-symbols-rounded-latin-300-normal")
    D_DIN_EXP_BOLD = ("d-din", "D-DINExp-Bold")
    D_DIN_EXP = ("d-din", "D-DINExp")

    def __init__(self, subdir: str, basename: str):
        self.subdir = subdir  # folder under assets/fonts
        self.basename = basename  # filename without .ttf

    @property
    def relpath(self) -> str:
        return f"assets/fonts/{self.subdir}/{self.basename}.ttf"
