import bpy, bmesh, math

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# Profile: same (radius, height) points used in the HTML preview
profile = [
    (0.0, 0.0),
    (0.5, 0.1),
    (0.9, 0.5),
    (1.1, 1.0),
    (1.2, 1.5),
    (1.0, 2.0),
    (0.6, 2.5),
    (0.45, 2.8),
    (0.5, 3.0)
]
segments = 64

mesh = bpy.data.meshes.new("vaseMesh")
obj  = bpy.data.objects.new("vase", mesh)
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
