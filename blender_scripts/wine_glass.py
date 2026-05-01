import bpy, bmesh, math

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# Profile: same (radius, height) points used in the HTML preview
profile = [
    (0.0, 0.0),
    (0.65, 0.02),
    (0.7, 0.06),
    (0.5, 0.12),
    (0.1, 0.22),
    (0.07, 0.6),
    (0.08, 1.0),
    (0.1, 1.15),
    (0.35, 1.35),
    (0.65, 1.65),
    (0.85, 1.95),
    (0.9, 2.25),
    (0.85, 2.5),
    (0.88, 2.6)
]
segments = 64

mesh = bpy.data.meshes.new("wine glassMesh")
obj  = bpy.data.objects.new("wine glass", mesh)
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
