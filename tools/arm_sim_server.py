"""arm_sim_server.py — MuJoCo Franka Panda simulator.

Runs in a separate venv (~/mujoco-venv with Python 3.10) because MuJoCo wheels
don't exist for Python 3.14, which is what the main Jarvis venv uses.

Launch this with mjpython, NOT python — the passive viewer needs the main thread:

    ~/mujoco-venv/bin/mjpython tools/arm_sim_server.py

Listens on TCP 127.0.0.1:9877 for newline-delimited JSON commands:

    {"cmd": "ping"}
    {"cmd": "home"}
    {"cmd": "open_gripper"}
    {"cmd": "close_gripper"}
    {"cmd": "move_to", "xyz": [x, y, z], "duration_sec": 1.0}

Replies are JSON: {"status": "success"} or {"status": "error", "message": "..."}.
"""

import json
import pathlib
import socketserver
import sys
import tempfile
import threading
import time

import mujoco
import mujoco.viewer
import numpy as np

# tools.paths lives in the main Jarvis tree; add it to sys.path so the script
# can be launched directly with mjpython without needing the main venv on PYTHONPATH.
_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
from tools import paths  # noqa: E402

HOST = "127.0.0.1"
PORT = 9877

PANDA_SCENE_PATH = pathlib.Path.home() / "Downloads" / "mujoco_menagerie" / "franka_emika_panda" / "scene.xml"
JARVIS_SCENE_TEMPLATE = paths.JARVIS_ROOT / "tools" / "jarvis_scene.xml"

# Names defined in the Franka Panda menagerie model.
EE_BODY_NAME = "hand"
ARM_JOINT_NAMES = [f"joint{i}" for i in range(1, 8)]
ARM_ACTUATOR_NAMES = [f"actuator{i}" for i in range(1, 8)]
GRIPPER_ACTUATOR_NAME = "actuator8"
HOME_QPOS = np.array([0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785])

# IK tuning knobs. Position-only 3-DOF IK — gripper orientation is left to the
# arm's redundancy. Orientation-aware grasping is replaced by a magnetic grasp
# that attaches the closest cube on close_gripper, so the wrist angle doesn't
# need to be exactly down.
IK_MAX_ITERS = 50
IK_TOL = 1e-3
IK_DAMPING = 1e-2
IK_STEP = 0.5

DEFAULT_DURATION_SEC = 1.0


def _check_scene_files():
    if not JARVIS_SCENE_TEMPLATE.exists():
        raise RuntimeError(f"Jarvis scene template missing at {JARVIS_SCENE_TEMPLATE}.")
    if not PANDA_SCENE_PATH.exists():
        raise RuntimeError(
            f"Franka Panda model not found at {PANDA_SCENE_PATH}. "
            "Clone github.com/google-deepmind/mujoco_menagerie into ~/Downloads/."
        )


# ─── Sim state ────────────────────────────────────────────────────────────────

class SimState:
    """All MuJoCo state lives here. Accessed from both viewer and command threads."""

    def __init__(self):
        # Copy the wrapper into the franka_emika_panda directory before loading.
        # MuJoCo resolves <compiler meshdir="assets"/> (declared inside panda.xml)
        # against the *top-level* XML file's directory, not against the file that
        # contains the compiler tag. So the wrapper has to live next to scene.xml,
        # otherwise the mesh paths come out wrong (link6.stl can't be opened).
        _check_scene_files()
        scene_dir = PANDA_SCENE_PATH.parent
        with tempfile.NamedTemporaryFile(
            mode="w",
            prefix="jarvis_scene_",
            suffix=".xml",
            dir=str(scene_dir),
            delete=False,
            encoding="utf-8",
        ) as tmp:
            tmp.write(JARVIS_SCENE_TEMPLATE.read_text(encoding="utf-8"))
            tmp_path = tmp.name
        try:
            self.model = mujoco.MjModel.from_xml_path(tmp_path)
        finally:
            pathlib.Path(tmp_path).unlink(missing_ok=True)

        self.data = mujoco.MjData(self.model)

        self.ee_body_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, EE_BODY_NAME)
        if self.ee_body_id < 0:
            raise RuntimeError(f"EE body '{EE_BODY_NAME}' not found in model.")

        self.arm_qpos_addrs = []
        self.arm_dof_addrs = []
        for name in ARM_JOINT_NAMES:
            jid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, name)
            if jid < 0:
                raise RuntimeError(f"Arm joint '{name}' not found in model.")
            self.arm_qpos_addrs.append(self.model.jnt_qposadr[jid])
            self.arm_dof_addrs.append(self.model.jnt_dofadr[jid])

        self.arm_actuator_ids = []
        for name in ARM_ACTUATOR_NAMES:
            aid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
            if aid < 0:
                raise RuntimeError(f"Arm actuator '{name}' not found in model.")
            self.arm_actuator_ids.append(aid)

        self.gripper_act_id = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_ACTUATOR, GRIPPER_ACTUATOR_NAME
        )

        # Magnetic grasp: track which cube (if any) is welded to the gripper
        # plus the offset from the EE to the cube at the moment of grasp.
        self.cube_body_ids = {}
        for name in ("red_block", "blue_block", "green_block"):
            bid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, name)
            if bid >= 0:
                self.cube_body_ids[name] = bid
        self.held_cube = None
        self._held_offset = None
        self.GRASP_RADIUS = 0.15  # 15 cm — extra-generous capture for the demo

        # Two locks: data_lock for short critical sections (so the viewer keeps
        # rendering between substeps), move_lock to serialize whole moves.
        self.data_lock = threading.Lock()
        self.move_lock = threading.Lock()

        self.reset_cubes()
        self._home_internal()

    def _home_internal(self):
        for qpos_addr, target in zip(self.arm_qpos_addrs, HOME_QPOS):
            self.data.qpos[qpos_addr] = target
        for dof_addr in self.arm_dof_addrs:
            self.data.qvel[dof_addr] = 0.0
        for aid, target in zip(self.arm_actuator_ids, HOME_QPOS):
            self.data.ctrl[aid] = target
        if self.gripper_act_id >= 0:
            self.data.ctrl[self.gripper_act_id] = 255  # open
        mujoco.mj_forward(self.model, self.data)

    def reset_cubes(self):
        """Re-spawn all cubes at random reachable positions, clearing held state."""
        import math
        import random
        SPAWN_X_RANGE = (0.35, 0.55)
        SPAWN_Y_RANGE = (-0.30, 0.00)
        SPAWN_Z = 0.025
        MIN_SEPARATION = 0.10
        TARGET_XY = (0.4, 0.15)
        MIN_TARGET_DIST = 0.12

        with self.data_lock:
            # Release any held cube first
            self.held_cube = None
            self._held_offset = None

            spawned = []
            for name, bid in self.cube_body_ids.items():
                x = y = 0.0
                for _ in range(100):
                    x = random.uniform(*SPAWN_X_RANGE)
                    y = random.uniform(*SPAWN_Y_RANGE)
                    if math.hypot(x - TARGET_XY[0], y - TARGET_XY[1]) < MIN_TARGET_DIST:
                        continue
                    if any(math.hypot(x - px, y - py) < MIN_SEPARATION for px, py in spawned):
                        continue
                    break
                spawned.append((x, y))
                joint_id = self.model.body_jntadr[bid]
                qpos_addr = self.model.jnt_qposadr[joint_id]
                qvel_addr = self.model.jnt_dofadr[joint_id]
                # Set position + identity quaternion, zero velocity
                self.data.qpos[qpos_addr:qpos_addr+7] = [x, y, SPAWN_Z, 1, 0, 0, 0]
                self.data.qvel[qvel_addr:qvel_addr+6] = 0.0
                print(f"[arm_sim] Spawned {name} at x={x:+.3f} y={y:+.3f}")

            mujoco.mj_forward(self.model, self.data)

    def state_summary(self) -> str:
        """Multi-line string with TCP, cube positions, distances, held."""
        import numpy as np
        lines = []
        with self.data_lock:
            ee_pos = self.data.xpos[self.ee_body_id].copy()
            lines.append(f"  TCP: x={ee_pos[0]:+.3f} y={ee_pos[1]:+.3f} z={ee_pos[2]:+.3f}")
            for name, bid in self.cube_body_ids.items():
                p = self.data.xpos[bid].copy()
                d = float(np.linalg.norm(ee_pos - p))
                lines.append(
                    f"  {name}: x={p[0]:+.3f} y={p[1]:+.3f} z={p[2]:+.3f} "
                    f"| dist_to_TCP={d:.3f}m"
                )
            held = self.held_cube if self.held_cube else "none"
            lines.append(f"  gripper: held={held}")
        return "\n".join(lines)

    # ─── Commands ─────────────────────────────────────────────────────────────

    def home(self):
        with self.move_lock, self.data_lock:
            self._home_internal()

    def set_gripper(self, value: float):
        # Gripper goes through ctrl, not qpos — no interpolation needed and
        # we don't want it to fight whatever the arm is doing.
        if self.gripper_act_id < 0:
            return
        with self.data_lock:
            self.data.ctrl[self.gripper_act_id] = value

    # ─── Magnetic grasp ───────────────────────────────────────────────────────

    def attach_closest_cube(self):
        """Find closest cube within GRASP_RADIUS of the TCP and attach it."""
        with self.data_lock:
            if self.held_cube is not None:
                return  # already holding something
            ee_pos = self.data.xpos[self.ee_body_id].copy()
            best_name, best_dist = None, self.GRASP_RADIUS
            for name, bid in self.cube_body_ids.items():
                cube_pos = self.data.xpos[bid]
                dist = float(np.linalg.norm(ee_pos - cube_pos))
                if dist < best_dist:
                    best_name, best_dist = name, dist
            if best_name is not None:
                self.held_cube = best_name
                bid = self.cube_body_ids[best_name]
                # Fixed visual offset: cube appears centered between the gripper
                # fingertips (~10cm below the hand TCP). This decouples the demo's
                # visual appearance from the IK's actual converged pose, so the cube
                # always looks tightly gripped regardless of orientation residual.
                self._held_offset = np.array([0.0, 0.0, -0.10])
                print(f"[arm_sim] Attached {best_name} "
                      f"(actual_dist={best_dist:.3f}m, visual_offset=fixed_-10cm)")
            else:
                print(f"[arm_sim] No cube within {self.GRASP_RADIUS}m of TCP")

    def release_cube(self):
        with self.data_lock:
            if self.held_cube is not None:
                print(f"[arm_sim] Released {self.held_cube}")
            self.held_cube = None
            self._held_offset = None

    def move_to(self, target_xyz, duration_sec: float = DEFAULT_DURATION_SEC):
        """Smoothly drive the EE to target_xyz over duration_sec.

        Strategy: solve Jacobian-pseudoinverse IK on a temporary qpos buffer
        (snapshot → mutate → restore so live qpos never teleports), then ramp
        the position-actuator setpoints (`data.ctrl`) from q_start to q_target
        one timestep at a time. The viewer's main loop owns `mj_step`; we just
        write ctrl and sleep, so the position actuators do the actual tracking.
        """
        target = np.asarray(target_xyz, dtype=np.float64)

        with self.move_lock:
            # Solve IK under data_lock, then restore live qpos before releasing.
            with self.data_lock:
                q_start = np.array([self.data.qpos[a] for a in self.arm_qpos_addrs])
                q_target = self._solve_ik(target)
                for i, qpos_addr in enumerate(self.arm_qpos_addrs):
                    self.data.qpos[qpos_addr] = q_start[i]
                mujoco.mj_forward(self.model, self.data)

            # Ramp ctrl from q_start to q_target, one timestep per write.
            # Don't call mj_step here — the viewer thread is doing it.
            timestep = float(self.model.opt.timestep)
            n_steps = max(2, int(duration_sec / timestep))
            traj = np.linspace(q_start, q_target, n_steps)

            for q in traj:
                with self.data_lock:
                    for i, aid in enumerate(self.arm_actuator_ids):
                        self.data.ctrl[aid] = q[i]
                time.sleep(timestep)

            with self.data_lock:
                return float(np.linalg.norm(target - self.data.xpos[self.ee_body_id]))

    # ─── IK helper ────────────────────────────────────────────────────────────

    def _solve_ik(self, target):
        """6-DOF damped-least-squares Jacobian IK with a SOFT orientation goal.

        Position dominates the cost; orientation (gripper z pointing world -Z)
        is downweighted so it doesn't fight position convergence. Magnetic
        grasp's 15cm tolerance absorbs the leftover orientation residual.
        """
        ORIENT_WEIGHT = 0.3
        desired_z = np.array([0.0, 0.0, -1.0])

        for _ in range(IK_MAX_ITERS):
            mujoco.mj_forward(self.model, self.data)
            ee_pos = self.data.xpos[self.ee_body_id]
            pos_err = target - ee_pos

            # Orientation error: gripper z-axis should point world -Z
            R = self.data.xmat[self.ee_body_id].reshape(3, 3)
            gripper_z = R[:, 2]
            rot_err = np.cross(gripper_z, desired_z)

            # Loose convergence: 3mm position, ~15deg orientation
            if np.linalg.norm(pos_err) < 3e-3 and np.linalg.norm(rot_err) < 0.25:
                break

            # Downweight orientation by 0.3x so position dominates the cost function.
            err = np.concatenate([pos_err, ORIENT_WEIGHT * rot_err])  # (6,)

            # Need both jacobians for 6-DOF
            jacp = np.zeros((3, self.model.nv))
            jacr = np.zeros((3, self.model.nv))
            mujoco.mj_jacBody(self.model, self.data, jacp, jacr, self.ee_body_id)
            jac_arm = np.vstack([jacp[:, :7], ORIENT_WEIGHT * jacr[:, :7]])   # (6, 7)

            # Solve damped least squares on the 6x6 system
            damped = jac_arm @ jac_arm.T + (IK_DAMPING ** 2) * np.eye(6)
            dq = jac_arm.T @ np.linalg.solve(damped, err)

            for i, qpos_addr in enumerate(self.arm_qpos_addrs):
                self.data.qpos[qpos_addr] += IK_STEP * dq[i]

        return np.array([self.data.qpos[a] for a in self.arm_qpos_addrs])


SIM = SimState()


# ─── TCP server ───────────────────────────────────────────────────────────────

class CommandHandler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            line = self.rfile.readline()
            if not line:
                return
            try:
                cmd = json.loads(line.decode("utf-8").strip())
            except json.JSONDecodeError as e:
                self._send({"status": "error", "message": f"bad json: {e}"})
                return

            self._send(self._dispatch(cmd))
        except Exception as e:
            self._send({"status": "error", "message": str(e)})

    def _send(self, obj):
        self.wfile.write((json.dumps(obj) + "\n").encode("utf-8"))

    def _dispatch(self, cmd: dict) -> dict:
        name = cmd.get("cmd")
        print(f"\n[arm_sim] >>> received: {name}", flush=True)

        if name == "ping":
            return {"status": "success", "message": "pong"}
        if name == "get_cube_pos":
            cube_name = cmd.get("name", "red_block")
            bid = SIM.cube_body_ids.get(cube_name)
            if bid is None:
                return {"status": "error", "message": f"no cube named {cube_name}"}
            with SIM.data_lock:
                p = SIM.data.xpos[bid].copy()
            return {"status": "success", "pos": [float(p[0]), float(p[1]), float(p[2])]}
        if name == "reset_cubes":
            SIM.reset_cubes()
            response = {"status": "success"}
        elif name == "home":
            SIM.home()
            response = {"status": "success"}
        elif name == "open_gripper":
            SIM.set_gripper(255)
            SIM.release_cube()
            response = {"status": "success"}
        elif name == "close_gripper":
            SIM.set_gripper(0)
            SIM.attach_closest_cube()
            response = {"status": "success", "held": SIM.held_cube}
        elif name == "move_to":
            xyz = cmd.get("xyz")
            if not (isinstance(xyz, list) and len(xyz) == 3):
                return {"status": "error", "message": "xyz must be [x, y, z]"}
            duration_sec = float(cmd.get("duration_sec", DEFAULT_DURATION_SEC))
            if duration_sec <= 0:
                return {"status": "error", "message": "duration_sec must be > 0"}
            err = SIM.move_to(xyz, duration_sec=duration_sec)
            print(f"[arm_sim] <<< move_to done (residual={err*1000:.1f}mm)")
            print(SIM.state_summary(), flush=True)
            return {"status": "success", "residual": err}
        else:
            return {"status": "error", "message": f"unknown cmd '{name}'"}

        print(f"[arm_sim] <<< {name} done")
        print(SIM.state_summary(), flush=True)
        return response


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def _serve():
    with ThreadedTCPServer((HOST, PORT), CommandHandler) as srv:
        print(f"[arm_sim] Listening on {HOST}:{PORT}")
        srv.serve_forever()


def main():
    server_thread = threading.Thread(target=_serve, daemon=True)
    server_thread.start()
    print("[arm_sim] Opening passive viewer (close the window to quit).")
    with mujoco.viewer.launch_passive(SIM.model, SIM.data) as viewer:
        while viewer.is_running():
            step_start = time.time()
            with SIM.data_lock:
                mujoco.mj_step(SIM.model, SIM.data)
                # Magnetic-grasp tracker: rigidly slave the held cube to the EE.
                if SIM.held_cube is not None:
                    bid = SIM.cube_body_ids[SIM.held_cube]
                    ee_pos = SIM.data.xpos[SIM.ee_body_id]
                    target_pos = ee_pos + SIM._held_offset
                    joint_id = SIM.model.body_jntadr[bid]
                    qpos_addr = SIM.model.jnt_qposadr[joint_id]
                    qvel_addr = SIM.model.jnt_dofadr[joint_id]
                    # freejoint qpos = [x, y, z, qw, qx, qy, qz]; qvel = [vx,vy,vz,wx,wy,wz]
                    SIM.data.qpos[qpos_addr:qpos_addr + 3] = target_pos
                    SIM.data.qvel[qvel_addr:qvel_addr + 6] = 0.0
            viewer.sync()
            sleep = SIM.model.opt.timestep - (time.time() - step_start)
            if sleep > 0:
                time.sleep(sleep)


if __name__ == "__main__":
    main()
