import bpy
import bmesh
import math

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

mesh = bpy.data.meshes.new("Vase")
obj = bpy.data.objects.new("Vase", mesh)
bpy.context.collection.objects.link(obj)
bpy.context.view_layer.objects.active = obj
obj.select_set(True)

bm = bmesh.new()

# Vase profile: (radius, z) from base to rim
profile = [
    (0.20, 0.00),   # base center
    (0.24, 0.03),   # base edge
    (0.26, 0.08),   # lower foot
    (0.38, 0.26),   # body widens
    (0.50, 0.48),   # mid body
    (0.57, 0.68),   # widest
    (0.54, 0.88),   # upper body tapering
    (0.42, 1.08),   # shoulder
    (0.27, 1.26),   # neck start
    (0.20, 1.42),   # narrowest neck
    (0.22, 1.52),   # neck top
    (0.29, 1.60),   # rim flare
    (0.31, 1.65),   # rim lip
]

SEG = 64

# Build vertex rings along the profile
rings = []
for r, z in profile:
    ring = []
    for i in range(SEG):
        a = 2.0 * math.pi * i / SEG
        ring.append(bm.verts.new((r * math.cos(a), r * math.sin(a), z)))
    rings.append(ring)

# Quad faces between adjacent rings
for i in range(len(rings) - 1):
    lo, hi = rings[i], rings[i + 1]
    for j in range(SEG):
        k = (j + 1) % SEG
        bm.faces.new([lo[j], lo[k], hi[k], hi[j]])

# Bottom cap (triangles fanning from center)
bc = bm.verts.new((0.0, 0.0, 0.0))
for j in range(SEG):
    bm.faces.new([bc, rings[0][(j + 1) % SEG], rings[0][j]])

# Top cap (triangles fanning from center)
tc = bm.verts.new((0.0, 0.0, profile[-1][1]))
for j in range(SEG):
    bm.faces.new([tc, rings[-1][j], rings[-1][(j + 1) % SEG]])

bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
bm.to_mesh(mesh)
bm.free()

mesh.update()
bpy.ops.object.shade_smooth()

# Ceramic blue glaze material
mat = bpy.data.materials.new(name="VaseGlaze")
mat.use_nodes = True
nodes = mat.node_tree.nodes
bsdf = nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.12, 0.32, 0.72, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.18
    bsdf.inputs["Metallic"].default_value = 0.0

obj.data.materials.append(mat)

bpy.context.view_layer.objects.active = obj
bpy.ops.object.select_all(action='DESELECT')
