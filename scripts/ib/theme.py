#!/usr/bin/env python3
"""
ib theme — Material 3 Theme & Component Matrix Auditor

Inspects and simulates Material 3 / MaterialKolor dynamic palettes,
computes HCT color science values, audits component-to-token mappings,
and prints rich ANSI Truecolor swatch grids in the terminal.
"""

import sys
import os
import argparse
import subprocess
import re

try:
    from materialyoucolor.hct import Hct
    from materialyoucolor.dynamiccolor.material_dynamic_colors import MaterialDynamicColors as MDC
    from materialyoucolor.scheme.scheme_vibrant import SchemeVibrant
    from materialyoucolor.scheme.scheme_expressive import SchemeExpressive
    from materialyoucolor.scheme.scheme_tonal_spot import SchemeTonalSpot
    from materialyoucolor.scheme.scheme_neutral import SchemeNeutral
    from materialyoucolor.scheme.scheme_monochrome import SchemeMonochrome
    from materialyoucolor.scheme.scheme_fidelity import SchemeFidelity
    from materialyoucolor.scheme.scheme_content import SchemeContent
    from materialyoucolor.scheme.scheme_rainbow import SchemeRainbow
    from materialyoucolor.scheme.scheme_fruit_salad import SchemeFruitSalad
except ImportError:
    print("Error: materialyoucolor package not found. Run: pip install materialyoucolor", file=sys.stderr)
    sys.exit(1)


STYLE_MAP = {
    "vibrant": SchemeVibrant,
    "expressive": SchemeExpressive,
    "tonal_spot": SchemeTonalSpot,
    "tonalspot": SchemeTonalSpot,
    "neutral": SchemeNeutral,
    "monochrome": SchemeMonochrome,
    "fidelity": SchemeFidelity,
    "content": SchemeContent,
    "rainbow": SchemeRainbow,
    "fruit_salad": SchemeFruitSalad,
    "fruitsalad": SchemeFruitSalad,
    "eassy": SchemeVibrant,  # Base scheme for eassy mode
}


def hex_to_argb(hex_str: str) -> int:
    s = hex_str.strip().lstrip("#")
    if len(s) == 3:
        s = "".join([c * 2 for c in s])
    val = int(s, 16)
    return 0xFF000000 | val


def argb_to_hex(val: int) -> str:
    return f"#{val & 0xFFFFFF:06X}"


def get_hct_info(argb: int) -> tuple[float, float, float]:
    h = Hct.from_int(argb)
    return h.hue, h.chroma, h.tone


def ansi_color_box(bg_argb: int, fg_argb: int, text: str, width: int = 0) -> str:
    r_bg = (bg_argb >> 16) & 0xFF
    g_bg = (bg_argb >> 8) & 0xFF
    b_bg = bg_argb & 0xFF
    r_fg = (fg_argb >> 16) & 0xFF
    g_fg = (fg_argb >> 8) & 0xFF
    b_fg = fg_argb & 0xFF

    content = f" {text} "
    if width > len(content):
        content = content.ljust(width)

    return f"\033[48;2;{r_bg};{g_bg};{b_bg}m\033[38;2;{r_fg};{g_fg};{b_fg}m{content}\033[0m"


def ansi_swatch(argb: int, label: str = "") -> str:
    r = (argb >> 16) & 0xFF
    g = (argb >> 8) & 0xFF
    b = argb & 0xFF
    hex_s = argb_to_hex(argb)
    hct = Hct.from_int(argb)
    # determine best text contrast for the swatch block
    fg = "\033[38;2;0;0;0m" if hct.tone > 55 else "\033[38;2;255;255;255m"
    return f"\033[48;2;{r};{g};{b}m{fg} {hex_s} (T-{int(hct.tone):02d}) \033[0m {label}"


def detect_system_seed() -> tuple[str, bool]:
    """Detects current GTK theme accent and dark mode."""
    theme_name = ""
    is_dark = False
    try:
        out = subprocess.check_output(["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"]).decode().strip().strip("'\"")
        theme_name = out
    except Exception:
        pass

    try:
        out = subprocess.check_output(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"]).decode().strip().strip("'\"")
        is_dark = "dark" in out.lower()
    except Exception:
        pass

    # Read CSS if available
    accent_hex = "#E1AA09"  # default amber/yellow fallback
    if theme_name:
        paths = [
            os.path.expanduser(f"~/.config/gtk-4.0/gtk.css"),
            f"/usr/share/themes/{theme_name}/gtk-4.0/gtk.css",
            f"/usr/share/themes/{theme_name}/gtk-3.0/gtk.css",
        ]
        for p in paths:
            if os.path.isfile(p):
                try:
                    with open(p) as f:
                        m = re.search(r'@define-color\s+(?:accent_color|accent_bg_color|theme_selected_bg_color)\s+#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b', f.read())
                        if m:
                            accent_hex = f"#{m.group(1)}"
                            break
                except Exception:
                    pass

    return accent_hex, is_dark


class ThemeMatrix:
    def __init__(self, seed_hex: str, is_dark: bool, style: str, contrast: float = 0.0):
        self.seed_hex = seed_hex
        self.seed_argb = hex_to_argb(seed_hex)
        self.is_dark = is_dark
        self.style = style.lower()
        self.contrast = contrast

        self.hct_seed = Hct.from_int(self.seed_argb)
        scheme_cls = STYLE_MAP.get(self.style, SchemeVibrant)
        self.scheme = scheme_cls(self.hct_seed, self.is_dark, self.contrast)

        self._compute_roles()

    def _compute_roles(self):
        s = self.scheme
        self.primary = MDC.primary.get_argb(s)
        self.on_primary = MDC.onPrimary.get_argb(s)
        self.primary_container = MDC.primaryContainer.get_argb(s)
        self.on_primary_container = MDC.onPrimaryContainer.get_argb(s)

        self.secondary = MDC.secondary.get_argb(s)
        self.on_secondary = MDC.onSecondary.get_argb(s)
        self.secondary_container = MDC.secondaryContainer.get_argb(s)
        self.on_secondary_container = MDC.onSecondaryContainer.get_argb(s)

        self.tertiary = MDC.tertiary.get_argb(s)
        self.on_tertiary = MDC.onTertiary.get_argb(s)
        self.tertiary_container = MDC.tertiaryContainer.get_argb(s)
        self.on_tertiary_container = MDC.onTertiaryContainer.get_argb(s)

        self.error = MDC.error.get_argb(s)
        self.on_error = MDC.onError.get_argb(s)
        self.error_container = MDC.errorContainer.get_argb(s)
        self.on_error_container = MDC.onErrorContainer.get_argb(s)

        # Surfaces
        self.surface = MDC.surface.get_argb(s)
        self.on_surface = MDC.onSurface.get_argb(s)
        self.on_surface_variant = MDC.onSurfaceVariant.get_argb(s)
        self.surface_dim = MDC.surfaceDim.get_argb(s)
        self.surface_bright = MDC.surfaceBright.get_argb(s)

        self.surface_container_lowest = MDC.surfaceContainerLowest.get_argb(s)
        self.surface_container_low = MDC.surfaceContainerLow.get_argb(s)
        self.surface_container = MDC.surfaceContainer.get_argb(s)
        self.surface_container_high = MDC.surfaceContainerHigh.get_argb(s)
        self.surface_container_highest = MDC.surfaceContainerHighest.get_argb(s)

        # Inverse & Outlines
        self.inverse_surface = MDC.inverseSurface.get_argb(s)
        self.inverse_on_surface = MDC.inverseOnSurface.get_argb(s)
        self.inverse_primary = MDC.inversePrimary.get_argb(s)
        self.outline = MDC.outline.get_argb(s)
        self.outline_variant = MDC.outlineVariant.get_argb(s)

        # Apply "eassy" mode calibration if active
        if self.style == "eassy":
            if self.is_dark:
                self.surface_container_lowest = 0xFF151C19  # Deep charcoal canvas (Tone 10)
                self.surface_container_low = 0xFF2B3A35     # Lifted sidebar (Tone 20, ΔT = +10)
                self.surface_container = 0xFF26332E         # Breadcrumb / Cards (Tone 18)
                self.surface_container_high = 0xFF202B27    # Headerbar (Tone 16)
                self.surface_container_highest = 0xFF34453E # Popovers / Menus (Tone 26)
            else:
                self.surface_container_lowest = 0xFFFFFFFF  # Pure crisp white canvas
                self.surface_container_low = 0xFFEAE9DA     # Shaded creamy sidebar (ΔT = 8)
                self.surface_container = 0xFFF0EFE2         # Cards / Pills
                self.surface_container_high = 0xFFF6F5EA    # Headerbar

    def print_overview(self):
        hue, chroma, tone = self.hct_seed.hue, self.hct_seed.chroma, self.hct_seed.tone
        mode_str = "🌙 DARK MODE" if self.is_dark else "☀️ LIGHT MODE"
        style_title = self.style.upper()

        print(f"\n\033[1;36m========================================================================================\033[0m")
        print(f"\033[1m  MATERIAL 3 THEME & COMPONENT AUDIT MATRIX\033[0m — \033[33m{mode_str}\033[0m | Style: \033[32m{style_title}\033[0m")
        print(f"  Seed: \033[1m{self.seed_hex}\033[0m (Hue: {hue:.1f}°, Chroma: {chroma:.1f}, Tone: {tone:.1f}) | Contrast: {self.contrast}")
        print(f"\033[1;36m========================================================================================\033[0m\n")

        print("\033[1;4m1. CORE COLOR ROLES & ACCENT CONTAINERS\033[0m")
        print(f"  Primary:          {ansi_color_box(self.primary, self.on_primary, 'Primary (Main Accent)', 28)}  On-Primary: {argb_to_hex(self.on_primary)}")
        print(f"  Primary Cont:     {ansi_color_box(self.primary_container, self.on_primary_container, 'Primary Container', 28)}  On-Primary Cont: {argb_to_hex(self.on_primary_container)}")
        print(f"  Secondary:        {ansi_color_box(self.secondary, self.on_secondary, 'Secondary Accent', 28)}  On-Secondary: {argb_to_hex(self.on_secondary)}")
        print(f"  Secondary Cont:   {ansi_color_box(self.secondary_container, self.on_secondary_container, 'Secondary Container', 28)}  On-Secondary Cont: {argb_to_hex(self.on_secondary_container)}")
        print(f"  Tertiary:         {ansi_color_box(self.tertiary, self.on_tertiary, 'Tertiary Accent', 28)}  On-Tertiary: {argb_to_hex(self.on_tertiary)}")
        print(f"  Tertiary Cont:    {ansi_color_box(self.tertiary_container, self.on_tertiary_container, 'Tertiary Container', 28)}  On-Tertiary Cont: {argb_to_hex(self.on_tertiary_container)}")
        print(f"  Error:            {ansi_color_box(self.error, self.on_error, 'Error Alert', 28)}  On-Error: {argb_to_hex(self.on_error)}")
        print()

        print("\033[1;4m2. SURFACE ELEVATION LADDER (TONE DELTAS)\033[0m")
        t_lowest = Hct.from_int(self.surface_container_lowest).tone
        t_low = Hct.from_int(self.surface_container_low).tone
        t_mid = Hct.from_int(self.surface_container).tone
        t_high = Hct.from_int(self.surface_container_high).tone
        t_highest = Hct.from_int(self.surface_container_highest).tone

        d_low = t_low - t_lowest
        d_mid = t_mid - t_low
        d_high = t_high - t_mid

        flag_low = "✅ CRISP" if abs(d_low) >= 7 else "⚠️ MUDDY (<7)"

        print(f"  [Level 0] Lowest (Canvas):      {ansi_swatch(self.surface_container_lowest)}  Base Canvas Layer")
        print(f"  [Level 1] Low (Sidebar):        {ansi_swatch(self.surface_container_low)}  ΔT = {d_low:+0.1f} vs Canvas  [{flag_low}]")
        print(f"  [Level 2] Mid (Pill / Cards):   {ansi_swatch(self.surface_container)}  ΔT = {d_mid:+0.1f} vs Sidebar")
        print(f"  [Level 3] High (Headerbar):     {ansi_swatch(self.surface_container_high)}  ΔT = {d_high:+0.1f} vs Mid")
        print(f"  [Level 4] Highest (Dialogs):    {ansi_swatch(self.surface_container_highest)}  Elevated Popovers")
        print()

        print("\033[1;4m3. INVERSE ROLES & HIGH-CONTRAST HIGHLIGHTS\033[0m")
        print(f"  Inverse Surface:  {ansi_color_box(self.inverse_surface, self.inverse_on_surface, 'Inverse Surface Pill', 28)}  On-Inverse: {argb_to_hex(self.inverse_on_surface)}")
        print(f"  Inverse Primary:  {ansi_swatch(self.inverse_primary)}  Inverse Primary Action")
        print(f"  Outline:          {ansi_swatch(self.outline)}  Standard 1px Boundary")
        print(f"  Outline Variant:  {ansi_swatch(self.outline_variant)}  Subtle Structural Divider")
        print()

        print("\033[1;4m4. UI COMPONENT RECIPE MAPPING (HOW WIDGETS ARE COLORED)\033[0m")
        print(f"  • Folder View Canvas:       {ansi_swatch(self.surface_container_lowest, 'surfaceContainerLowest')}")
        print(f"  • Sidebar Left Rail:        {ansi_swatch(self.surface_container_low, 'surfaceContainerLow')}")
        print(f"  • Active Sidebar Pill (M3): {ansi_color_box(self.secondary_container, self.on_secondary_container, 'secondaryContainer (M3 Standard)')}")
        print(f"  • Active Sidebar Pill (Alt):{ansi_color_box(self.primary, self.on_primary, 'primary (Vivid Pill)')}")
        print(f"  • Active Sidebar (Inverse): {ansi_color_box(self.inverse_surface, self.inverse_on_surface, 'inverseSurface (High-Contrast)')}")
        print(f"  • Breadcrumb Capsule:       {ansi_swatch(self.surface_container, 'surfaceContainer')}")
        print(f"  • Top Headerbar:            {ansi_swatch(self.surface_container_high, 'surfaceContainerHigh')}")
        print(f"  • Folder Icons:             {ansi_swatch(self.primary, 'primary')}")
        print()


def compare_styles(seed_hex: str, is_dark: bool):
    styles = ["vibrant", "eassy", "expressive", "tonal_spot", "neutral"]
    mode_str = "DARK" if is_dark else "LIGHT"
    print(f"\n\033[1;36m=== SIDE-BY-SIDE PALETTE STYLE COMPARISON [{mode_str} | Seed: {seed_hex}] ===\033[0m\n")
    print(f"{'Style':<16} {'Canvas':<22} {'Sidebar':<22} {'Active Pill (SecCont)':<26} {'Primary (Vivid)':<22}")
    print("─" * 108)

    for st in styles:
        m = ThemeMatrix(seed_hex, is_dark, st)
        canvas_box = ansi_swatch(m.surface_container_lowest)
        sidebar_box = ansi_swatch(m.surface_container_low)
        pill_box = ansi_swatch(m.secondary_container)
        primary_box = ansi_swatch(m.primary)

        print(f"{st.upper():<16} {canvas_box}   {sidebar_box}   {pill_box}   {primary_box}")
    print()


def main():
    detected_seed, detected_dark = detect_system_seed()

    parser = argparse.ArgumentParser(description="ib theme — Material 3 Theme & Component Matrix Auditor")
    parser.add_argument("--seed", default=detected_seed, help=f"Hex seed color (default: auto-detected {detected_seed})")
    parser.add_argument("--dark", action="store_true", default=None, help="Force Dark Mode")
    parser.add_argument("--light", action="store_true", default=None, help="Force Light Mode")
    parser.add_argument("--style", default="eassy", choices=list(STYLE_MAP.keys()), help="Palette style (default: eassy)")
    parser.add_argument("--contrast", type=float, default=0.0, help="Contrast level (-1.0 to 1.0)")
    parser.add_argument("--compare", action="store_true", help="Compare all styles side-by-side")

    args = parser.parse_args()

    is_dark = detected_dark
    if args.dark:
        is_dark = True
    elif args.light:
        is_dark = False

    if args.compare:
        compare_styles(args.seed, is_dark)
    else:
        matrix = ThemeMatrix(args.seed, is_dark, args.style, args.contrast)
        matrix.print_overview()


if __name__ == "__main__":
    main()
