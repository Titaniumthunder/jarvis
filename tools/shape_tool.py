# shape_tool.py
# The "shape compiler" — asks the LLM for a structured shape definition (JSON),
# then converts it into both Three.js and Blender code from the SAME data.
#
# This guarantees the HTML preview and Blender model are always identical.
#
# Two shape types are supported:
#   "revolution" — a profile spun 360° (vases, bowls, bottles, cups, columns)
#   "freeform"   — anything else (chairs, brackets, animals, buildings)
#                  for freeform, the LLM writes raw code directly

import json
from tools import llm_tool
from tools.llm_tool import SMART_MODEL

# ── Hardcoded fallback profiles for common shapes ────────────────────────────
# Used when the LLM generates a bad (cone-like) profile.
# Format: [(radius, height), ...]
FALLBACK_PROFILES = {
    "vase": {
        # Proven working profile — belly at mid-height, narrows to neck, slight rim flare
        "profile": [
            (0.0, 0.0), (0.5, 0.1), (0.9, 0.5), (1.1, 1.0),
            (1.2, 1.5), (1.0, 2.0), (0.6, 2.5), (0.45, 2.8), (0.5, 3.0)
        ],
        "segments": 64,
    },
    "bowl": {
        "profile": [
            (0.0, 0.0), (0.3, 0.05), (0.7, 0.25), (1.1, 0.6),
            (1.4, 1.0), (1.55, 1.35), (1.6, 1.6)
        ],
        "segments": 64,
    },
    "bottle": {
        "profile": [
            (0.0, 0.0), (0.4, 0.05), (0.5, 0.3), (0.65, 0.8),
            (0.85, 1.3), (0.9, 1.7), (0.7, 2.1), (0.3, 2.5),
            (0.25, 2.9), (0.28, 3.2)
        ],
        "segments": 64,
    },
    "cup": {
        "profile": [
            (0.0, 0.0), (0.5, 0.05), (0.55, 0.4), (0.6, 0.8),
            (0.65, 1.2), (0.68, 1.6), (0.7, 1.8)
        ],
        "segments": 48,
    },
    "wine glass": {
        # Wide foot → narrow stem → open bowl → flared rim
        "profile": [
            (0.0,  0.0),  (0.65, 0.02), (0.7,  0.06), (0.5,  0.12),
            (0.1,  0.22), (0.07, 0.6),  (0.08, 1.0),  (0.1,  1.15),
            (0.35, 1.35), (0.65, 1.65), (0.85, 1.95), (0.9,  2.25),
            (0.85, 2.5),  (0.88, 2.6)
        ],
        "segments": 64,
    },
    "goblet": {
        # Like wine glass but with a thicker stem and deeper bowl
        "profile": [
            (0.0,  0.0),  (0.7,  0.03), (0.75, 0.08), (0.55, 0.15),
            (0.18, 0.28), (0.15, 0.65), (0.18, 1.0),  (0.25, 1.1),
            (0.55, 1.35), (0.85, 1.7),  (1.0,  2.0),  (1.05, 2.3),
            (1.0,  2.55), (1.02, 2.65)
        ],
        "segments": 64,
    },
    "trophy": {
        # Wide cup on top, narrow stem, wide base
        "profile": [
            (0.0,  0.0),  (0.7,  0.03), (0.75, 0.1),  (0.6,  0.18),
            (0.2,  0.3),  (0.15, 0.6),  (0.2,  0.9),  (0.35, 1.05),
            (0.7,  1.25), (0.95, 1.55), (1.1,  1.85), (1.15, 2.15),
            (1.05, 2.45), (1.1,  2.55)
        ],
        "segments": 64,
    },
    "candlestick": {
        # Broad foot, elegant narrow column, small cup at top for candle
        "profile": [
            (0.0,  0.0),  (0.6,  0.03), (0.65, 0.1),  (0.5,  0.2),
            (0.3,  0.4),  (0.2,  0.8),  (0.18, 1.4),  (0.2,  2.0),
            (0.22, 2.6),  (0.25, 2.8),  (0.35, 2.9),  (0.38, 3.0),
            (0.35, 3.1),  (0.3,  3.15)
        ],
        "segments": 64,
    },
    "flower pot": {
        "profile": [
            (0.0,  0.0),  (0.45, 0.03), (0.5,  0.1),  (0.55, 0.5),
            (0.65, 1.0),  (0.75, 1.5),  (0.85, 1.9),  (0.9,  2.1),
            (0.95, 2.2),  (0.92, 2.3)
        ],
        "segments": 64,
    },
    "mug": {
        # Short cup, wider than tall, flat-ish walls
        "profile": [
            (0.0,  0.0),  (0.55, 0.03), (0.6,  0.08), (0.65, 0.5),
            (0.65, 1.0),  (0.65, 1.4),  (0.65, 1.6),  (0.68, 1.7),
            (0.65, 1.75)
        ],
        "segments": 48,
    },
    "pitcher": {
        # Wide belly, narrow base, wide open top with slight spout flare
        "profile": [
            (0.0,  0.0),  (0.4,  0.04), (0.55, 0.15), (0.75, 0.5),
            (0.9,  0.9),  (0.95, 1.3),  (0.9,  1.7),  (0.75, 2.0),
            (0.65, 2.2),  (0.7,  2.4),  (0.8,  2.5)
        ],
        "segments": 64,
    },
    "urn": {
        # Classic burial urn — wide belly, narrow neck, flared rim, small base
        "profile": [
            (0.0,  0.0),  (0.35, 0.04), (0.45, 0.15), (0.65, 0.45),
            (0.95, 0.9),  (1.1,  1.35), (1.15, 1.75), (1.0,  2.1),
            (0.65, 2.4),  (0.45, 2.6),  (0.5,  2.75), (0.6,  2.85)
        ],
        "segments": 64,
    },
    "hourglass": {
        # Wide top, pinches to narrow waist, wide bottom — symmetric
        "profile": [
            (0.0,  0.0),  (0.7,  0.04), (0.85, 0.15), (0.9,  0.4),
            (0.75, 0.7),  (0.45, 1.0),  (0.2,  1.3),  (0.15, 1.5),
            (0.2,  1.7),  (0.45, 2.0),  (0.75, 2.3),  (0.9,  2.55),
            (0.85, 2.75), (0.7,  2.85), (0.0,  2.9)
        ],
        "segments": 64,
    },
    "column": {
        # Greek/Roman column — base, shaft with slight taper, capital
        "profile": [
            (0.0,  0.0),  (0.7,  0.03), (0.75, 0.12), (0.65, 0.25),
            (0.55, 0.4),  (0.52, 1.0),  (0.5,  1.6),  (0.52, 2.2),
            (0.55, 2.8),  (0.65, 2.92), (0.75, 3.0)
        ],
        "segments": 32,
    },
    "lamp": {
        # Decorative lamp base — wide foot, elegant taper, narrow neck
        "profile": [
            (0.0,  0.0),  (0.5,  0.04), (0.55, 0.12), (0.45, 0.3),
            (0.55, 0.6),  (0.75, 0.9),  (0.85, 1.2),  (0.8,  1.55),
            (0.55, 1.85), (0.3,  2.1),  (0.2,  2.3),  (0.22, 2.4)
        ],
        "segments": 64,
    },
    "chess pawn": {
        # Round head, narrow neck, wider body, flat base
        "profile": [
            (0.0,  0.0),  (0.45, 0.03), (0.5,  0.1),  (0.4,  0.2),
            (0.25, 0.35), (0.2,  0.5),  (0.22, 0.65), (0.35, 0.75),
            (0.45, 0.85), (0.5,  1.0),  (0.48, 1.15), (0.45, 1.25),
            (0.35, 1.35), (0.2,  1.4),  (0.0,  1.45)
        ],
        "segments": 48,
    },
    "rocket": {
        # Pointed nose cone, cylindrical body, wider engine bell at base
        "profile": [
            (0.0,  0.0),  (0.0,  0.05), (0.05, 0.2),  (0.15, 0.5),
            (0.25, 0.9),  (0.3,  1.4),  (0.3,  2.0),  (0.3,  2.6),
            (0.3,  3.0),  (0.35, 3.1),  (0.5,  3.2),  (0.55, 3.3),
            (0.5,  3.35)
        ],
        "segments": 48,
    },
    "teapot": {
        # Round belly, small flat top for lid, narrow spout base
        "profile": [
            (0.0,  0.0),  (0.35, 0.04), (0.6,  0.2),  (0.85, 0.55),
            (1.0,  0.95), (1.05, 1.35), (0.95, 1.7),  (0.75, 1.95),
            (0.5,  2.1),  (0.3,  2.18), (0.25, 2.22)
        ],
        "segments": 64,
    },
}


def _is_cone_like(profile: list) -> bool:
    """
    Return True if the profile lacks a proper belly-and-neck shape.
    A real vase / bowl must:
      1. Have a clear belly (max radius) that is NOT in the top 30% of the height
      2. Have a neck narrower than 65% of the belly radius after the belly
    Catches both strict cones AND funnel shapes (wide-at-top, no neck).
    """
    if len(profile) < 4:
        return True

    radii  = [r for r, h in profile]
    max_r  = max(radii)
    min_r  = min(radii)

    if (max_r - min_r) < 0.2:
        return True  # almost flat / cylinder

    # Where is the belly?
    belly_idx = radii.index(max_r)
    total     = len(radii)

    # Belly must exist in the LOWER 70% of the profile
    if belly_idx >= int(total * 0.7):
        return True  # belly is at or near the top → funnel shape

    # After the belly there must be a real narrowing (neck < 65% of belly)
    after_belly = radii[belly_idx:]
    if not after_belly:
        return True
    min_after = min(after_belly)
    if min_after > max_r * 0.65:
        return True  # no real neck — shape stays wide all the way up

    return False


def _get_fallback(description: str) -> dict | None:
    """Return a hardcoded fallback profile if the description matches a known shape.
    Checks longest keys first so 'wine glass' matches before 'wine'."""
    desc = description.lower()
    for key in sorted(FALLBACK_PROFILES.keys(), key=len, reverse=True):
        if key in desc:
            data = FALLBACK_PROFILES[key]
            print(f"[shape_tool] Using hardcoded fallback profile for '{key}'")
            return {"shape_type": "revolution", "name": key, **data}
    return None


# ── System prompt: asks LLM for a JSON shape definition ──────────────────────
SHAPE_JSON_PROMPT = """
You are a 3D shape designer. Given a description, output a JSON object that defines the shape.

For objects that are rotationally symmetric (vases, bowls, bottles, cups, pots, columns, jars):
  Use shape_type "revolution" with a "profile" list of [radius, height] pairs.
  The profile is swept 360 degrees to create the shape.
  CRITICAL: Make the radius vary realistically — NOT linearly.
    - A vase: wide belly, narrow neck, slight rim flare
    - A bowl: wide at top, curves to small base
    - A bottle: narrow base, wide belly, narrow neck, narrow mouth

For everything else (chairs, tables, brackets, animals, buildings):
  Use shape_type "freeform" with a plain English "description" field.

Return ONLY raw JSON, no explanation, no markdown.

Examples:

Input: "a curved vase"
Output: {
  "shape_type": "revolution",
  "name": "curved vase",
  "segments": 64,
  "profile": [
    [0.0, 0.0], [0.5, 0.1], [0.9, 0.5], [1.1, 1.0],
    [1.2, 1.5], [1.0, 2.0], [0.6, 2.5], [0.45, 2.8], [0.5, 3.0]
  ]
}

Input: "a wide salad bowl"
Output: {
  "shape_type": "revolution",
  "name": "salad bowl",
  "segments": 64,
  "profile": [
    [0.0, 0.0], [0.2, 0.05], [0.6, 0.3], [1.0, 0.7],
    [1.3, 1.1], [1.5, 1.5], [1.6, 1.8]
  ]
}

Input: "a wooden chair"
Output: {
  "shape_type": "freeform",
  "name": "wooden chair",
  "description": "a wooden chair with four legs, a flat seat, and a straight back with two horizontal rails"
}
""".strip()


def get_shape_definition(user_description: str) -> dict | None:
    """
    Convert a plain-English description into a shape definition dict.

    For known shapes (vase, bowl, bottle, cup) uses a hardcoded reliable profile
    directly — no LLM needed, always consistent.
    For everything else asks the LLM, then validates the result.

    Returns a dict with shape_type, name, and either profile (revolution) or
    description (freeform). Returns None on failure.
    """
    # Fast path — known shapes always use the hardcoded profile
    known = _get_fallback(user_description)
    if known:
        return known

    raw = llm_tool.ask(
        prompt=f"Describe this as a 3D shape definition: {user_description}",
        system=SHAPE_JSON_PROMPT,
        model=SMART_MODEL,
        temperature=0.1,
        max_tokens=400,
        expect_json=True,
    )

    if raw.startswith("[llm_tool]"):
        print(f"[shape_tool] LLM error: {raw}")
        return None

    # Strip markdown fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[1:end])

    try:
        data = json.loads(text)
        print(f"[shape_tool] Shape type: {data.get('shape_type')} | Name: {data.get('name')}")

        # Validate revolution profiles — reject cone-like results and fall back
        if data.get("shape_type") == "revolution":
            profile = data.get("profile", [])
            if _is_cone_like(profile):
                print(f"[shape_tool] Profile looks cone-like — trying fallback")
                fallback = _get_fallback(user_description)
                if fallback:
                    return fallback
                # Re-ask with a more explicit prompt if no hardcoded fallback exists
                print(f"[shape_tool] No hardcoded fallback, re-asking LLM with stricter prompt...")
                return _retry_with_strict_prompt(user_description)

        return data
    except json.JSONDecodeError as e:
        print(f"[shape_tool] JSON parse error: {e} | Raw: {raw[:200]}")
        return _get_fallback(user_description)


def _retry_with_strict_prompt(description: str) -> dict | None:
    """
    Second attempt with a very explicit prompt when the first try came out cone-like.
    Forces the LLM to include a belly (radius goes up then comes back down).
    """
    strict_prompt = (
        f"Create a revolution profile for: {description}\n\n"
        "RULES — your profile MUST:\n"
        "1. Start at radius 0 at height 0\n"
        "2. Increase in radius to form a WIDE BELLY in the middle\n"
        "3. Then DECREASE in radius toward the top (narrow neck)\n"
        "4. Have at least 8 points\n"
        "5. The max radius must be at least 2x the top radius\n\n"
        "Return ONLY this JSON:\n"
        '{"shape_type":"revolution","name":"<name>","segments":64,"profile":[[r,h],...]}'
    )
    raw = llm_tool.ask(
        prompt=strict_prompt,
        system="Return only raw JSON, no markdown.",
        model=SMART_MODEL,
        temperature=0.1,
        max_tokens=400,
        expect_json=True,
    )
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[1:end])
    try:
        data = json.loads(text)
        print(f"[shape_tool] Retry result: {len(data.get('profile', []))} points")
        return data
    except Exception:
        return None


def profile_to_threejs(profile: list, segments: int = 64) -> str:
    """
    Convert a [(radius, height), ...] profile into Three.js LatheGeometry code.
    Returns the JavaScript string to inject into the HTML template.
    """
    points_js = ",\n    ".join(
        f"new THREE.Vector2({r}, {h})" for r, h in profile
    )
    return f"""
  const points = [
    {points_js}
  ];
  const geo  = new THREE.LatheGeometry(points, {segments});
  const mesh = new THREE.Mesh(geo, material);
  return mesh;
""".strip()


def profile_to_blender(profile: list, name: str, segments: int = 64) -> str:
    """
    Convert a [(radius, height), ...] profile into a complete Blender bpy script.
    Uses the bmesh ring approach — same math as LatheGeometry.
    """
    # Format profile as a Python list literal for injection into the script
    profile_str = ",\n    ".join(f"({r}, {h})" for r, h in profile)
    safe_name   = name.replace('"', '').replace("'", "")

    return f'''import bpy, bmesh, math

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# Profile: same (radius, height) points used in the HTML preview
profile = [
    {profile_str}
]
segments = {segments}

mesh = bpy.data.meshes.new("{safe_name}Mesh")
obj  = bpy.data.objects.new("{safe_name}", mesh)
bpy.context.collection.objects.link(obj)

bm = bmesh.new()
verts_rings = []
for r, h in profile:
    ring = []
    for i in range(segments):
        angle = 2 * math.pi * i / segments
        x = r * math.cos(angle)
        y = r * math.sin(angle)
        ring.append(bm.verts.new((x, y, h)))
    verts_rings.append(ring)

# Connect rings with quads
for i in range(len(verts_rings) - 1):
    for j in range(segments):
        a = verts_rings[i][j]
        b = verts_rings[i][(j + 1) % segments]
        c = verts_rings[i + 1][(j + 1) % segments]
        d = verts_rings[i + 1][j]
        bm.faces.new([a, b, c, d])

# Close the bottom
bm.faces.new(verts_rings[0])

bm.to_mesh(mesh)
bm.free()
mesh.update()

for p in mesh.polygons:
    p.use_smooth = True

mod = obj.modifiers.new(name="Subdiv", type="SUBSURF")
mod.levels = 2

bpy.context.view_layer.objects.active = obj
obj.select_set(True)
'''
