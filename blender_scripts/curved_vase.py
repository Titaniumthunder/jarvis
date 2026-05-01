import bpy, bmesh, math

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# Vase profile: (radius, height) — radius varies to create belly + narrow neck
profile = [
    (0.0,  0.0),   # bottom centre
    (0.5,  0.1),   # bottom edge
    (0.9,  0.5),   # lower body widens
    (1.0,  1.0),   # belly start
    (1.1,  1.5),   # widest point
    (0.95, 2.0),   # upper body
    (0.6,  2.5),   # neck narrows
    (0.45, 2.8),   # neck
    (0.5,  3.0),   # rim flares slightly
]
segments = 48

mesh = bpy.data.meshes.new("VaseMesh")
obj  = bpy.data.objects.new("Vase", mesh)
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

for i in range(len(verts_rings) - 1):
    for j in range(segments):
        a = verts_rings[i][j]
        b = verts_rings[i][(j+1) % segments]
        c = verts_rings[i+1][(j+1) % segments]
        d = verts_rings[i+1][j]
        bm.faces.new([a, b, c, d])

bm.faces.new(verts_rings[0])   # close bottom

bm.to_mesh(mesh)
bm.free()
mesh.update()

for p in mesh.polygons:
    p.use_smooth = True

mod = obj.modifiers.new(name="Subdiv", type="SUBSURF")
mod.levels = 2

bpy.context.view_layer.objects.active = obj
obj.select_set(True)