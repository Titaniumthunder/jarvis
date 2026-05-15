# arm_agent.py
# Drives the simulated Franka Panda arm via tools.arm_sim_client.
# Demo behavior: pick up red, blue, then green blocks (in that order) from
# their random spawn positions and stack them on the target zone.

import time
from tools import arm_sim_client

# Stack location (where blocks are placed in order: bottom -> top).
STACK_XY = [0.4, 0.15]

# TCP Z when releasing each level. Held cube floats 10cm below TCP, so:
#   TCP=0.130 -> cube center at 0.030 (bottom block on floor, ~5mm clearance)
#   TCP=0.180 -> cube center at 0.080 (middle block on top of bottom)
#   TCP=0.230 -> cube center at 0.130 (top block on top of middle)
STACK_TCP_Z = [0.130, 0.180, 0.230]

# High lift clearance — must be above the top of the finished stack (z=0.15)
LIFT_Z = 0.40

# TCP target for grasping a block sitting on the floor:
#   TCP = block_z + this offset.
GRASP_Z_OFFSET = 0.105

# Stacking order: bottom to top.
BLOCKS = ["red_block", "blue_block", "green_block"]


def run(command: dict) -> str:
    if not arm_sim_client.ensure_running():
        return "Could not start the arm simulator. See docs/ARM_SETUP.md."

    # Initialize once at start
    print("[arm_agent] === Initialize ===")
    arm_sim_client.home()
    time.sleep(0.8)
    arm_sim_client.open_gripper()
    time.sleep(0.8)

    for i, block_name in enumerate(BLOCKS):
        print(f"\n[arm_agent] === Block {i + 1}/3: {block_name} ===")
        err = _pick_and_place(block_name, i)
        if err:
            return err

    arm_sim_client.home()
    return "All three blocks stacked on the target."


def reset(command: dict) -> str:
    """Re-spawn blocks at new random positions and return arm to home."""
    if not arm_sim_client.ensure_running():
        return "Could not start the arm simulator."
    arm_sim_client.home()
    time.sleep(0.5)
    arm_sim_client.open_gripper()
    result = arm_sim_client.reset_cubes()
    if result.get("status") != "success":
        return f"Reset failed: {result}"
    return "Blocks reset to new random positions. Ready for the next demo."


def _pick_and_place(block_name: str, stack_idx: int) -> str | None:
    # Find this block's current position
    pos_result = arm_sim_client.get_cube_pos(block_name)
    if pos_result.get("status") != "success":
        return f"Could not locate {block_name}: {pos_result}"
    bx, by, bz = pos_result["pos"]
    print(f"[arm_agent] {block_name} at ({bx:+.3f}, {by:+.3f}, {bz:+.3f})")

    grasp_z = bz + GRASP_Z_OFFSET
    release_z = STACK_TCP_Z[stack_idx]

    # Each step: (label, callable, args)
    moves = [
        ("approach",            arm_sim_client.move_to, ([bx, by, LIFT_Z],)),
        ("descend to grasp",    arm_sim_client.move_to, ([bx, by, grasp_z],)),
        ("close gripper",       arm_sim_client.close_gripper, ()),
        ("lift",                arm_sim_client.move_to, ([bx, by, LIFT_Z],)),
        ("travel to stack",     arm_sim_client.move_to, ([STACK_XY[0], STACK_XY[1], LIFT_Z],)),
        (f"descend to level {stack_idx + 1}",
                                arm_sim_client.move_to, ([STACK_XY[0], STACK_XY[1], release_z],)),
        ("release",             arm_sim_client.open_gripper, ()),
        ("retreat",             arm_sim_client.move_to, ([STACK_XY[0], STACK_XY[1], LIFT_Z],)),
    ]

    for label, fn, args in moves:
        print(f"[arm_agent]   {label}")
        result = fn(*args)
        if isinstance(result, dict) and result.get("status") != "success":
            return f"Arm failed at '{label}' for {block_name}: {result.get('message', result)}"
        time.sleep(0.8)
    return None
