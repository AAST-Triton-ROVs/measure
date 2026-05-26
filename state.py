import threading
import numpy as np

# --- CONFIGURATION ---
UNDERWATER_MODE = True  # True = Flashed EEPROM, False = Factory EEPROM
PORT = 1111
JPEG_QUALITY = 70  
MOTION_THRESHOLD = 3.5  # TUNE THIS: Higher = less sensitive. Lower = more sensitive.

# --- GLOBAL MEMORY & STATE ---
system_state = "LIVE"
active_clients = 0
latest_jpeg = None
latest_uncompressed_frame = None  
frozen_uncompressed_frame = None  
latest_depth_frame = None
depth_buffer = []  
fx = fy = cx = cy = 0.0
state_lock = threading.Lock() # Thread safety lock

# --- SPATIAL FILTER ---
def get_smart_percentile(valid_pixels):
    """
    Analyzes spatial depth data to bypass near-field backscatter.
    Normalizes the noise spread against distance to prevent false
    turbidity detection at extreme stereo ranges.
    """
    p10 = np.percentile(valid_pixels, 10)
    p50 = np.percentile(valid_pixels, 50)

    noise_gap = p50 - p10
    normalized_gap = (noise_gap / max(p50, 1)) * 1000

    if normalized_gap < 15:
        target_p = 25       # Clean water / normal hardware variance
    elif normalized_gap > 100:
        target_p = 65       # Heavy backscatter: push up to clear the noise wall
    else:
        target_p = 25 + ((normalized_gap - 15) / 85) * 40  # Linear interpolation

    # Sparse ROI guard: don't push too high on unreliable distributions
    if len(valid_pixels) < 15:
        target_p = min(target_p, 45)

    return np.percentile(valid_pixels, target_p)
