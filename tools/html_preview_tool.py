# html_preview_tool.py
# Generates a Three.js HTML file from LLM-generated geometry code
# and opens it in the browser automatically.
#
# How it works:
#   1. The LLM generates ONLY the Three.js geometry code (the shape itself)
#   2. We inject that code into a full HTML template with:
#      - Three.js loaded from CDN (no install)
#      - OrbitControls for mouse rotation, zoom, pan
#      - Lighting, shadows, dark background
#      - Auto-rotate so it looks alive on first open
#   3. We save the file and call `open` to launch it in the default browser

import os
import subprocess
import pathlib

# Where to save preview files
OUTPUT_DIR = pathlib.Path.home() / "Personal Project" / "Desktop assistant" / "jarvis" / "previews"

# ── HTML template ─────────────────────────────────────────────────────────────
# Uses ES modules (importmap) — the correct approach for Three.js r150+
# {{GEOMETRY_CODE}} is replaced with the LLM's geometry output at runtime
# {{MODEL_NAME}}    is replaced with the model description
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Jarvis Preview — {{MODEL_NAME}}</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { background: #0a0a0f; overflow: hidden; font-family: monospace; }
    #label {
      position: fixed; top: 20px; left: 50%;
      transform: translateX(-50%);
      color: #00aaff; font-size: 14px; letter-spacing: 2px;
      text-transform: uppercase; opacity: 0.8;
      pointer-events: none;
    }
    #hint {
      position: fixed; bottom: 20px; left: 50%;
      transform: translateX(-50%);
      color: #444; font-size: 11px; letter-spacing: 1px;
      pointer-events: none;
    }
    #error {
      position: fixed; top: 50%; left: 50%;
      transform: translate(-50%, -50%);
      color: #ff4444; font-size: 13px; max-width: 600px;
      text-align: center; display: none;
    }
  </style>

  <!-- importmap tells the browser where to load Three.js modules from -->
  <script type="importmap">
  {
    "imports": {
      "three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
      "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"
    }
  }
  </script>
</head>
<body>
  <div id="label">&#x2B21; {{MODEL_NAME}}</div>
  <div id="hint">drag to rotate &middot; scroll to zoom &middot; right-click to pan</div>
  <div id="error"></div>

  <script type="module">
    import * as THREE from 'three';
    import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

    // ── Error display (shows JS errors on screen instead of silent black) ────
    window.onerror = (msg) => {
      const el = document.getElementById('error');
      el.style.display = 'block';
      el.textContent = 'Model error: ' + msg;
    };

    // ── Scene setup ──────────────────────────────────────────────────────────
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0a0a0f);
    scene.fog        = new THREE.Fog(0x0a0a0f, 30, 100);

    const camera = new THREE.PerspectiveCamera(45, innerWidth / innerHeight, 0.1, 1000);
    camera.position.set(4, 3, 6);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(innerWidth, innerHeight);
    renderer.setPixelRatio(devicePixelRatio);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type    = THREE.PCFSoftShadowMap;
    document.body.appendChild(renderer.domElement);

    // ── Lighting ─────────────────────────────────────────────────────────────
    scene.add(new THREE.AmbientLight(0x334466, 3));

    const sun = new THREE.DirectionalLight(0xffffff, 3);
    sun.position.set(8, 12, 6);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    scene.add(sun);

    const fill = new THREE.DirectionalLight(0x4466ff, 1.2);
    fill.position.set(-6, 4, -4);
    scene.add(fill);

    const rim = new THREE.DirectionalLight(0x00ffaa, 0.6);
    rim.position.set(0, -4, -8);
    scene.add(rim);

    // ── Grid floor ───────────────────────────────────────────────────────────
    const grid = new THREE.GridHelper(30, 30, 0x111133, 0x111133);
    scene.add(grid);

    // ── OrbitControls ────────────────────────────────────────────────────────
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping   = true;
    controls.dampingFactor   = 0.05;
    controls.autoRotate      = true;
    controls.autoRotateSpeed = 1.5;
    controls.minDistance     = 0.5;
    controls.maxDistance     = 50;

    renderer.domElement.addEventListener('pointerdown', () => {
      controls.autoRotate = false;
    });

    // ── Shared material (available to geometry code) ──────────────────────────
    const material = new THREE.MeshStandardMaterial({
      color:     0x0088ff,
      metalness: 0.25,
      roughness: 0.45,
      side:      THREE.DoubleSide,  // render inside AND outside so hollow tops aren't black
    });

    // ── Model geometry (generated by LLM) ────────────────────────────────────
    function createModel() {
      {{GEOMETRY_CODE}}
    }

    try {
      const model = createModel();
      if (model === undefined || model === null) {
        throw new Error("createModel() returned nothing — the LLM may have wrapped code in a function declaration. Check terminal output.");
      }
      model.castShadow    = true;
      model.receiveShadow = true;

      // Centre model above the grid
      const bbox = new THREE.Box3().setFromObject(model);
      const centre = new THREE.Vector3();
      bbox.getCenter(centre);
      model.position.sub(centre);
      model.position.y += (bbox.max.y - bbox.min.y) / 2;

      scene.add(model);

      // Zoom camera to fit the model nicely
      const size = bbox.getSize(new THREE.Vector3()).length();
      camera.position.set(size * 1.2, size * 0.8, size * 1.8);
      controls.update();
    } catch (e) {
      document.getElementById('error').style.display = 'block';
      document.getElementById('error').textContent = 'Geometry error: ' + e.message;
    }

    // ── Resize ───────────────────────────────────────────────────────────────
    window.addEventListener('resize', () => {
      camera.aspect = innerWidth / innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(innerWidth, innerHeight);
    });

    // ── Render loop ──────────────────────────────────────────────────────────
    (function animate() {
      requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    })();
  </script>
</body>
</html>"""


def generate_and_open(geometry_code: str, model_name: str) -> str:
    """
    Inject LLM geometry code into the HTML template, save it, and open in browser.

    Args:
        geometry_code: Three.js JS code that builds and returns the mesh/group.
        model_name:    Human-readable name shown in the page title and label.

    Returns:
        The path to the saved HTML file, or an error string.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Sanitise the filename
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in model_name)
    html_path = OUTPUT_DIR / f"{safe_name}.html"

    html = HTML_TEMPLATE.replace("{{GEOMETRY_CODE}}", geometry_code)
    html = html.replace("{{MODEL_NAME}}", model_name)

    html_path.write_text(html, encoding="utf-8")
    print(f"[html_preview] Saved preview to {html_path}")

    # Open in the default browser (macOS `open` command)
    subprocess.Popen(["open", str(html_path)])
    print("[html_preview] Opened in browser.")

    return str(html_path)
