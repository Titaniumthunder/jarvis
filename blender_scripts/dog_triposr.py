import bpy

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

bpy.ops.wm.obj_import(filepath=r"/Users/alexsalamati/Personal Project/Desktop assistant/jarvis/shape_e_output/dog_triposr.obj")

obj = bpy.context.selected_objects[0] if bpy.context.selected_objects else None
if obj:
    # Centre to world origin
    bpy.ops.object.origin_set(type='GEOMETRY_ORIGIN', center='BOUNDS')
    obj.location = (0, 0, 0)

    # Smooth shading
    bpy.ops.object.shade_smooth()

    # Light remesh to clean up the mesh
    mod = obj.modifiers.new(name="Remesh", type="REMESH")
    mod.mode = 'SMOOTH'
    mod.octree_depth = 7
    mod.use_smooth_shade = True

    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)