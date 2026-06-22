from typing import Union
import enum
import re
import copy

import numpy as np

from . import shared
from .structures import Tuple, Union, List, Dict, Config, field, nested_dataclass


def pt2px(pt, to_int=False) -> float:
    if to_int:
        return int(round(pt * shared.LDPI / 72.))
    else:
        return pt * shared.LDPI / 72.

def px2pt(px) -> float:
    return px / shared.LDPI * 72.


class LineSpacingType(enum.IntEnum):
    Proportional = 0
    Distance = 1


class TextAlignment(enum.IntEnum):
    Left = 0
    Center = 1
    Right = 2


fontweight_qt5_to_qt6 = {0: 100, 12: 200, 25: 300, 50: 400, 57: 500, 63: 600, 75: 700, 81: 800, 87: 900}
fontweight_qt6_to_qt5 = {100: 0, 200: 12, 300: 25, 400: 50, 500: 57, 600: 63, 700: 75, 800: 81, 900: 87}

fontweight_pattern = re.compile(r'font-weight:(\d+)', re.DOTALL)

def fix_fontweight_qt(weight: Union[str, int]):

    def _fix_html_fntweight(matched):
        weight = int(matched.group(1))
        return f'font-weight:{fix_fontweight_qt(weight)}'

    if weight is None:
        return None
    if isinstance(weight, int):
        if shared.FLAG_QT6 and weight < 100:
            if weight in fontweight_qt5_to_qt6:
                weight = fontweight_qt5_to_qt6[weight]
        if not shared.FLAG_QT6 and weight >= 100:
            if weight in fontweight_qt6_to_qt5:
                weight = fontweight_qt6_to_qt5[weight]
    if isinstance(weight, str):
        weight = fontweight_pattern.sub(lambda matched: _fix_html_fntweight(matched), weight)
    return weight


def apply_font_family(font, family_name: str):
    if not family_name:
        font.setFamily(family_name)
        return
        
    # First priority: check FONT_TYPOGRAPHIC_MAP for direct font file typographic mappings
    if hasattr(shared, 'FONT_TYPOGRAPHIC_MAP') and shared.FONT_TYPOGRAPHIC_MAP:
        if family_name in shared.FONT_TYPOGRAPHIC_MAP:
            tf, ts = shared.FONT_TYPOGRAPHIC_MAP[family_name]
            font.setFamily(tf)
            font.setStyleName(ts)
            
            # Map style name keywords to standard Qt weights to ensure correct weight rendering on Windows/DirectWrite
            style_lower = ts.lower()
            weight_mapping = {
                "thin": 100,
                "extralight": 200,
                "light": 300,
                "regular": 400,
                "normal": 400,
                "medium": 500,
                "semibold": 600,
                "bold": 700,
                "extrabold": 800,
                "heavy": 900,
                "black": 950
            }
            for kw, val in weight_mapping.items():
                if kw in style_lower:
                    font.setWeight(val)
                    break
            # Also handle single-letter styles like B, M, R from XinLanYuan
            if style_lower == "b":
                font.setWeight(700) # Bold
            elif style_lower == "m":
                font.setWeight(500) # Medium
            elif style_lower == "r":
                font.setWeight(400) # Regular
            return
    
    # Translate English name to display (Chinese) name if mapped
    display_name = family_name
    if hasattr(shared, 'FONT_DISPLAY_NAME_MAP'):
        display_name = shared.FONT_DISPLAY_NAME_MAP.get(family_name, family_name)
        
    # Check if either the display name or the family name exists directly in registered families
    target_family = None
    if shared.FONT_FAMILIES:
        if display_name in shared.FONT_FAMILIES:
            target_family = display_name
        elif family_name in shared.FONT_FAMILIES:
            target_family = family_name
            
    if target_family:
        font.setFamily(target_family)
        return
        
    # If not directly registered, try prefix matching on both names
    if shared.FONT_FAMILIES:
        for name_to_try in (display_name, family_name):
            # Find the longest registered family name that is a prefix of family_name
            longest_prefix = ""
            for family in shared.FONT_FAMILIES:
                if name_to_try.startswith(family) and len(name_to_try) > len(family):
                    sep = name_to_try[len(family)]
                    if sep in (" ", "-", "_"):
                        if len(family) > len(longest_prefix):
                            longest_prefix = family
            
            if longest_prefix:
                style_name = name_to_try[len(longest_prefix) + 1:]
                font.setFamily(longest_prefix)
                font.setStyleName(style_name)
                
                # Map style name keywords to standard Qt weights to ensure correct weight rendering on Windows/DirectWrite
                style_lower = style_name.lower()
                weight_mapping = {
                    "thin": 100,
                    "extralight": 200,
                    "light": 300,
                    "regular": 400,
                    "normal": 400,
                    "medium": 500,
                    "semibold": 600,
                    "bold": 700,
                    "extrabold": 800,
                    "heavy": 900,
                    "black": 950
                }
                for kw, val in weight_mapping.items():
                    if kw in style_lower:
                        font.setWeight(val)
                        break
                return
    font.setFamily(family_name)


def create_qfont(family_name: str, size: float = -1, weight: int = -1, italic: bool = False):
    from qtpy.QtGui import QFont
    font = QFont()
    apply_font_family(font, family_name)
    if size > 0:
        font.setPointSizeF(size)
    if weight != -1:
        font.setWeight(weight)
    font.setItalic(italic)
    return font


@nested_dataclass
class FontFormat(Config):

    font_family: str = shared.DEFAULT_FONT_FAMILY # to always apply shared.DEFAULT_FONT_FAMILY
    font_size: float = 24
    stroke_width: float = 0.
    frgb: List = field(default_factory=lambda: [0, 0, 0])
    srgb: List = field(default_factory=lambda: [0, 0, 0])
    bold: bool = False
    underline: bool = False
    italic: bool = False
    alignment: int = 0
    vertical: bool = False
    font_weight: int = None
    line_spacing: float = 1.2
    letter_spacing: float = 1.15
    opacity: float = 1.
    shadow_radius: float = 0.
    shadow_strength: float = 1.
    shadow_color: List = field(default_factory=lambda: [0, 0, 0])
    shadow_offset: List = field(default_factory=lambda: [0., 0.])
    gradient_enabled: bool = False
    gradient_start_color: List = field(default_factory=lambda: [0, 0, 0])
    gradient_end_color: List = field(default_factory=lambda: [255, 255, 255])
    gradient_angle: float = 0.
    gradient_size: float = 1.0
    _style_name: str = ''
    line_spacing_type: int = LineSpacingType.Proportional

    deprecated_attributes: dict = field(default_factory = lambda: dict())

    @property
    def size_pt(self):
        return px2pt(self.font_size)

    def __post_init__(self):
        da = self.deprecated_attributes
        if len(da) > 0:
            if 'size' in da:
                self.font_size = pt2px(da['size'])
            if 'weight' in da:
                self.font_weight = da['weight']
            if 'family' in da:
                self.font_family = da['family']

        self.font_weight = fix_fontweight_qt(self.font_weight)
        self.deprecated_attributes = {}

    def deepcopy(self):
        fmt_copyed: FontFormat = None
        fmt_copyed = copy.deepcopy(self)
        return fmt_copyed

    def merge(self, target: Config, compare: bool = False):
        if id(self) == id(target):
            return set()
        tgt_keys = target.annotations_set()
        updated_keys = set()
        for key in tgt_keys:
            if not hasattr(self, key):
                continue
            if compare:
                if key != '_style_name':
                    if isinstance(target[key], np.ndarray):
                        is_diff = np.any(self[key] != target[key])
                    else:
                        is_diff = self[key] != target[key]
                    if is_diff:
                        self.update(key, copy.deepcopy(target[key]))
                        updated_keys.add(key)
            else:
                self.update(key, copy.deepcopy(target[key]))
        return updated_keys

    def foreground_color(self):
        return [int(round(x)) for x in self.frgb]
    
    def stroke_color(self):
        return [int(round(x)) for x in self.srgb]