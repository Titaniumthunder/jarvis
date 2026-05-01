# blender_mcp_agent.py
# Uses the live Blender MCP connection to create and refine 3D objects.
#
# Two modes:
#   run()    → create a new object from scratch (clears scene, saves session)
#   refine() → modify the last created object using saved code as context

import json
import pathlib
from tools import blender_mcp_tool, llm_tool, image_gen_tool

# Saves the last session so refinements have full context
SESSION_FILE = (
    pathlib.Path.home()
    / "Personal Project" / "Desktop assistant" / "jarvis"
    / "blender_scripts" / "_last_session.json"
)

MAX_RETRIES = 2

SYSTEM = """You are an expert Blender Python (bpy) developer.
Write ONLY bpy Python code — no explanations, no markdown, no backticks.

Critical rules:
- import bpy at the top. import math separately (NOT bpy.math — does not exist)
- NEVER use bmesh.ops.vert_add, bmesh.ops.create_face_from_verts — these do not exist
- NEVER use bmesh.ops.polyextrude_face_region — does not exist
- NEVER use bmesh.ops.extrude_vert_indiv — does not exist
- The ONLY valid bmesh extrude is: bmesh.ops.extrude_face_region(bm, geom=list(bm.faces))
- NEVER use bpy.ops.curve.* in script mode — unreliable
- NEVER call bpy.ops.object.modifier_apply() — fails in script mode
- For mechanical/hard-surface objects (gears, bolts, brackets, machines): end with bpy.ops.object.shade_flat()
- For organic objects (characters, creatures, blobs): end with bpy.ops.object.shade_smooth()
- For objects with handles or complex shapes: build them from multiple primitives joined together
  Safe primitives: bpy.ops.mesh.primitive_cylinder_add, primitive_uv_sphere_add, primitive_torus_add, primitive_cube_add, primitive_cone_add

Correct bmesh API:
  bm = bmesh.new()
  v1 = bm.verts.new((x, y, z))     # add a vertex
  bm.faces.new([v1, v2, v3, v4])   # add a face from vertex list
  bmesh.ops.extrude_face_region(bm, geom=bm.faces[:])  # extrude
  bm.to_mesh(mesh); bm.free(); mesh.update()

Example — proper gear with flat-topped teeth, center hole, and thickness:
  import bpy, bmesh, math
  bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete()
  mesh = bpy.data.meshes.new("Gear")
  obj  = bpy.data.objects.new("Gear", mesh)
  bpy.context.collection.objects.link(obj)
  bpy.context.view_layer.objects.active = obj
  bm = bmesh.new()
  teeth=10; r_root=0.75; r_tip=1.0; r_hole=0.2; depth=0.3
  tooth_width=0.6
  profile = []
  for i in range(teeth):
      base_angle = 2*math.pi*i/teeth
      slot = math.pi/teeth
      gap  = slot*(1-tooth_width)
      for a, r in [(base_angle-slot, r_root),(base_angle-slot+gap, r_tip),
                   (base_angle+slot-gap, r_tip),(base_angle+slot, r_root)]:
          profile.append((math.cos(a)*r, math.sin(a)*r))
  hole = [(math.cos(2*math.pi*i/24)*r_hole, math.sin(2*math.pi*i/24)*r_hole) for i in range(24)]
  def ring(pts, z): return [bm.verts.new((x, y, z)) for x,y in pts]
  ob=ring(profile,0); ot=ring(profile,depth); ib=ring(hole,0); it=ring(hole,depth)
  n=len(ob); bm.faces.new(list(reversed(ob))+ib); bm.faces.new(ot+list(reversed(it)))
  for i in range(n): bm.faces.new([ob[i],ob[(i+1)%n],ot[(i+1)%n],ot[i]])
  h=len(ib)
  for i in range(h): bm.faces.new([ib[i],it[i],it[(i+1)%h],ib[(i+1)%h]])
  bm.to_mesh(mesh); bm.free(); mesh.update()

Example — coffee mug with handle using primitives:
  import bpy
  bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete()
  # Body: cylinder
  bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.5, depth=1.0, location=(0,0,0))
  body = bpy.context.active_object; body.name = "MugBody"
  # Handle: torus squashed into an oval, placed on the side
  bpy.ops.mesh.primitive_torus_add(major_radius=0.3, minor_radius=0.06,
      major_segments=24, minor_segments=12, location=(0.65, 0, 0))
  handle = bpy.context.active_object; handle.name = "MugHandle"
  handle.scale = (0.5, 1.0, 1.2)   # squash into oval shape
  # Join into one object
  bpy.ops.object.select_all(action='DESELECT')
  body.select_set(True); handle.select_set(True)
  bpy.context.view_layer.objects.active = body
  bpy.ops.object.join()
  bpy.ops.object.shade_smooth()"""


# ── Session helpers ───────────────────────────────────────────────────────────

def _save_session(description: str, code: str, image_path: str = None):
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps({
        "description": description,
        "code": code,
        "image_path": image_path,
    }, indent=2))


def _load_session() -> dict | None:
    try:
        if SESSION_FILE.exists():
            return json.loads(SESSION_FILE.read_text())
    except Exception:
        pass
    return None


# ── Create ────────────────────────────────────────────────────────────────────

def run(command: dict) -> str:
    description = command.get("description", "object")

    if not blender_mcp_tool.ensure_connected():
        return "[blender_mcp] Could not connect to Blender."

    print(f"[blender_mcp] Creating: '{description}'")
    blender_mcp_tool.clear_scene()

    # Generate a reference image first so Gemma4 can see what to build
    print(f"[blender_mcp] Generating reference image...")
    img_path = image_gen_tool.generate(description)
    has_image = img_path and not img_path.startswith("[image_gen] ERROR")

    if has_image:
        print(f"[blender_mcp] Using image as visual reference: {img_path}")
        prompt = (
            f"I am showing you an image of: {description}\n\n"
            f"Write Blender Python (bpy) code to create a 3D model that matches "
            f"the shape, proportions and style you see in this image.\n\n"
            f"- Clear the scene first\n"
            f"- Centre the final object at (0, 0, 0)\n"
            f"- Output ONLY the code, no explanation, no backticks"
        )
        code = _strip_fences(llm_tool.ask_with_image(prompt, img_path, system=SYSTEM, temperature=0.2, max_tokens=2000))
    else:
        print(f"[blender_mcp] No image available, generating from text only...")
        prompt = (
            f"Write Blender Python (bpy) code to create: {description}\n\n"
            f"- Clear the scene first\n"
            f"- Centre the final object at (0, 0, 0)\n"
            f"- Output ONLY the code, no explanation, no backticks"
        )
        code = _strip_fences(llm_tool.ask(prompt, system=SYSTEM, temperature=0.2, max_tokens=2000))
    code, result = _send_with_retry(code, description)

    if not result.startswith("[blender_mcp] ERROR"):
        _save_session(description, code, img_path if has_image else None)
        return f"Created '{description}' in Blender."

    return f"[blender_mcp] Failed to create '{description}'. Last error: {result}"


# ── Refine ────────────────────────────────────────────────────────────────────

def refine(command: dict) -> str:
    instruction = command.get("instruction", "").strip()

    if not blender_mcp_tool.ensure_connected():
        return "[blender_mcp] Could not connect to Blender."

    session = _load_session()
    if not session:
        return "I don't have memory of the last object I created. Try creating something first."

    description = session["description"]
    last_code   = session["code"]
    image_path  = session.get("image_path")

    # Also grab current scene state so the LLM knows what's there
    scene_info = blender_mcp_tool.get_scene_info()

    print(f"[blender_mcp] Refining '{description}': {instruction}")

    prompt = (
        f"You previously created this object in Blender: {description}\n\n"
        f"Current scene: {scene_info}\n\n"
        f"Here is the code that created it:\n{last_code}\n\n"
        f"Instruction: {instruction}\n\n"
        f"Return the COMPLETE updated code that recreates the object with this change applied. "
        f"Output ONLY the code, no explanation, no backticks."
    )

    # Use image reference if available
    has_image = image_path and pathlib.Path(image_path).exists()
    if has_image:
        print(f"[blender_mcp] Using original reference image for refinement")
        code = _strip_fences(llm_tool.ask_with_image(prompt, image_path, system=SYSTEM, temperature=0.2, max_tokens=2000))
    else:
        code = _strip_fences(llm_tool.ask(prompt, system=SYSTEM, temperature=0.2, max_tokens=2000))

    # Clear and rebuild with updated code
    blender_mcp_tool.clear_scene()
    code, result = _send_with_retry(code, instruction)

    if not result.startswith("[blender_mcp] ERROR"):
        _save_session(description, code, image_path if has_image else None)
        return f"Updated '{description}': {instruction}"

    return f"[blender_mcp] Refinement failed. Last error: {result}"


# ── Shared helpers ────────────────────────────────────────────────────────────

def _send_with_retry(code: str, context: str) -> tuple[str, str]:
    """Send code to Blender, auto-fixing errors up to MAX_RETRIES times.
    Returns (final_code, last_result)."""
    for attempt in range(MAX_RETRIES + 1):
        print(f"[blender_mcp] Sending to Blender (attempt {attempt + 1})...")
        result = str(blender_mcp_tool.run_code(code))

        if not result.startswith("[blender_mcp] ERROR"):
            print(f"[blender_mcp] Success")
            return code, result

        if attempt < MAX_RETRIES:
            print(f"[blender_mcp] Error: {result} — fixing...")
            fix_prompt = (
                f"This bpy code failed:\nError: {result}\n\nCode:\n{code}\n\n"
                f"Fix the error. Return ONLY the corrected code, no explanation, no backticks."
            )
            code = _strip_fences(llm_tool.ask(fix_prompt, system=SYSTEM, temperature=0.1, max_tokens=2000))

    return code, result


def _strip_fences(code: str) -> str:
    lines = code.strip().splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()
