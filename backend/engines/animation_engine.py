# """Pre-built animation library is copied locally; LLM only picks timing. Saves most animation tokens."""
# import re
# from backend.config import TEMPLATES_DIR

# EASING = re.compile(r"^(ease|ease-in|ease-out|ease-in-out|linear|cubic-bezier\(\s*-?[\d.]+\s*(,\s*-?[\d.]+\s*){3}\))$")
# DEFAULT = {"hero": "fade-up", "scroll": "reveal", "hover": "lift", "lib": "css",
#            "duration_ms": [250, 700], "easing": "cubic-bezier(.22,1,.36,1)"}


# def normalize(m) -> dict:
#     m = m if isinstance(m, dict) else {}
#     out = dict(DEFAULT)
#     for k in ("hero", "scroll", "hover"):
#         out[k] = str(m.get(k, DEFAULT[k]))[:60]
#     try:
#         lo, hi = (max(100, min(int(x), 2000)) for x in m.get("duration_ms", DEFAULT["duration_ms"])[:2])
#         out["duration_ms"] = [min(lo, hi), max(lo, hi)]
#     except (TypeError, ValueError):
#         pass
#     e = str(m.get("easing", "")).strip()
#     out["easing"] = e if EASING.match(e) else DEFAULT["easing"]
#     return out  # Phase 2 ships the CSS/vanilla-JS engine only (lib forced to "css")


# def css_vars(m) -> str:
#     m = normalize(m)
#     lo, hi = m["duration_ms"]
#     return f":root{{--dur-min:{lo}ms;--dur-max:{hi}ms;--ease:{m['easing']};}}\n"


# def install(pf) -> None:
#     pf.write("css/animations.css", (TEMPLATES_DIR / "animation" / "animations.css").read_text(encoding="utf-8"))
#     pf.write("js/motion.js", (TEMPLATES_DIR / "animation" / "motion.js").read_text(encoding="utf-8"))


























"""
Local animation engine for the Full-Stack AI Developer Agent.

Design goals:
- Pre-built CSS and vanilla-JS animations are copied locally.
- The LLM selects animation presets and timing only.
- CSS-only animation engine for Phase 2.
- Strict validation and safe defaults.
- Reduced-motion accessibility support.
- Responsive, lightweight animations without unnecessary dependencies.
"""

import re
from pathlib import Path

from backend.config import TEMPLATES_DIR


# ----------------------------------------------------------------
# 1. VALIDATION
# ----------------------------------------------------------------

EASING = re.compile(
    r"^(?:ease|ease-in|ease-out|ease-in-out|linear|"
    r"cubic-bezier\(\s*-?(?:\d+(?:\.\d*)?|\.\d+)"
    r"\s*,\s*-?(?:\d+(?:\.\d*)?|\.\d+)"
    r"\s*,\s*-?(?:\d+(?:\.\d*)?|\.\d+)"
    r"\s*,\s*-?(?:\d+(?:\.\d*)?|\.\d+)\s*\))$"
)

PRESETS = {
    "hero": {
        "fade-up",
        "fade-in",
        "scale-in",
        "slide-in",
        "none",
    },
    "scroll": {
        "reveal",
        "reveal-left",
        "reveal-scale",
        "fade-up",
        "none",
    },
    "hover": {
        "lift",
        "glow",
        "scale",
        "underline",
        "none",
    },
}

DEFAULT = {
    "hero": "fade-up",
    "scroll": "reveal",
    "hover": "lift",
    "lib": "css",
    "duration_ms": [250, 700],
    "easing": "cubic-bezier(.22,1,.36,1)",
}

MIN_DURATION = 100
MAX_DURATION = 2000
MAX_PRESET_LENGTH = 60


# ----------------------------------------------------------------
# 2. NORMALIZE MODEL OUTPUT
# ----------------------------------------------------------------

def normalize(m) -> dict:
    """
    Validate animation settings returned by the LLM.

    Unknown presets fall back to safe defaults.
    The animation library is always CSS in Phase 2.
    """

    m = m if isinstance(m, dict) else {}
    out = dict(DEFAULT)

    # Validate animation presets.
    for key, allowed in PRESETS.items():
        value = m.get(key, DEFAULT[key])

        if not isinstance(value, str):
            value = DEFAULT[key]

        value = value.strip()[:MAX_PRESET_LENGTH]

        out[key] = (
            value if value in allowed else DEFAULT[key]
        )

    # Phase 2 supports CSS only.
    out["lib"] = "css"

    # Validate animation durations.
    try:
        durations = m.get(
            "duration_ms",
            DEFAULT["duration_ms"],
        )

        if (
            not isinstance(durations, (list, tuple))
            or len(durations) != 2
            or isinstance(durations[0], bool)
            or isinstance(durations[1], bool)
        ):
            raise ValueError("Invalid duration range")

        lo, hi = (
            max(MIN_DURATION, min(int(x), MAX_DURATION))
            for x in durations
        )

        out["duration_ms"] = [
            min(lo, hi),
            max(lo, hi),
        ]

    except (TypeError, ValueError, OverflowError):
        out["duration_ms"] = list(DEFAULT["duration_ms"])

    # Validate easing values.
    easing = m.get("easing", DEFAULT["easing"])

    if not isinstance(easing, str):
        easing = DEFAULT["easing"]

    easing = easing.strip()

    if EASING.fullmatch(easing):
        # Prevent cubic-bezier control points outside [0, 1].
        if easing.startswith("cubic-bezier"):
            numbers = re.findall(
                r"-?(?:\d+(?:\.\d*)?|\.\d+)",
                easing,
            )

            try:
                points = [float(n) for n in numbers]

                if (
                    len(points) != 4
                    or not all(
                        -1000 <= n <= 1000
                        for n in points
                    )
                    or not 0 <= points[0] <= 1
                    or not 0 <= points[2] <= 1
                ):
                    easing = DEFAULT["easing"]

            except (ValueError, OverflowError):
                easing = DEFAULT["easing"]

        out["easing"] = easing
    else:
        out["easing"] = DEFAULT["easing"]

    return out


# ----------------------------------------------------------------
# 3. GENERATE CSS VARIABLES
# ----------------------------------------------------------------

def css_vars(m) -> str:
    """
    Generate validated CSS custom properties.

    These variables are consumed by the local animation stylesheet.
    """

    m = normalize(m)
    lo, hi = m["duration_ms"]

    return (
        ":root {\n"
        f"  --dur-min: {lo}ms;\n"
        f"  --dur-max: {hi}ms;\n"
        f"  --ease: {m['easing']};\n"
        "}\n"
    )


# ----------------------------------------------------------------
# 4. LOCAL TEMPLATE HELPERS
# ----------------------------------------------------------------

def _read_template(name: str) -> str:
    """
    Read a required animation template from the local templates folder.
    """

    path = (
        Path(TEMPLATES_DIR)
        / "animation"
        / name
    )

    if not path.is_file():
        raise FileNotFoundError(
            f"Required animation template is missing: {name}"
        )

    return path.read_text(encoding="utf-8")


# ----------------------------------------------------------------
# 5. INSTALL ANIMATION ENGINE
# ----------------------------------------------------------------

def install(pf) -> None:
    """
    Install local CSS and vanilla-JS animation assets.

    pf must provide a write(relative_path, content) method.
    """

    assets = {
        "css/animations.css": _read_template(
            "animations.css"
        ),
        "js/motion.js": _read_template(
            "motion.js"
        ),
    }

    for relative_path, content in assets.items():
        if not content.strip():
            raise ValueError(
                f"Animation asset is empty: {relative_path}"
            )

        pf.write(relative_path, content)


# ----------------------------------------------------------------
# 6. GENERATE ANIMATION CONFIGURATION
# ----------------------------------------------------------------

def animation_config(m) -> dict:
    """
    Return a normalized configuration suitable for JSON serialization.
    """

    config = normalize(m)

    return {
        **config,
        "reduced_motion": True,
        "engine": "css",
    }


# ----------------------------------------------------------------
# 7. GENERATE ACCESSIBILITY OVERRIDES
# ----------------------------------------------------------------

def reduced_motion_css() -> str:
    """
    Disable nonessential motion for users who prefer reduced motion.
    """

    return """
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
  }
}
""".strip() + "\n"


# ----------------------------------------------------------------
# 8. PRESET CLASS GENERATION
# ----------------------------------------------------------------

def preset_classes(m) -> dict:
    """
    Convert normalized preset selections to CSS class names.
    """

    config = normalize(m)

    return {
        "hero": (
            ""
            if config["hero"] == "none"
            else config["hero"]
        ),
        "scroll": (
            ""
            if config["scroll"] == "none"
            else config["scroll"]
        ),
        "hover": (
            ""
            if config["hover"] == "none"
            else config["hover"]
        ),
    }


# ----------------------------------------------------------------
# 9. COMBINED INSTALLATION
# ----------------------------------------------------------------

def install_animation_system(pf, model_output) -> dict:
    """
    Install assets and return the configuration for the generated project.
    """

    config = animation_config(model_output)

    install(pf)

    pf.write(
        "css/animation-config.css",
        css_vars(config) + reduced_motion_css(),
    )

    return {
        "config": config,
        "classes": preset_classes(config),
        "assets": [
            "css/animations.css",
            "css/animation-config.css",
            "js/motion.js",
        ],
    }
