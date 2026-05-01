# Robot Arm Setup (MuJoCo Franka Panda)

The `move_arm` action drives a simulated Franka Emika Panda inside MuJoCo. The
sim runs in its own Python venv because MuJoCo doesn't have wheels for Python
3.14 (which is what the main Jarvis venv uses).

## One-time setup

### 1. Create the MuJoCo venv

```bash
python3.10 -m venv ~/mujoco-venv
~/mujoco-venv/bin/pip install --upgrade pip
~/mujoco-venv/bin/pip install -r requirements-mujoco.txt
```

After this, `~/mujoco-venv/bin/mjpython` should exist. The client launches the
server through that binary — `mjpython` is required on macOS because the
passive viewer must run on the main thread.

### 2. Get the Franka Panda model

```bash
mkdir -p ~/Downloads
cd ~/Downloads
git clone https://github.com/google-deepmind/mujoco_menagerie.git
```

The server expects the scene at:

```
~/Downloads/mujoco_menagerie/franka_emika_panda/scene.xml
```

If you put it somewhere else, edit `PANDA_XML` at the top of
`tools/arm_sim_server.py`.

## How it works

```
┌────────────────────┐  TCP 9877  ┌──────────────────────┐
│ Jarvis web UI      │ ─────────▶ │ arm_sim_server.py    │
│  └─ arm_agent.py   │   JSON     │  (in ~/mujoco-venv)  │
│     └─ arm_sim_    │            │  + passive viewer    │
│        client.py   │ ◀───────── │  + Jacobian IK       │
└────────────────────┘            └──────────────────────┘
```

- `arm_sim_client.py` runs in the main Jarvis venv and only uses the standard
  library.
- It auto-launches the server via `mjpython tools/arm_sim_server.py` if the
  socket isn't responding (same pattern as `blender_mcp_tool.launch_blender`).
- The server exposes five JSON commands: `ping`, `home`, `open_gripper`,
  `close_gripper`, `move_to`.
- IK is a damped-least-squares Jacobian pseudoinverse (~30 lines, no extra
  deps) — accurate enough for the block-pick demo, will get replaced when we
  need real trajectory tracking.

## Test it from the Jarvis web UI

Start Jarvis as usual:

```bash
./jarvis-web
```

Then in the chat:

> Pick up the red block

The first call takes ~10–20 seconds to spin up the MuJoCo viewer. Subsequent
calls are instant because the server stays running. You should see a Blender-
style window pop up showing the Panda swinging through the pick sequence.

Other commands you can try right now:

> Place at home
>
> Point at the green block
>
> Move arm to home

Known target names (hardcoded in `agents/arm_agent.py`): `red block`,
`blue block`, `green block`, `home`. Once YOLO + a camera are wired up,
we'll swap the lookup table for a real perception call.

## Troubleshooting

**"mjpython not found at ~/mujoco-venv/bin/mjpython"** — venv wasn't created
with Python 3.10, or `mujoco` wasn't installed. Re-run step 1.

**`mjpython: bad interpreter: /Users/.../Personal: no such file or directory`** —
this happens if MuJoCo was first installed into a venv whose path contains a
space (e.g. `~/Personal Project/...`). The macOS kernel can't parse a shebang
with spaces, and pip stamps `mjpython`'s shebang with the original venv's
Python path. Fix: recreate `~/mujoco-venv` from scratch using a Python whose
own path has no spaces (the system / Homebrew Python is fine), then reinstall:

```bash
rm -rf ~/mujoco-venv
/opt/homebrew/bin/python3.10 -m venv ~/mujoco-venv
~/mujoco-venv/bin/pip install -r requirements-mujoco.txt
```

**"Franka Panda model not found"** — `mujoco_menagerie` isn't where the server
expects it. Either clone it as in step 2, or edit `PANDA_XML` in
`tools/arm_sim_server.py`.

**Viewer opens then immediately closes** — that's normal if you Ctrl-C the
server; just close the window if you want to stop it. The sim runs at the
model's default timestep and should look smooth.

**Arm can't reach the target** — workspace coords in `TARGETS` may be outside
the Panda's reach. The Franka Panda has roughly 0.85 m reach from the base; if
you're seeing residual errors > 1 cm, the target is probably out of envelope.
