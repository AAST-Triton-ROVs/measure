import threading
import numpy as np

# --- CONFIGURATION ---
UNDERWATER_MODE = True  
PORT = 1111
JPEG_QUALITY = 70  
MOTION_THRESHOLD = 6.0  

# --- DYNAMIC SETTINGS ---
BUFFER_SIZE = 30  
TARGET_FPS = 30
FPS_CHANGED = False

# --- GLOBAL MEMORY & STATE ---
system_state = "LIVE"
active_clients = 0

latest_json_payload = "{}" 
latest_rgb_jpeg_bytes = None
frozen_rgb_jpeg_bytes = None  

latest_depth_frame = None
depth_buffer = []  
fx = fy = cx = cy = 0.0
state_lock = threading.Lock()

# --- SPATIAL FILTER ---
def get_smart_percentile(valid_pixels):
    p10 = np.percentile(valid_pixels, 10)
    p50 = np.percentile(valid_pixels, 50)
    noise_gap = p50 - p10
    normalized_gap = (noise_gap / max(p50, 1)) * 1000

    if normalized_gap < 15: target_p = 25
    elif normalized_gap > 100: target_p = 65
    else: target_p = 25 + ((normalized_gap - 15) / 85) * 40

    if len(valid_pixels) < 15: target_p = min(target_p, 45)
    return np.percentile(valid_pixels, target_p)