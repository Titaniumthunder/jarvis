import bpy, bmesh, math

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# Profile: same (radius, height) points used in the HTML preview
profile = [
    (0.0, 0.0),
    (0.55, 0.03),
    (0.6, 0.08),
    (0.65, 0.5),
    (0.65, 1.0),
    (0.65, 1.4),
    (0.65, 1.6),
    (0.68, 1.7),
    (0.65, 1.75)
]
segments = 48

mesh = bpy.data.meshes.new("mugMesh")
obj  = bpy.data.objects.new("mug", mesh)
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
