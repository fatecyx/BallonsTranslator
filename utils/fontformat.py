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
        
    # Translate English name to display (Chinese) name if mapped
    display_name = family_name
    if hasattr(shared, 'FONT_DISPLAY_NAME_MAP'):
        display_name = shared.FONT_DISPLAY_NAME_MAP.get(family_name, family_name)
        
    # Get internal English name if mapped
    internal_name = family_name
    if hasattr(shared, 'FONT_INTERNAL_NAME_MAP'):
        internal_name = shared.FONT_INTERNAL_NAME_MAP.get(family_name, family_name)
        
    # First priority: check if either display name, family name, or internal name exists directly in registered families.
    # If the family name itself is recognized by QFontDatabase (e.g. "思源宋体 Heavy"), we MUST set the family directly
    # to this GDI family name, because GDI registers it as a separate family, not as a style of "思源宋体".
    target_family = None
    if shared.FONT_FAMILIES:
        if display_name in shared.FONT_FAMILIES:
            target_family = display_name
        elif family_name in shared.FONT_FAMILIES:
            target_family = family_name
        elif internal_name in shared.FONT_FAMILIES:
            target_family = internal_name
            
    if target_family:
        font.setFamily(target_family)
        # Also set style/weight if mapped in FONT_TYPOGRAPHIC_MAP
        if hasattr(shared, 'FONT_TYPOGRAPHIC_MAP') and shared.FONT_TYPOGRAPHIC_MAP:
            gdi_key = target_family
            if gdi_key not in shared.FONT_TYPOGRAPHIC_MAP:
                for k in (family_name, display_name, internal_name):
                    if k in shared.FONT_TYPOGRAPHIC_MAP:
                        gdi_key = k
                        break
            if gdi_key in shared.FONT_TYPOGRAPHIC_MAP:
                tf, ts = shared.FONT_TYPOGRAPHIC_MAP[gdi_key]
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
                if style_lower == "b":
                    font.setWeight(700)
                elif style_lower == "m":
                    font.setWeight(500)
                elif style_lower == "r":
                    font.setWeight(400)
        return
        
    # Second priority: check FONT_TYPOGRAPHIC_MAP for direct font file typographic mappings
    if hasattr(shared, 'FONT_TYPOGRAPHIC_MAP') and shared.FONT_TYPOGRAPHIC_MAP:
        if family_name in shared.FONT_TYPOGRAPHIC_MAP and (not shared.FONT_FAMILIES or family_name in shared.FONT_FAMILIES):
            tf, ts = shared.FONT_TYPOGRAPHIC_MAP[family_name]
            
            # If tf is not in families, but its internal English name is in families, use the English one
            if shared.FONT_FAMILIES and tf not in shared.FONT_FAMILIES:
                internal_tf = shared.FONT_INTERNAL_NAME_MAP.get(tf, tf) if hasattr(shared, 'FONT_INTERNAL_NAME_MAP') else tf
                if internal_tf in shared.FONT_FAMILIES:
                    tf = internal_tf
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
        
    # If not directly registered, try prefix matching on names (including internal_name)
    if shared.FONT_FAMILIES:
        for name_to_try in (display_name, family_name, internal_name):
            # Find the longest registered family name that is a prefix of family_name
            longest_prefix = ""
            matched_family = ""
            for family in shared.FONT_FAMILIES:
                aliases = [family]
                if hasattr(shared, 'FONT_DISPLAY_NAME_MAP') and family in shared.FONT_DISPLAY_NAME_MAP:
                    aliases.append(shared.FONT_DISPLAY_NAME_MAP[family])
                if hasattr(shared, 'FONT_INTERNAL_NAME_MAP') and family in shared.FONT_INTERNAL_NAME_MAP:
                    aliases.append(shared.FONT_INTERNAL_NAME_MAP[family])
                
                for alias in aliases:
                    if name_to_try.startswith(alias) and len(name_to_try) > len(alias):
                        sep = name_to_try[len(alias)]
                        if sep in (" ", "-", "_"):
                            if len(alias) > len(longest_prefix):
                                longest_prefix = alias
                                matched_family = family
            
            if longest_prefix:
                style_name = name_to_try[len(longest_prefix) + 1:]
                font.setFamily(matched_family)
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


def decompose_font_name(font_name: str) -> tuple:
    if not font_name:
        return "", ""
        
    # 1. Check FONT_TYPOGRAPHIC_MAP first
    if hasattr(shared, 'FONT_TYPOGRAPHIC_MAP') and shared.FONT_TYPOGRAPHIC_MAP:
        if font_name in shared.FONT_TYPOGRAPHIC_MAP:
            return shared.FONT_TYPOGRAPHIC_MAP[font_name]
            
    # 2. Check FONT_DISPLAY_NAME_MAP and FONT_INTERNAL_NAME_MAP to resolve aliases
    display_name = font_name
    if hasattr(shared, 'FONT_DISPLAY_NAME_MAP') and shared.FONT_DISPLAY_NAME_MAP:
        display_name = shared.FONT_DISPLAY_NAME_MAP.get(font_name, font_name)
        if display_name in shared.FONT_TYPOGRAPHIC_MAP:
            return shared.FONT_TYPOGRAPHIC_MAP[display_name]
            
    if hasattr(shared, 'FONT_INTERNAL_NAME_MAP') and shared.FONT_INTERNAL_NAME_MAP:
        internal_name = shared.FONT_INTERNAL_NAME_MAP.get(font_name, font_name)
        if internal_name in shared.FONT_TYPOGRAPHIC_MAP:
            return shared.FONT_TYPOGRAPHIC_MAP[internal_name]
            
    # 2.5 Check if font_name itself is already a valid family name in FONT_FAMILIES
    if shared.FONT_FAMILIES:
        for name in (display_name, font_name, internal_name if 'internal_name' in locals() else font_name):
            if name in shared.FONT_FAMILIES:
                display_family = shared.FONT_DISPLAY_NAME_MAP.get(name, name) if hasattr(shared, 'FONT_DISPLAY_NAME_MAP') else name
                return display_family, "Regular"
                
    # 3. Fallback to longest prefix matching with separators
    if shared.FONT_FAMILIES:
        for name_to_try in (display_name, font_name):
            longest_prefix = ""
            matched_family = ""
            for family in shared.FONT_FAMILIES:
                aliases = [family]
                if hasattr(shared, 'FONT_DISPLAY_NAME_MAP') and family in shared.FONT_DISPLAY_NAME_MAP:
                    aliases.append(shared.FONT_DISPLAY_NAME_MAP[family])
                if hasattr(shared, 'FONT_INTERNAL_NAME_MAP') and family in shared.FONT_INTERNAL_NAME_MAP:
                    aliases.append(shared.FONT_INTERNAL_NAME_MAP[family])
                    
                for alias in aliases:
                    if name_to_try.startswith(alias) and len(name_to_try) > len(alias):
                        sep = name_to_try[len(alias)]
                        if sep in (" ", "-", "_"):
                            if len(alias) > len(longest_prefix):
                                longest_prefix = alias
                                matched_family = family
                                
            if longest_prefix:
                style_name = name_to_try[len(longest_prefix) + 1:]
                # Prefer returning the display name of the matched family prefix
                display_prefix = shared.FONT_DISPLAY_NAME_MAP.get(matched_family, matched_family) if hasattr(shared, 'FONT_DISPLAY_NAME_MAP') else longest_prefix
                return display_prefix, style_name
                
    # 4. Default fallback: family is the display name of the font, style is Regular
    display_family = shared.FONT_DISPLAY_NAME_MAP.get(font_name, font_name) if hasattr(shared, 'FONT_DISPLAY_NAME_MAP') else font_name
    return display_family, "Regular"


def find_gdi_font_name(family: str, style: str, weight: int = -1) -> str:
    # 0. If family is already in FONT_TYPOGRAPHIC_MAP and no style change is requested,
    # return it directly.
    if not style and hasattr(shared, 'FONT_TYPOGRAPHIC_MAP') and shared.FONT_TYPOGRAPHIC_MAP:
        display_name = shared.FONT_DISPLAY_NAME_MAP.get(family, family) if hasattr(shared, 'FONT_DISPLAY_NAME_MAP') else family
        internal_name = shared.FONT_INTERNAL_NAME_MAP.get(family, family) if hasattr(shared, 'FONT_INTERNAL_NAME_MAP') else family
        for k in (family, display_name, internal_name):
            if k in shared.FONT_TYPOGRAPHIC_MAP:
                return k

    # Decompose family to get the typographic family name
    typo_family, typo_style = decompose_font_name(family)
    
    # Get internal English name of typographic family
    internal_typo_family = shared.FONT_INTERNAL_NAME_MAP.get(typo_family, typo_family) if hasattr(shared, 'FONT_INTERNAL_NAME_MAP') else typo_family
    
    # 1. Look in FONT_TYPOGRAPHIC_MAP
    if hasattr(shared, 'FONT_TYPOGRAPHIC_MAP') and shared.FONT_TYPOGRAPHIC_MAP:
        if style:
            for gdi_name, (tf, ts) in shared.FONT_TYPOGRAPHIC_MAP.items():
                internal_tf = shared.FONT_INTERNAL_NAME_MAP.get(tf, tf) if hasattr(shared, 'FONT_INTERNAL_NAME_MAP') else tf
                if internal_tf == internal_typo_family and ts == style:
                    return gdi_name
                
        # Second pass: if style is empty, try matching by tf and weight
        if (not style or style.lower() in ("regular", "normal")) and weight != -1:
            for gdi_name, (tf, ts) in shared.FONT_TYPOGRAPHIC_MAP.items():
                internal_tf = shared.FONT_INTERNAL_NAME_MAP.get(tf, tf) if hasattr(shared, 'FONT_INTERNAL_NAME_MAP') else tf
                if internal_tf == internal_typo_family:
                    style_lower = ts.lower()
                    cand_weight = 400
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
                            cand_weight = val
                            break
                    if style_lower == "b":
                        cand_weight = 700
                    elif style_lower == "m":
                        cand_weight = 500
                    elif style_lower == "r":
                        cand_weight = 400
                        
                    if cand_weight == weight:
                        return gdi_name
                
    # 2. If not found in FONT_TYPOGRAPHIC_MAP, try standard combining (with separator)
    if style and style.lower() not in ("regular", "normal"):
        return f"{family} {style}"
    return family



def create_qfont(family_name: str, size: float = -1, weight: int = -1, italic: bool = False):
    from qtpy.QtGui import QFont
    font = QFont()
    apply_font_family(font, family_name)
    if size > 0:
        font.setPointSizeF(size)
        
    applied_weight = font.weight()
    normal_weights = (50, 400)
    
    # Check if typographic weight defines it
    has_typo_weight = False
    if hasattr(shared, 'FONT_TYPOGRAPHIC_MAP') and shared.FONT_TYPOGRAPHIC_MAP:
        display_name = shared.FONT_DISPLAY_NAME_MAP.get(family_name, family_name) if hasattr(shared, 'FONT_DISPLAY_NAME_MAP') else family_name
        internal_name = shared.FONT_INTERNAL_NAME_MAP.get(family_name, family_name) if hasattr(shared, 'FONT_INTERNAL_NAME_MAP') else family_name
        for k in (family_name, display_name, internal_name):
            if k in shared.FONT_TYPOGRAPHIC_MAP:
                has_typo_weight = True
                break
                
    if weight != -1 and not has_typo_weight:
        if applied_weight not in normal_weights and weight in normal_weights:
            # Keep the applied weight from the font family style!
            pass
        else:
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