# triposr_tool.py
# Generates a 3D mesh from an image using TripoSR (Stability AI).
#
# Pipeline:
#   Image → TripoSR → .obj mesh → Blender
#
# TripoSR is dramatically better than Shap-E:
#   - Generates clean, detailed geometry (not just blobs)
#   - ~5 seconds per mesh on CPU
#   - ~1.2GB model, cached after first download
#
# Model: stabilityai/TripoSR

import pathlib
import sys
import torch
import warnings
warnings.filterwarnings("ignore")

# Add the cloned TripoSR source directory to path so `from tsr.system import TSR` works.
# The VAST-AI-Research/TripoSR repo is not a pip-installable package — it ships a raw
# `tsr/` folder that must be on sys.path directly.
_TRIPOSR_SRC = pathlib.Path.home() / "Personal Project" / "Desktop assistant" / "jarvis" / "triposr_src"
if str(_TRIPOSR_SRC) not in sys.path:
    sys.path.insert(0, str(_TRIPOSR_SRC))

OUTPUT_DIR = pathlib.Path.home() / "Personal Project" / "Desktop assistant" / "jarvis" / "shape_e_output"
CACHE_DIR  = str(pathlib.Path.home() / "Personal Project" / "Desktop assistant" / "jarvis" / "triposr_cache")

# Run on CPU — MPS has precision issues with some TripoSR ops
DEVICE = "cpu"

_model = None


def _load_model():
    global _model
    if _model is not None:
        return

    print("[triposr] Loading TripoSR (~1.2GB download on first run, cached after)...")
    from tsr.system import TSR

    _model = TSR.from_pretrained(
        "stabilityai/TripoSR",
        config_name="config.yaml",
        weight_name="model.ckpt",
    )
    _model.renderer.set_chunk_size(8192)
    _model = _model.to(DEVICE)
    print("[triposr] TripoSR ready.")


def generate_from_image(img_path: str, name: str = "model") -> str:
    """
    Generate a 3D mesh from an image using TripoSR.

    Args:
        img_path: Path to the input image (PNG/JPG)
        name:     Name for the output file

    Returns:
        Path to the saved .obj file, or error string starting with "[triposr] ERROR"
    """
    from PIL import Image
    _load_model()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[triposr] Removing background from image...")
    try:
        from rembg import remove
        raw = Image.open(img_path).convert("RGBA")
        rgba = remove(raw)                          # keep RGBA — TripoSR uses alpha channel
        # Save the masked image so we can debug if the background removal worked
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:50]
        masked_path = OUTPUT_DIR / f"{safe_name}_masked.png"
        rgba.save(str(masked_path))
        print(f"[triposr] Masked image saved to {masked_path}")
        image = rgba.convert("RGB")
    except Exception as e:
        print(f"[triposr] Background removal failed ({e}), using image as-is")
        image = Image.open(img_path).convert("RGB")

    print(f"[triposr] Generating 3D mesh for: '{name}' (~5-15 seconds)...")
    try:
        with torch.no_grad():
            scene_codes = _model([image], device=DEVICE)

        # resolution=256 is the default — higher (384/512) gives more detail but much slower
        meshes = _model.extract_mesh(scene_codes, has_vertex_color=False, resolution=256)
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:50]
        obj_path  = OUTPUT_DIR / f"{safe_name}_triposr.obj"
        meshes[0].export(str(obj_path))
        print(f"[triposr] Saved mesh to {obj_path}")
        return str(obj_path)

    except Exception as e:
        return f"[triposr] ERROR: {e}"


def open_in_blender(obj_path: str) -> str:
    """Import the TripoSR .obj into Blender, clean it up and open it."""
    import pathlib, textwrap
    from tools import blender_tool

    script = textwrap.dedent(f"""
        import bpy

        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)

        bpy.ops.wm.obj_import(filepath=r"{obj_path}")

        obj = bpy.context.selected_objects[0] if bpy.context.selected_objects else None
        if obj:
            # Centre to world origin
            bpy.ops.object.origin_set(type='GEOMETRY_ORIGIN', center='BOUNDS')
            obj.location = (0, 0, 0)

            # Smooth shading — keeps detail, just looks nicer than flat
            bpy.ops.object.shade_smooth()

            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
    """).strip()

    name = pathlib.Path(obj_path).stem
    return blender_tool.run_script(script, name)
