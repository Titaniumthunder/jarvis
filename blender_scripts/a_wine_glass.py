import bpy
import bmesh
import mathutils

# Clear scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# Create new mesh and object
obj = bpy.data.objects.new("WineGlass", None)
bpy.context.collection.objects.link(obj)

# Get the mesh
bm = bmesh.new()
bm.to_mesh(obj.data)
bm.free

# Define wine glass geometry
def add_cylinder(bm, name, location, radius, height):
    v1 = bm.verts.new(location)
    v2 = bm.verts.new((location[0], location[1] + height, location[2]))
    e = bm.edges.new([v1, v2])
    f = bm.faces.new([v1, v2, (location[0], location[1], location[2]), (location[0], location[1] + height, location[2])])
    f.material_index_set(0)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

def add_cone(bm, name, location, radius, height):
    v1 = bm.verts.new(location)
    v2 = bm.verts.new((location[0], location[1] + height, location[2]))
    e = bm.edges.new([v1, v2])
    f = bm.faces.new([v1, v2, (location[0], location[1], location[2]), (location[0], location[1] + height, location[2])])
    f.material_index_set(0)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

def add_curve(bm, name, location, radius):
    v1 = bm.verts.new(location)
    v2 = bm.verts.new((location[0] + mathutils.Vector((math.pi * 2, 0, 0)).normalized() * radius, location[1], location[2]))
    e = bm.edges.new([v1, v2])
    f = bm.faces.new([v1, v2, (location[0], location[1] + radius, location[2]), (location[0] + mathutils.Vector((math.pi * 2, 0, 0)).normalized() * radius, location[1] + radius, location[2])])
    f.material_index_set(0)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

# Add wine glass geometry
add_cylinder(bm, "Cylinder", (0, 0, 0), 1, 5)
add_cone(bm, "Cones", (0, 2.5, 0), 1, 3)

# Create curve for stem
stem_location = mathutils.Vector((0, -2.5, 0))
stem_radius = 0.25
add_curve(bm, "Curve", stem_location, stem_radius)
bm.to_mesh(obj.data)
bm.free

# Add modifiers
obj.modifiers.new(name="Subdivision", type="SUBSURF")
obj.modifiers.new(name="Decimate", type="DECIMATE")

# Set active object and select it
bpy.context.view_layer.objects.active = obj
obj.select_set(True)