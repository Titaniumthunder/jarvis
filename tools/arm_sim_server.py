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
    {"cmd": "move_to", "xyz": [x, y, z]}

Replies are JSON: {"status": "success"} or {"status": "error", "message": "..."}.
"""

import json
import pathlib
import socket
import socketserver
import threading
import time

import mujoco
import mujoco.viewer
import numpy as np

HOST = "127.0.0.1"
PORT = 9877

PANDA_XML = pathlib.Path.home() / "Downloads" / "mujoco_menagerie" / "franka_emika_panda" / "scene.xml"

# Names defined in the Franka Panda menagerie model.
EE_BODY_NAME = "hand"
ARM_JOINT_NAMES = [f"joint{i}" for i in range(1, 8)]
GRIPPER_ACTUATOR_NAME = "actuator8"
HOME_QPOS = np.array([0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785])

# IK tuning knobs.
IK_MAX_ITERS = 200
IK_TOL = 1e-3
IK_DAMPING = 1e-2
IK_STEP = 0.5


# ─── Sim state ────────────────────────────────────────────────────────────────

class SimState:
    """All MuJoCo state lives here. Accessed from both viewer and command threads."""

    def __init__(self):
        if not PANDA_XML.exists():
            raise RuntimeError(
                f"Franka Panda model not found at {PANDA_XML}. "
                "Clone github.com/google-deepmind/mujoco_menagerie into ~/Downloads/."
            )

        self.model = mujoco.MjModel.from_xml_path(str(PANDA_XML))
        self.data = mujoco.MjData(self.model)

        self.ee_body_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, EE_BODY_NAME)
        if self.ee_body_id < 0:
            raise RuntimeError(f"EE body '{EE_BODY_NAME}' not found in model.")

        self.arm_qpos_addrs = []
        for name in ARM_JOINT_NAMES:
            jid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, name)
            if jid < 0:
                raise RuntimeError(f"Arm joint '{name}' not found in model.")
            self.arm_qpos_addrs.append(self.model.jnt_qposadr[jid])

        self.gripper_act_id = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_ACTUATOR, GRIPPER_ACTUATOR_NAME
        )

        self.lock = threading.Lock()
        self._home_internal()

    def _home_internal(self):
        for qpos_addr, target in zip(self.arm_qpos_addrs, HOME_QPOS):
            self.data.qpos[qpos_addr] = target
        if self.gripper_act_id >= 0:
            self.data.ctrl[self.gripper_act_id] = 255  # open
        mujoco.mj_forward(self.model, self.data)

    # ─── Commands ─────────────────────────────────────────────────────────────

    def home(self):
        with self.lock:
            self._home_internal()

    def set_gripper(self, value: float):
        if self.gripper_act_id < 0:
            return
        with self.lock:
            self.data.ctrl[self.gripper_act_id] = value
            mujoco.mj_forward(self.model, self.data)

    def move_to(self, target_xyz):
        """Jacobian-pseudoinverse IK toward target_xyz, applied to the EE body."""
        target = np.asarray(target_xyz, dtype=np.float64)
        with self.lock:
            jacp = np.zeros((3, self.model.nv))
            jacr = np.zeros((3, self.model.nv))
            for _ in range(IK_MAX_ITERS):
                mujoco.mj_forward(self.model, self.data)
                ee_pos = self.data.xpos[self.ee_body_id]
                err = target - ee_pos
                if np.linalg.norm(err) < IK_TOL:
                    break

                mujoco.mj_jacBody(self.model, self.data, jacp, jacr, self.ee_body_id)
                # Restrict to the seven arm DOFs.
                jac_arm = jacp[:, :7]
                # Damped-least-squares pseudoinverse for numerical stability near singularities.
                jjt = jac_arm @ jac_arm.T
                damped = jjt + (IK_DAMPING ** 2) * np.eye(3)
                dq = jac_arm.T @ np.linalg.solve(damped, err)

                for i, qpos_addr in enumerate(self.arm_qpos_addrs):
                    self.data.qpos[qpos_addr] += IK_STEP * dq[i]

            mujoco.mj_forward(self.model, self.data)
            final_err = float(np.linalg.norm(target - self.data.xpos[self.ee_body_id]))
            return final_err


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
        if name == "ping":
            return {"status": "success", "message": "pong"}
        if name == "home":
            SIM.home()
            return {"status": "success"}
        if name == "open_gripper":
            SIM.set_gripper(255)
            return {"status": "success"}
        if name == "close_gripper":
            SIM.set_gripper(0)
            return {"status": "success"}
        if name == "move_to":
            xyz = cmd.get("xyz")
            if not (isinstance(xyz, list) and len(xyz) == 3):
                return {"status": "error", "message": "xyz must be [x, y, z]"}
            err = SIM.move_to(xyz)
            return {"status": "success", "residual": err}
        return {"status": "error", "message": f"unknown cmd '{name}'"}


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
            with SIM.lock:
                mujoco.mj_step(SIM.model, SIM.data)
            viewer.sync()
            sleep = SIM.model.opt.timestep - (time.time() - step_start)
            if sleep > 0:
                time.sleep(sleep)


if __name__ == "__main__":
    main()
