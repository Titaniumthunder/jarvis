import bpy

def _autoconnect():
    try:
        # Set port to 9876 (default)
        bpy.context.scene.blendermcp_port = 9876
        bpy.ops.blendermcp.start_server()
        print("[jarvis] BlenderMCP auto-connected on port 9876")
    except Exception as e:
        print(f"[jarvis] BlenderMCP auto-connect failed: {e}")
    return None  # run once, don't repeat

bpy.app.timers.register(_autoconnect, first_interval=1.5)