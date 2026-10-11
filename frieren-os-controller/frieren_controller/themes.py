"""Local theme palettes; private wallpapers are referenced, never bundled."""

THEMES = {
    "night": {
        "name": "프리렌의 밤",
        "dark": True,
        "wallpaper": "frieren-beyond-5120x2880-25925.jpg",
        "position": "center 12%",
        "colors": {
            "background": "#1e1e2e",
            "sidebar": "#181825",
            "surface": "#313244",
            "border": "#45475a",
            "selected": "#45475a",
            "text": "#cdd6f4",
            "muted": "#a6adc8",
            "faint": "#9399b2",
            "primary": "#f5c2e7",
            "accent": "#cba6f7",
            "cyan": "#74c7ec",
            "healthy": "#a6e3a1",
            "error": "#f38ba8",
        },
    },
    "dawn": {
        "name": "새벽의 마법",
        "dark": False,
        "wallpaper": "frieren-5k-white-5120x2880-15144.jpeg",
        "position": "center 22%",
        "colors": {
            "background": "#f4f0f6",
            "sidebar": "#ece6ef",
            "surface": "#fffafb",
            "border": "#d9cfe0",
            "selected": "#ded5ea",
            "text": "#312a3e",
            "muted": "#625b73",
            "faint": "#746c80",
            "primary": "#73405f",
            "accent": "#71509d",
            "cyan": "#286c7c",
            "healthy": "#336d49",
            "error": "#a3314f",
        },
    },
    "forest": {
        "name": "숲의 여정",
        "dark": True,
        "wallpaper": "frieren-beyond-3840x2160-24988.jpg",
        "position": "center 52%",
        "colors": {
            "background": "#182521",
            "sidebar": "#121d19",
            "surface": "#253830",
            "border": "#40544a",
            "selected": "#3a5144",
            "text": "#e5eddf",
            "muted": "#b9c9b9",
            "faint": "#98ad9f",
            "primary": "#d9dfae",
            "accent": "#a7ceb4",
            "cyan": "#9bd3c5",
            "healthy": "#b6d49b",
            "error": "#f0a7ad",
        },
    },
}


def theme_css(name: str, template: bytes) -> bytes:
    theme = THEMES.get(name, THEMES["night"])
    colors = theme["colors"]
    definitions = "\n".join(
        f"@define-color {key} {value};" for key, value in (colors | native_colors(colors)).items()
    )
    return definitions.encode() + b"\n" + template


def native_colors(colors: dict[str, str]) -> dict[str, str]:
    """Map GTK/Breeze native surfaces to the same foreground/background pairs as our pages."""
    roles = {
        "theme_bg_color": "background",
        "theme_base_color": "background",
        "theme_fg_color": "text",
        "theme_text_color": "text",
        "theme_selected_bg_color": "selected",
        "theme_selected_fg_color": "text",
        "insensitive_bg_color": "surface",
        "insensitive_base_color": "background",
        "insensitive_fg_color": "muted",
        "insensitive_base_fg_color": "muted",
        "unfocused_bg_color": "background",
        "unfocused_base_color": "background",
        "unfocused_fg_color": "text",
        "unfocused_text_color": "text",
        "unfocused_selected_bg_color": "selected",
        "unfocused_selected_fg_color": "text",
        "borders": "border",
        "warning_color": "primary",
        "error_color": "error",
        "success_color": "healthy",
    }
    result = {name: colors[role] for name, role in roles.items()}
    breeze_roles = {name + "_breeze": role for name, role in roles.items()}
    breeze_roles.update(
        {
            "content_view_bg_breeze": "background",
            "theme_unfocused_bg_color_breeze": "background",
            "theme_unfocused_base_color_breeze": "background",
            "theme_unfocused_fg_color_breeze": "text",
            "theme_unfocused_text_color_breeze": "text",
            "theme_unfocused_view_bg_color_breeze": "background",
            "theme_unfocused_view_text_color_breeze": "text",
            "theme_unfocused_selected_bg_color_breeze": "selected",
            "theme_unfocused_selected_bg_color_alt_breeze": "selected",
            "theme_unfocused_selected_fg_color_breeze": "text",
            "theme_hovering_selected_bg_color_breeze": "selected",
            "theme_view_active_decoration_color_breeze": "accent",
            "theme_view_hover_decoration_color_breeze": "cyan",
            "link_color_breeze": "cyan",
            "link_visited_color_breeze": "primary",
            "tooltip_background_breeze": "surface",
            "tooltip_text_breeze": "text",
            "tooltip_border_breeze": "border",
        }
    )
    for state in (
        "normal",
        "active",
        "backdrop",
        "insensitive",
        "active_backdrop",
        "active_insensitive",
        "backdrop_insensitive",
        "active_backdrop_insensitive",
    ):
        breeze_roles["theme_button_foreground_" + state + "_breeze"] = (
            "muted" if "insensitive" in state else "text"
        )
    for state in ("normal", "backdrop", "insensitive", "backdrop_insensitive"):
        breeze_roles["theme_button_background_" + state + "_breeze"] = "surface"
    for kind in ("header", "titlebar"):
        for state in ("", "_light", "_backdrop"):
            breeze_roles[f"theme_{kind}_background{state}_breeze"] = "sidebar"
        for state in ("", "_backdrop", "_insensitive", "_insensitive_backdrop"):
            breeze_roles[f"theme_{kind}_foreground{state}_breeze"] = "text"
    for name in ("base", "unfocused", "selected", "unfocused_selected"):
        breeze_roles[f"insensitive_{name}_bg_color_breeze"] = "surface"
        breeze_roles[f"insensitive_{name}_fg_color_breeze"] = "muted"
    result.update({name: colors[role] for name, role in breeze_roles.items()})
    return result
