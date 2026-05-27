import numpy as np
import math
import time
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

import state
from gui import HTML_PAGE_BYTES

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    pass

class ROVWebHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  
        
    def do_GET(self):
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
                    
        elif self.path == '/snapshot':
            buffer = None
            with state.state_lock:
                if state.system_state == "FROZEN" and state.frozen_rgb_jpeg_bytes is not None:
                    buffer = state.frozen_rgb_jpeg_bytes
                else:
                    buffer = state.latest_rgb_jpeg_bytes
            
            if buffer is not None:
                self.send_response(200)
                self.send_header('Content-Type', 'image/jpeg')
                timestamp = int(time.time())
                self.send_header('Content-Disposition', f'attachment; filename="triton_capture_{timestamp}.jpg"')
                self.end_headers()
                self.wfile.write(buffer)
            else:
                self.send_response(400)
                self.end_headers()

    def do_POST(self):
        if self.path == '/toggle':
            buf_len = 0
            with state.state_lock:
                if state.system_state == "LIVE":
                    state.system_state = "FROZEN"
                    state.frozen_rgb_jpeg_bytes = state.latest_rgb_jpeg_bytes
                    
                    buf_len = len(state.depth_buffer)
                    if buf_len > 0:
                        stack = np.array(state.depth_buffer)
                        low  = np.percentile(stack, 10, axis=0)
                        high = np.percentile(stack, 80, axis=0)
                        mask = (stack >= low) & (stack <= high)
                        stack_masked = np.where(mask, stack, 0).astype(np.float32)
                        count = mask.sum(axis=0).astype(np.float32)
                        count = np.where(count == 0, 1, count)
                        state.latest_depth_frame = (stack_masked.sum(axis=0) / count).astype(np.uint16)
                else:
                    state.system_state = "LIVE"
                    state.depth_buffer = []
                    state.frozen_rgb_jpeg_bytes = None
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'state': state.system_state,
                'buf_len': buf_len,
                'max_buf': state.BUFFER_SIZE
            }).encode('utf-8'))
            
        elif self.path == '/settings':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            new_size = max(10, min(60, int(data.get('size', state.BUFFER_SIZE))))
            new_fps = max(10, min(60, int(data.get('fps', state.TARGET_FPS))))
            
            needs_reboot = False
            with state.state_lock:
                state.BUFFER_SIZE = new_size
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
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            p1, p2 = data['p1'], data['p2']
            measure_mode = data.get('mode', 'DIRECT')
            
            response_data = {'status': 'error', 'result': 'Unknown Error'}
            
            if state.latest_depth_frame is not None:
                pad = 15
                x1_min, x1_max = max(0, p1[0]-pad), min(640, p1[0]+pad)
                y1_min, y1_max = max(0, p1[1]-pad), min(360, p1[1]+pad)
                x2_min, x2_max = max(0, p2[0]-pad), min(640, p2[0]+pad)
                y2_min, y2_max = max(0, p2[1]-pad), min(360, p2[1]+pad)
                roi1 = state.latest_depth_frame[y1_min:y1_max, x1_min:x1_max]
                roi2 = state.latest_depth_frame[y2_min:y2_max, x2_min:x2_max]
                
                valid1 = roi1[(roi1 > 0)]
                valid2 = roi2[(roi2 > 0)]
                
                if len(valid1) > 4 and len(valid2) > 4:
                    z1 = state.get_smart_percentile(valid1)
                    z2 = state.get_smart_percentile(valid2)
                    avg_z = (z1 + z2) / 2.0
                    
                    x1_raw = (p1[0] - state.cx) * z1 / state.fx
                    y1_raw = (p1[1] - state.cy) * z1 / state.fy
                    x2_raw = (p2[0] - state.cx) * z2 / state.fx
                    y2_raw = (p2[1] - state.cy) * z2 / state.fy
                    
                    if measure_mode == 'DIRECT':
                        alpha = 0.10
                        edge_ratio_x1 = abs(p1[0] - state.cx) / state.cx
                        edge_ratio_x2 = abs(p2[0] - state.cx) / state.cx
                        x1_3d = x1_raw * (1.0 - (alpha * (edge_ratio_x1 ** 2)))
                        x2_3d = x2_raw * (1.0 - (alpha * (edge_ratio_x2 ** 2)))
                    else:
                        x1_3d = x1_raw
                        x2_3d = x2_raw
                    
                    y1_3d = y1_raw
                    y2_3d = y2_raw
                    
                    dist_mm = math.sqrt((x2_3d - x1_3d)**2 + (y2_3d - y1_3d)**2 + (z2 - z1)**2)
                    std1, std2 = np.std(valid1), np.std(valid2)
                    uncertainty_mm = math.sqrt(std1**2 + std2**2)
                    
                    dist_cm = round(dist_mm / 10.0, 2)
                    unc_cm = round(uncertainty_mm / 10.0, 2)
                    
                    response_data = {
                        'status': 'success',
                        'result': f"{dist_cm:.1f} cm",
                        'dist_cm': dist_cm,
                        'uncertainty_cm': unc_cm,
                        'avg_cam_dist_m': round(avg_z / 1000.0, 2),
                    }
                    if avg_z > 2500:
                        response_data['warning'] = f"Target ~{avg_z/10:.0f}cm away. Use REF mode to verify accuracy."
                else:
                    response_data['result'] = "ERR: Bad Depth at Clicks"
            else:
                response_data['result'] = "ERR: Buffer Empty"
                
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode('utf-8'))