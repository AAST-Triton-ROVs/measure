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

# --- MEASUREMENT CORRECTION ---
REFRACTION_K = 1.0  # Scalar for dome port refraction (Default 1.0)
SIGMA_THRESHOLD = 2.0  # Strictness for temporal variance masking

# --- GLOBAL MEMORY & STATE ---
system_state = "LIVE"
active_clients = 0

latest_json_payload = "{}"
latest_rgb_jpeg_bytes = None
frozen_rgb_jpeg_bytes = None

latest_depth_frame = None       # Averaged, variance-masked depth (uint16, mm)
frozen_disp_jpeg_bytes = None   # Averaged depth heatmap JPEG, generated on freeze

depth_buffer = []               # Raw per-frame depth stack (uint16 arrays)
fx = fy = cx = cy = 0.0
state_lock = threading.Lock()

# --- SPATIAL FILTERS & OPTICS ---
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

def compute_adaptive_pad(z_mm, base_pad=15, min_pad=5, max_pad=30):
    if z_mm <= 0: return base_pad
    pad = int(base_pad * (1000.0 / z_mm))
    return int(np.clip(pad, min_pad, max_pad))

def variance_masked_average(stack):
    arr = np.array(stack, dtype=np.float32)
    N = arr.shape[0]
    if N == 1: return arr[0].astype(np.uint16)

    valid_mask = arr > 0 
    masked = np.ma.array(arr, mask=~valid_mask)
    pixel_median = np.ma.median(masked, axis=0).filled(0)

    # Robust std via Median Absolute Deviation (MAD)
    abs_dev = np.abs(arr - pixel_median[np.newaxis, :, :])
    mad = np.ma.median(np.ma.array(abs_dev, mask=~valid_mask), axis=0).filled(0)
    std_est = 1.4826 * mad

    # Filter out anything deviating wildly from the temporal median
    threshold = SIGMA_THRESHOLD * std_est[np.newaxis, :, :]
    accept = valid_mask & (abs_dev <= threshold)

    arr_accepted = np.where(accept, arr, 0.0)
    count = accept.sum(axis=0).astype(np.float32)
    count = np.where(count == 0, 1, count)
    
    return (arr_accepted.sum(axis=0) / count).astype(np.uint16)

def roi_confidence(depth_frame, cx_px, cy_px, pad):
    H, W = depth_frame.shape
    x_min, x_max = max(0, cx_px - pad), min(W, cx_px + pad)
    y_min, y_max = max(0, cy_px - pad), min(H, cy_px + pad)

    roi = depth_frame[y_min:y_max, x_min:x_max]
    total = roi.size
    valid = roi[roi > 0]
    ratio = len(valid) / max(total, 1)

    if ratio >= 0.6: label = "HIGH"
    elif ratio >= 0.3: label = "MEDIUM"
    else: label = "LOW"
    
    return valid, label