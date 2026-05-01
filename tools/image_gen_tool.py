# image_gen_tool.py
# Generates images from text using Stable Diffusion (runs locally via diffusers).
#
# Uses SDXL-Turbo — generates high quality images in just 4 steps (~10-20s on M5 Pro).
# Model downloads ~7GB on first run, cached permanently after that.
#
# The images are used as input for the image-to-3D pipeline (Shap-E image300M).
# A white background + full body view prompt gives the best 3D conversion results.

import torch
import warnings
warnings.filterwarnings("ignore")

from tools import paths

# Where to save generated images
OUTPUT_DIR = paths.IMAGE_GEN_OUTPUT

# Fixed cache dir — prevents re-downloading when launched from different folders
CACHE_DIR = str(paths.SD_MODEL_CACHE)

# MPS + float32 (no fp16 variant).
# MPS + fp16 produces solid black images on torch 2.11+ (precision bug in VAE).
# MPS + float32 works correctly AND is fast (~2s for 4 steps on M5 Pro).
# The float32 model files are cached locally — no re-download needed.
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
DTYPE  = torch.float32

_pipe = None


def _load_pipeline():
    """Load SDXL-Turbo once. Cached in memory for subsequent calls."""
    global _pipe
    if _pipe is not None:
        return

    print("[image_gen] Loading SDXL-Turbo (first run downloads ~7GB, loading from cache after that)...")
    from diffusers import AutoPipelineForText2Image

    _pipe = AutoPipelineForText2Image.from_pretrained(
        "stabilityai/sdxl-turbo",
        torch_dtype=DTYPE,
        # No variant="fp16" — use float32 model files (cached, no re-download)
        cache_dir=CACHE_DIR,
    )
    _pipe = _pipe.to(DEVICE)
    print(f"[image_gen] SDXL-Turbo ready on {DEVICE} ({DTYPE}).")


def generate(prompt: str, negative_prompt: str = "") -> str:
    """
    Generate an image from a text prompt and save it as PNG.

    The prompt is automatically enhanced for 3D conversion:
    - White background so the background remover in Shap-E works cleanly
    - Full body view so the 3D model captures the whole subject
    - 3D render style for cleaner shapes

    Args:
        prompt:          What to generate (e.g. "Pikachu holding a flower pot")
        negative_prompt: What to avoid (optional)

    Returns:
        Path to the saved PNG, or error string.
    """
    _load_pipeline()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Enhance the prompt for better 3D conversion results
    enhanced = (
        f"3D render of {prompt}, "
        "full body view, white background, single object centred, "
        "clean edges, no shadows, cartoon style, high detail"
    )
    neg = negative_prompt or "blurry, low quality, multiple objects, complex background, text"

    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in prompt)[:50]
    img_path  = OUTPUT_DIR / f"{safe_name}.png"

    print(f"[image_gen] Generating image for: '{prompt}'")
    print(f"[image_gen] Device: {DEVICE} | float32 | ~2-5 seconds on M5 Pro...")

    try:
        result = _pipe(
            prompt=enhanced,
            negative_prompt=neg,
            num_inference_steps=4,    # SDXL-Turbo is designed for 4 steps
            guidance_scale=0.0,       # SDXL-Turbo doesn't use classifier-free guidance
            height=512,
            width=512,
        )
        image = result.images[0]
        image.save(img_path)
        print(f"[image_gen] Saved to {img_path}")
        return str(img_path)

    except Exception as e:
        return f"[image_gen] ERROR: {e}"


def generate_standalone(prompt: str, negative_prompt: str = "") -> str:
    """
    Generate an image from a text prompt for display — NOT for 3D conversion.
    Uses the prompt as-is with quality boosters, no white background or 3D-render overrides.

    Args:
        prompt:          What to generate (e.g. "a sunset over the ocean")
        negative_prompt: What to avoid (optional)

    Returns:
        Path to the saved PNG, or error string starting with "[image_gen] ERROR".
    """
    _load_pipeline()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    enhanced = f"{prompt}, highly detailed, sharp focus, vibrant colours, 4K"
    neg = negative_prompt or "blurry, low quality, text, watermark, nsfw"

    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in prompt)[:50]
    img_path  = OUTPUT_DIR / f"{safe_name}.png"

    print(f"[image_gen] Generating standalone image for: '{prompt}'")
    print(f"[image_gen] Device: {DEVICE} | float32 | ~2-5 seconds on M5 Pro...")

    try:
        result = _pipe(
            prompt=enhanced,
            negative_prompt=neg,
            num_inference_steps=4,
            guidance_scale=0.0,
            height=512,
            width=512,
        )
        image = result.images[0]
        image.save(img_path)
        print(f"[image_gen] Saved to {img_path}")
        return str(img_path)

    except Exception as e:
        return f"[image_gen] ERROR: {e}"
