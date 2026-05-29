import cv2
import depthai as dai
import numpy as np
import time
import threading
import base64
import json

import state
from server import ThreadedHTTPServer, ROVWebHandler

def main():
    print("\n--- TRITON ROV BOOT SEQUENCE ---")
    
    server = ThreadedHTTPServer(('0.0.0.0', state.PORT), ROVWebHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"✅ HUD SERVER ONLINE")
    print(f"🌐 Connect laptop browser to: http://<ROV_IP>:{state.PORT}\n")

    while True:
        print("⏳ Waiting for OAK-D camera to be connected...")
        while len(dai.Device.getAllAvailableDevices()) == 0:
            time.sleep(1)
            
        print("🔗 Camera detected! Booting hardware...")

        try:
            with dai.Device() as temp_device:
                calibData = temp_device.readCalibration() if state.UNDERWATER_MODE else temp_device.readFactoryCalibration()

            intrinsics = calibData.getCameraIntrinsics(dai.CameraBoardSocket.CAM_A, 640, 360)
            state.fx, state.fy = intrinsics[0][0], intrinsics[1][1]
            state.cx, state.cy = intrinsics[0][2], intrinsics[1][2]

            pipeline = dai.Pipeline()
            pipeline.setCalibrationData(calibData)

            camRgb = pipeline.create(dai.node.ColorCamera)
            camRgb.setBoardSocket(dai.CameraBoardSocket.CAM_A)
            camRgb.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
            camRgb.setVideoSize(640, 360) 
            camRgb.setPreviewSize(160, 90)
            camRgb.setInterleaved(False)
            camRgb.setColorOrder(dai.ColorCameraProperties.ColorOrder.BGR)
            camRgb.setFps(state.TARGET_FPS)

            videoEncRgb = pipeline.create(dai.node.VideoEncoder)
            videoEncRgb.setDefaultProfilePreset(state.TARGET_FPS, dai.VideoEncoderProperties.Profile.MJPEG)
            videoEncRgb.setQuality(state.JPEG_QUALITY)
            camRgb.video.link(videoEncRgb.input)

            camLeft = pipeline.create(dai.node.MonoCamera)
            camLeft.setBoardSocket(dai.CameraBoardSocket.CAM_B)
            camLeft.setResolution(dai.MonoCameraProperties.SensorResolution.THE_800_P)
            camLeft.setFps(state.TARGET_FPS)
            
            camRight = pipeline.create(dai.node.MonoCamera)
            camRight.setBoardSocket(dai.CameraBoardSocket.CAM_C)
            camRight.setResolution(dai.MonoCameraProperties.SensorResolution.THE_800_P)
            camRight.setFps(state.TARGET_FPS)

            stereo = pipeline.create(dai.node.StereoDepth)
            stereo.setDefaultProfilePreset(dai.node.StereoDepth.PresetMode.HIGH_DENSITY)
            stereo.setDepthAlign(dai.CameraBoardSocket.CAM_A)
            stereo.setOutputSize(640, 360)
            stereo.setLeftRightCheck(True)
            stereo.setSubpixel(True)
            
            stereo.initialConfig.setConfidenceThreshold(160)
            stereo.initialConfig.setMedianFilter(dai.MedianFilter.KERNEL_7x7)
            config = stereo.initialConfig.get()
            config.postProcessing.spatialFilter.enable = True
            config.postProcessing.spatialFilter.holeFillingRadius = 2
            config.postProcessing.spatialFilter.numIterations = 1
            config.postProcessing.temporalFilter.enable = True
            config.postProcessing.temporalFilter.alpha = 0.4
            config.postProcessing.temporalFilter.delta = 20
            config.postProcessing.thresholdFilter.minRange = 200
            config.postProcessing.thresholdFilter.maxRange = 5000
            stereo.initialConfig.set(config)
            
            camLeft.out.link(stereo.left)
            camRight.out.link(stereo.right)

            xoutJpeg = pipeline.create(dai.node.XLinkOut)
            xoutJpeg.setStreamName("rgb_jpeg")
            videoEncRgb.bitstream.link(xoutJpeg.input)

            xoutPreview = pipeline.create(dai.node.XLinkOut)
            xoutPreview.setStreamName("preview")
            camRgb.preview.link(xoutPreview.input)

            xoutDepth = pipeline.create(dai.node.XLinkOut)
            xoutDepth.setStreamName("depth")
            stereo.depth.link(xoutDepth.input)

            xoutDisp = pipeline.create(dai.node.XLinkOut)
            xoutDisp.setStreamName("disp")
            stereo.disparity.link(xoutDisp.input)

            with dai.Device(pipeline) as device:
                print(f"✅ DEPTH PIPELINE ACTIVE (FPS: {state.TARGET_FPS})")
                
                # Decoupled Queues
                qJpeg = device.getOutputQueue(name="rgb_jpeg", maxSize=1, blocking=False)
                qPreview = device.getOutputQueue(name="preview", maxSize=1, blocking=False)
                qDepth = device.getOutputQueue(name="depth", maxSize=1, blocking=False)
                qDisp = device.getOutputQueue(name="disp", maxSize=1, blocking=False)
                
                fps_start_time = time.time()
                fps_counter = 0
                current_fps = 0.0
                prev_gray = None
                
                while True:
                    with state.state_lock:
                        if state.FPS_CHANGED:
                            print(f"🔄 FPS Change Requested. Rebooting pipeline...")
                            state.FPS_CHANGED = False
                            break
                            
                    inJpeg = qJpeg.get() # Heartbeat
                    inPreview = qPreview.tryGet()
                    inDepth = qDepth.tryGet()
                    inDisp = qDisp.tryGet()

                    fps_counter += 1
                    current_time = time.time()
                    if current_time - fps_start_time >= 1.0:
                        current_fps = fps_counter / (current_time - fps_start_time)
                        fps_counter = 0
                        fps_start_time = current_time

                    if state.system_state != "LIVE":
                        continue # Drain queues silently while frozen

                    rgb_bytes = inJpeg.getData().tobytes()
                    state.latest_rgb_jpeg_bytes = rgb_bytes
                    b64_rgb = base64.b64encode(rgb_bytes).decode('utf-8')
                    b64_disp = ""

                    if inDisp is not None:
                        disp_vis = (inDisp.getFrame() * (255.0 / 96.0)).astype(np.uint8)
                        disp_color = cv2.applyColorMap(disp_vis, cv2.COLORMAP_JET)
                        _, buf = cv2.imencode('.jpg', disp_color, [cv2.IMWRITE_JPEG_QUALITY, state.JPEG_QUALITY])
                        b64_disp = base64.b64encode(buf.tobytes()).decode('utf-8')

                    motion_score = 0.0
                    is_stable = True
                    if inPreview is not None:
                        small_frame = inPreview.getCvFrame()
                        curr_gray = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
                        curr_gray = cv2.GaussianBlur(curr_gray, (5, 5), 0)
                        if prev_gray is not None:
                            diff = cv2.absdiff(curr_gray, prev_gray)
                            motion_score = np.mean(diff)
                            if motion_score > state.MOTION_THRESHOLD:
                                is_stable = False
                        prev_gray = curr_gray

                    if inDepth is not None:
                        with state.state_lock:
                            if is_stable:
                                state.depth_buffer.append(inDepth.getFrame().copy())
                                while len(state.depth_buffer) > state.BUFFER_SIZE:
                                    state.depth_buffer.pop(0)
                            else:
                                state.depth_buffer.clear()

                    payload = {
                        "fps": current_fps,
                        "motion": motion_score,
                        "stable": is_stable,
                        "buf_len": len(state.depth_buffer),
                        "max_buf": state.BUFFER_SIZE,
                        "rgb": b64_rgb,
                        "disp": b64_disp,
                        "disconnected": False
                    }
                    
                    with state.state_lock:
                        state.latest_json_payload = json.dumps(payload)

        except RuntimeError as e:
            print(f"\n⚠️ OAK-D CONNECTION LOST: {e}")
            with state.state_lock:
                state.depth_buffer.clear()
                state.latest_json_payload = json.dumps({
                    "fps": 0.0, "motion": 0.0, "stable": False, 
                    "buf_len": 0, "max_buf": state.BUFFER_SIZE, "disconnected": True
                })
            time.sleep(2)

if __name__ == "__main__":
    main()