# Triton ROV - Stereo Measurement System

A browser-based underwater measurement tool for the Triton ROV, built around the OAK-D S2 stereo camera. Pilots freeze a live video feed and click two points on the image to measure real-world distances using stereo depth — no physical contact with the target required.

Developed for the MATE ROV Competition by the Triton ROVs software team at AASTMT Alexandria.

---

## Features

- **Live MJPEG stream** served over Wi-Fi to any browser on the operator station
- **Freeze & measure** — spacebar freezes the feed; click two points to get a distance
- **Multi-measurement overlay** — accumulate multiple labeled measurements on the same frozen frame, each color-coded
- **Magnifier loupe** — hover over the frozen frame to zoom in for precise click placement
- **Motion-gated depth buffer** — depth frames are only accumulated when the ROV is stable; buffer clears automatically on motion
- **Smart percentile filter** — adapts to water turbidity by analyzing the statistical spread of depth values per click region
- **Temporal trimmed mean** — 60-frame depth stack with outlier rejection baked in at freeze time
- **Reference scaling mode** — empirical correction when stereo accuracy degrades at long range (>2.5 m)
- **Distance warning** — pilot is alerted when target distance exceeds reliable stereo bounds
- **Snapshot export** — save the full-resolution uncompressed frame to disk from the browser
- **HUD overlays** — live FPS, motion score, and buffer fill status burned into the stream

---

## Architecture

The system is split across four files with clean separation of concerns:

```
freeze.py   — hardware entry point: camera pipeline, capture loop, motion detection, HUD
server.py   — HTTP server: stream, snapshot, toggle, measure endpoints
gui.py      — HTML/CSS/JS frontend served as a string constant
state.py    — shared globals, configuration, and the smart percentile filter
```

`freeze.py` is the only file that touches DepthAI hardware. `server.py` handles all HTTP logic. `state.py` acts as the shared memory bus between threads, protected by a `threading.Lock`.

---

## Hardware Requirements

| Component | Spec |
|-----------|------|
| Camera | Luxonis OAK-D S2 |
| Onboard computer | Raspberry Pi 4 (4 GB recommended) |
| Connection | USB 3.0 (camera to Pi) |
| Network | Wi-Fi or tethered Ethernet to operator station |
| Operator station | Any modern browser (Chrome recommended) |

The OAK-D S2 must be calibrated and have its calibration flashed to EEPROM before deployment. Set `UNDERWATER_MODE = True` in `state.py` to load the flashed underwater calibration, or `False` to use the factory calibration for bench testing.

---

## Installation

```bash
# On the Raspberry Pi
pip install depthai opencv-python numpy

# Clone or copy the four source files to the Pi
scp freeze.py server.py gui.py state.py pi@<ROV_IP>:~/triton/
```

---

## Running

```bash
cd ~/triton
python freeze.py
```

On boot, the terminal will print the server address:

```
--- TRITON ROV BOOT SEQUENCE ---
 UNDERWATER MODE: Fetching Flashed Custom Calibration from EEPROM...
 SYSTEM ONLINE (HEADLESS MODE)
 Connect any laptop browser to: http://<ROV_IP>:1111
```

Open `http://<ROV_IP>:1111` in the operator browser. No installation required on the station side.

---

## Usage

### Direct Measurement (DIRECT 3D mode)

1. Watch the HUD overlay in the top-left corner. Wait for **LOCKED: 60/60 (READY)** before freezing.
2. Press **Spacebar** (or the FREEZE button) to freeze the frame.
3. Click **Point 1** on the target. A crosshair marker appears.
4. Click **Point 2**. The system queries the depth buffer, computes 3D coordinates, and draws a labeled line between the two points.
5. Repeat clicks for additional measurements on the same frame. Each pair gets a distinct color.
6. Press **CLEAR ALL** to reset measurements without resuming the stream.
7. Press **Spacebar** again to resume the live feed.

### Reference Scaling Mode (for targets > 2.5 m)

Use this when the distance warning appears, or when you know the target is at the edge of stereo accuracy.

1. Ensure a **known-length object** is visible in the frame (e.g., a PVC strut of measured length).
2. Click **MODE: DIRECT 3D** to switch to **SET REFERENCE**.
3. Freeze and click the two ends of the known object.
4. Enter the real length in cm when prompted. The scale factor is locked.
5. The mode switches to **MEASURING TARGET** — click any two points; the system applies the empirical correction.

### Snapshot

Click **SAVE TO PC** at any time (frozen or live) to download a full-resolution JPEG from the browser.

---

## Configuration

All tuneable parameters are in `state.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `UNDERWATER_MODE` | `True` | `True` = load flashed EEPROM calibration; `False` = factory calibration |
| `PORT` | `1111` | HTTP server port |
| `JPEG_QUALITY` | `70` | Stream compression (lower = faster, higher = sharper) |
| `MOTION_THRESHOLD` | `3.5` | Motion sensitivity for depth buffer gating. Increase (6–8) if pool lighting flicker causes false clears. |

---

## How the Depth Pipeline Works

### Capture & Buffering

The Pi continuously captures stereo depth frames from the OAK-D S2. Each frame is motion-checked against the previous one using a downscaled (160×90) grayscale diff. If motion exceeds `MOTION_THRESHOLD`, the depth buffer is cleared. When stable, frames accumulate up to a 60-frame rolling window (~2 seconds at 30 fps).

### Freeze & Temporal Filter

When the pilot freezes, the 60-frame stack is processed pixel-by-pixel:
- Bottom 10% of values per pixel (backscatter / flying pixels) are rejected
- Top 20% of values per pixel (noise spikes) are rejected
- Remaining values are averaged into a single high-quality depth map

### Per-Click Spatial Filter (`get_smart_percentile`)

For each clicked point, a 30×30 px ROI is sampled from the depth map. Valid (non-zero) pixels are analyzed:

```
normalized_gap = ((p50 - p10) / p50) × 1000
```

This normalizes depth spread relative to distance, preventing long-range stereo noise from being mistaken for turbidity.

| Condition | Target percentile |
|-----------|------------------|
| `normalized_gap < 15` (clear water) | 25th |
| `normalized_gap > 100` (heavy backscatter) | 65th |
| Between | Linear interpolation |
| ROI has < 15 valid pixels | Capped at 45th |

Near-field backscatter particles return low depth values (appear closer than the object). Pushing the percentile upward bypasses these and lands on the solid object surface behind them.

### 3D Reconstruction

Standard pinhole unprojection with a flat-port edge correction in DIRECT mode:

```
x_3d = ((px - cx) × z / fx) × (1 - α × edge_ratio²)
y_3d =  (py - cy) × z / fy
dist = √(Δx² + Δy² + Δz²)
```

The edge correction (`α = 0.10`) compensates for apparent barrel distortion introduced by the flat acrylic port at wide angles. It is bypassed in Reference Scaling mode, where empirical correction replaces the analytical model.

---

## Stereo Accuracy Expectations

| Camera-to-target distance | Expected accuracy | Recommended mode |
|--------------------------|------------------|-----------------|
| < 1 m | ± 3–5 cm | DIRECT 3D |
| 1–2 m | ± 5–10 cm | DIRECT 3D |
| 2–3 m | ± 10–20 cm | DIRECT 3D |
| 3–4 m | ± 20–40 cm | REF mode strongly recommended |
| > 4 m | Unreliable | REF mode only |

Accuracy degrades at long range due to the OAK-D S2's 7.5 cm stereo baseline. Underwater contrast loss and backscatter accelerate this degradation. The distance warning fires automatically when the averaged depth exceeds 2.5 m.

---

## Known Limitations

- Measurements require a frozen frame; real-time measurement is not supported
- Depth accuracy assumes a stationary ROV; measurements taken while drifting will be unreliable even if the HUD shows LOCKED
- The flat-port edge correction coefficient (`α = 0.10`) was tuned empirically at 1 m calibration depth and may need adjustment for other configurations
- Reference scaling applies a single global scale factor; it cannot correct for spatially-varying distortion across the frame

---

## File Reference

| File | Responsibility |
|------|---------------|
| `freeze.py` | Entry point. DepthAI pipeline, capture loop, motion detection, HUD rendering, HTTP server thread launch |
| `server.py` | `ThreadedHTTPServer`. Handles `/`, `/stream`, `/snapshot`, `/toggle`, `/measure` |
| `gui.py` | Complete frontend as `HTML_PAGE` / `HTML_PAGE_BYTES`. Pure client-side JS — no server load for drawing |
| `state.py` | Shared globals, `state_lock`, configuration constants, `get_smart_percentile()` |

---

## Team

Triton ROVs - Software sub-team                                      
Arab Academy for Science, Technology & Maritime Transport, Alexandria                          
MATE ROV Competition
