import cv2
import numpy as np
import math
import time
import json
import base64
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

import state
from gui import HTML_PAGE_BYTES

def _averaged_depth_to_jpeg(depth_frame_u16, quality):
    valid_mask = depth_frame_u16 > 0
    norm = np.zeros_like(depth_frame_u16, dtype=np.uint8)

    if valid_mask.any():
        valid_vals = depth_frame_u16[valid_mask].astype(np.float32)
        d_min = float(valid_vals.min())
        d_max = float(valid_vals.max())
        scale = 255.0 / max(d_max - d_min, 1.0)
        norm[valid_mask] = np.clip((depth_frame_u16[valid_mask].astype(np.float32) - d_min) * scale, 0, 255).astype(np.uint8)

    color = cv2.applyColorMap(norm, cv2.COLORMAP_JET)
    color[~valid_mask] = 0   

    _, buf = cv2.imencode('.jpg', color, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes()

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    pass

class ROVWebHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  
        
    def do_GET(self):
        try:
            if self.path == '/':
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(HTML_PAGE_BYTES)
                
            elif self.path == '/state':
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                with state.state_lock:
                    payload = state.latest_json_payload
                self.wfile.write(payload.encode('utf-8'))
                
            elif self.path == '/raw_depth':
                with state.state_lock:
                    if state.latest_depth_frame is not None:
                        buffer = state.latest_depth_frame.tobytes()
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/octet-stream')
                        self.end_headers()
                        self.wfile.write(buffer)
                    else:
                        self.send_response(400)
                        self.end_headers()
                        
            elif self.path == '/snapshot':
                buffer = None
                with state.state_lock:
                    buffer = state.frozen_rgb_jpeg_bytes if state.system_state == "FROZEN" else state.latest_rgb_jpeg_bytes
                
                if buffer is not None:
                    self.send_response(200)
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Disposition', f'attachment; filename="triton_{int(time.time())}.jpg"')
                    self.end_headers()
                    self.wfile.write(buffer)
                else:
                    self.send_response(400)
                    self.end_headers()
            else:
                self.send_response(404)
                self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            pass 

    def do_POST(self):
        try:
            if self.path == '/toggle':
                response_payload = {}
                with state.state_lock:
                    if state.system_state == "LIVE":
                        state.system_state = "FROZEN"
                        state.frozen_rgb_jpeg_bytes = state.latest_rgb_jpeg_bytes
                        buf_len = len(state.depth_buffer)
                        
                        b64_rgb = ""
                        b64_disp = ""
                        
                        if buf_len > 0:
                            averaged = state.variance_masked_average(state.depth_buffer)
                            state.latest_depth_frame = averaged
                            
                            frozen_disp = _averaged_depth_to_jpeg(averaged, state.JPEG_QUALITY)
                            state.frozen_disp_jpeg_bytes = frozen_disp
                            
                            b64_rgb  = base64.b64encode(state.frozen_rgb_jpeg_bytes).decode('utf-8')
                            b64_disp = base64.b64encode(frozen_disp).decode('utf-8')
                            
                            state.latest_json_payload = json.dumps({
                                "fps": 0.0, "motion": 0.0, "stable": True,
                                "buf_len": buf_len, "max_buf": state.BUFFER_SIZE,
                                "rgb": b64_rgb, "disp": b64_disp,
                                "frozen": True, "disconnected": False
                            })
                        else:
                            state.frozen_disp_jpeg_bytes = None
                            
                        response_payload = {
                            'state': state.system_state,
                            'buf_len': buf_len,
                            'max_buf': state.BUFFER_SIZE,
                            'rgb': b64_rgb,
                            'disp': b64_disp
                        }
                    else:
                        state.system_state = "LIVE"
                        state.depth_buffer = []
                        state.frozen_rgb_jpeg_bytes = None
                        state.frozen_disp_jpeg_bytes = None
                        state.latest_depth_frame = None
                        
                        response_payload = {
                            'state': state.system_state,
                            'buf_len': 0,
                            'max_buf': state.BUFFER_SIZE
                        }
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response_payload).encode('utf-8'))
                
            elif self.path == '/settings':
                length = int(self.headers['Content-Length'])
                data = json.loads(self.rfile.read(length).decode('utf-8'))
                
                new_size = int(np.clip(int(data.get('size', state.BUFFER_SIZE)), 10, 60))
                new_fps = int(np.clip(int(data.get('fps', state.TARGET_FPS)), 10, 60))
                new_k = float(np.clip(float(data.get('k', state.REFRACTION_K)), 0.5, 2.0))
                new_sigma = float(np.clip(float(data.get('sigma', state.SIGMA_THRESHOLD)), 0.5, 5.0))
                
                needs_reboot = False
                with state.state_lock:
                    state.BUFFER_SIZE = new_size
                    state.REFRACTION_K = new_k
                    state.SIGMA_THRESHOLD = new_sigma
                    while len(state.depth_buffer) > state.BUFFER_SIZE:
                        state.depth_buffer.pop(0)
                    
                    if state.TARGET_FPS != new_fps:
                        state.TARGET_FPS = new_fps
                        state.FPS_CHANGED = True
                        needs_reboot = True
                        
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'success', 'rebooting': needs_reboot}).encode('utf-8'))
                
            elif self.path == '/measure':
                length = int(self.headers['Content-Length'])
                data = json.loads(self.rfile.read(length).decode('utf-8'))
                p1, p2 = data['p1'], data['p2']
                measure_mode = data.get('mode', 'DIRECT')
                
                response_data = {'status': 'error', 'result': 'Unknown Error'}
                
                with state.state_lock:
                    depth_frame = state.latest_depth_frame
                    k = state.REFRACTION_K
                    fx, fy = state.fx, state.fy
                    cx, cy = state.cx, state.cy
                    
                if depth_frame is None:
                    response_data['result'] = "ERR: Buffer Empty"
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(response_data).encode('utf-8'))
                    return

                H, W = depth_frame.shape

                def _rough_z(px, py):
                    r = 8
                    x0, x1 = max(0, px - r), min(W, px + r)
                    y0, y1 = max(0, py - r), min(H, py + r)
                    patch = depth_frame[y0:y1, x0:x1]
                    valid = patch[patch > 0]
                    return float(np.median(valid)) if len(valid) > 0 else 1000.0

                z1_est = _rough_z(p1[0], p1[1])
                z2_est = _rough_z(p2[0], p2[1])

                pad1 = state.compute_adaptive_pad(z1_est)
                pad2 = state.compute_adaptive_pad(z2_est)

                valid1, conf1 = state.roi_confidence(depth_frame, p1[0], p1[1], pad1)
                valid2, conf2 = state.roi_confidence(depth_frame, p2[0], p2[1], pad2)

                conf_rank = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}
                conf_label = conf1 if conf_rank[conf1] <= conf_rank[conf2] else conf2

                if len(valid1) <= 4 or len(valid2) <= 4:
                    response_data['result'] = "ERR: Bad Depth at Clicks"
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(response_data).encode('utf-8'))
                    return
                    
                z1 = state.get_smart_percentile(valid1)
                z2 = state.get_smart_percentile(valid2)
                avg_z = (z1 + z2) / 2.0
                
                x1_raw = (p1[0] - cx) * z1 / fx
                y1_raw = (p1[1] - cy) * z1 / fy
                x2_raw = (p2[0] - cx) * z2 / fx
                y2_raw = (p2[1] - cy) * z2 / fy
                
                if measure_mode == 'DIRECT':
                    alpha = 0.10
                    er1 = abs(p1[0] - cx) / cx
                    er2 = abs(p2[0] - cx) / cx
                    x1_3d = x1_raw * (1.0 - alpha * er1 ** 2)
                    x2_3d = x2_raw * (1.0 - alpha * er2 ** 2)
                else:
                    x1_3d = x1_raw
                    x2_3d = x2_raw
                
                y1_3d = y1_raw
                y2_3d = y2_raw
                
                dist_mm_raw = math.sqrt((x2_3d - x1_3d)**2 + (y2_3d - y1_3d)**2 + (z2 - z1)**2)
                dist_mm = dist_mm_raw * k 
                dist_cm = round(dist_mm / 10.0, 2)
                
                response_data = {
                    'status': 'success',
                    'result': f"{dist_cm:.1f} cm",
                    'dist_cm': dist_cm,
                    'avg_cam_dist_m': round(avg_z / 1000.0, 2),
                    'confidence': conf_label,
                    'pad1': pad1,
                    'pad2': pad2
                }
                if avg_z > 2500:
                    response_data['warning'] = f"Target ~{avg_z/10:.0f}cm away. Check accuracy."
                    
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response_data).encode('utf-8'))
        except (BrokenPipeError, ConnectionResetError):
            pass