# paths.py
# Single source of truth for every file/directory location Jarvis touches.
#
# Anything anchored to JARVIS_ROOT resolves relative to this file's location,
# so the repo works no matter where it's cloned. External tool binaries are
# read from environment variables with sensible Mac defaults.

import os
import pathlib

JARVIS_ROOT = pathlib.Path(__file__).resolve().parent.parent

IMAGE_GEN_OUTPUT = JARVIS_ROOT / "image_gen_output"
SHAPE_E_OUTPUT   = JARVIS_ROOT / "shape_e_output"
PREVIEWS         = JARVIS_ROOT / "previews"
BLENDER_SCRIPTS  = JARVIS_ROOT / "blender_scripts"
CODE_OUTPUT      = JARVIS_ROOT / "code_output"
SD_MODEL_CACHE   = JARVIS_ROOT / "sd_model_cache"
TRIPOSR_CACHE    = JARVIS_ROOT / "triposr_cache"
TRIPOSR_SRC      = JARVIS_ROOT / "triposr_src"

MEMORY_VAULT = pathlib.Path.home() / "Documents" / "Jarvis Memory"

# External tools — read from env with sensible Mac defaults
BLENDER_PATH = os.environ.get(
    "JARVIS_BLENDER_PATH",
    "/Applications/Blender.app/Contents/MacOS/Blender",
)
CLAUDE_CLI = os.environ.get("JARVIS_CLAUDE_CLI", "/usr/local/bin/claude")
