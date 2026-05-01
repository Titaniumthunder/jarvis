# cad_agent.py
# Generates 3D models and images.
#
#   generate_image   → SDXL-Turbo 2D image, shown inline in chat
#   generate_cad     → Three.js HTML browser preview (rotatable)
#   generate_shape_e → Text → SDXL image → TripoSR 3D mesh → Blender

import re
from tools import llm_tool, html_preview_tool, shape_tool
from tools.llm_tool import SMART_MODEL

THREEJS_FREEFORM_PROMPT = """
You are an expert Three.js developer.
Write the body of a createModel() function that builds the described shape.

RULES:
- Return ONLY the JavaScript inside the function body — no declaration, no markdown.
- Last line must be: return mesh;  or  return group;
- The variable `material` is already defined in scope (MeshStandardMaterial).
- Use THREE.Group() to combine multiple meshes for complex objects.
- All units in metres (1 = 1m).
""".strip()


def run(command: dict) -> str:
    task        = command.get("task", "generate_cad")
    description = command.get("description", "")
    filename    = command.get("filename", "model")

    if task == "open_bambu":
        return f"Bambu Studio integration coming soon. File: {command.get('stl_path', '')}"

    if not description:
        return "No description provided."

    if task == "generate_image":
        return _generate_image(description)

    if task == "generate_shape_e":
        return _generate_shape_e(description)

    # Default: Three.js HTML preview
    return _generate_html_preview(description, filename)


# ── Image generation ──────────────────────────────────────────────────────────

def _generate_image(description: str) -> str:
    from tools import image_gen_tool
    print(f"[cad_agent] Generating image: '{description}'")
    img_path = image_gen_tool.generate_standalone(description)
    if img_path.startswith("[image_gen] ERROR"):
        return img_path
    return f"IMAGE:{img_path}"


# ── HTML preview (Three.js) ───────────────────────────────────────────────────

def _generate_html_preview(description: str, filename: str) -> str:
    print(f"[cad_agent] Generating HTML preview: '{description}'")
    shape = shape_tool.get_shape_definition(description)

    if shape and shape.get("shape_type") == "revolution":
        profile       = shape["profile"]
        segments      = shape.get("segments", 64)
        name          = shape.get("name", description)
        geometry_code = shape_tool.profile_to_threejs(profile, segments)
        print(f"[cad_agent] Revolution shape — {len(profile)} profile points")
    else:
        print(f"[cad_agent] Freeform shape — generating Three.js code directly")
        geometry_code = llm_tool.ask(
            prompt=f"Generate Three.js geometry for: {description}",
            system=THREEJS_FREEFORM_PROMPT,
            model=SMART_MODEL,
            temperature=0.15,
            max_tokens=1000,
        )
        if geometry_code.startswith("[llm_tool]"):
            return geometry_code
        geometry_code = _strip_fences(geometry_code)
        name = description

    html_path = html_preview_tool.generate_and_open(geometry_code, name)
    return f"3D preview opened in browser.\nFile: {html_path}"


# ── TripoSR pipeline (Text → Image → 3D mesh → Blender) ──────────────────────

def _generate_shape_e(description: str) -> str:
    from tools import image_gen_tool, triposr_tool
    print(f"[cad_agent] Step 1/3 — Generating image of '{description}'...")
    img_path = image_gen_tool.generate(description)
    if img_path.startswith("[image_gen] ERROR"):
        return f"Image generation failed: {img_path}"

    print(f"[cad_agent] Step 2/3 — Converting to 3D mesh with TripoSR...")
    obj_path = triposr_tool.generate_from_image(img_path, description)
    if obj_path.startswith("[triposr] ERROR"):
        return obj_path

    print(f"[cad_agent] Step 3/3 — Opening in Blender...")
    result = triposr_tool.open_in_blender(obj_path)
    if result != "Done":
        return f"Model saved to {obj_path}. Blender: {result}"

    return f"'{description}' generated and opened in Blender.\nSaved to: {obj_path}"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        end   = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        text  = "\n".join(lines[1:end]).strip()
    match = re.match(
        r'^\s*function\s+createModel\s*\(\s*\)\s*\{([\s\S]*)\}\s*$', text)
    if match:
        text = match.group(1).strip()
    return text
