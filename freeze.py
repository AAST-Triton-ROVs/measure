import cv2
import depthai as dai
import numpy as np
import time
import threading

import state
from server import ThreadedHTTPServer, ROVWebHandler

def main():
    print("\n--- TRITON ROV BOOT SEQUENCE ---")
    
    with dai.Device() as temp_device:
        if state.UNDERWATER_MODE:
            print("🌊 UNDERWATER MODE: Fetching Flashed Custom Calibration from EEPROM...")
            calibData = temp_device.readCalibration()
        else:
            print("🏢 DESK MODE: Fetching Original Factory Calibration from EEPROM...")
            calibData = temp_device.readFactoryCalibration()

    intrinsics = calibData.getCameraIntrinsics(dai.CameraBoardSocket.CAM_A, 640, 360)
    state.fx, state.fy = intrinsics[0][0], intrinsics[1][1]
    state.cx, state.cy = intrinsics[0][2], intrinsics[1][2]

    pipeline = dai.Pipeline()
    pipeline.setCalibrationData(calibData)

    camRgb = pipeline.create(dai.node.ColorCamera)
    camRgb.setBoardSocket(dai.CameraBoardSocket.CAM_A)
    camRgb.setPreviewSize(640, 360)
    camRgb.setInterleaved(False)
    camRgb.setColorOrder(dai.ColorCameraProperties.ColorOrder.BGR)

    camLeft = pipeline.create(dai.node.MonoCamera)
    camLeft.setBoardSocket(dai.CameraBoardSocket.CAM_B)
    camLeft.setResolution(dai.MonoCameraProperties.SensorResolution.THE_800_P)
    
    camRight = pipeline.create(dai.node.MonoCamera)
    camRight.setBoardSocket(dai.CameraBoardSocket.CAM_C)
    camRight.setResolution(dai.MonoCameraProperties.SensorResolution.THE_800_P)

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
    xoutRgb = pipeline.create(dai.node.XLinkOut)
    xoutRgb.setStreamName("rgb")
    camRgb.preview.link(xoutRgb.input)
    xoutDepth = pipeline.create(dai.node.XLinkOut)
    xoutDepth.setStreamName("depth")
    stereo.depth.link(xoutDepth.input)

    server = ThreadedHTTPServer(('0.0.0.0', state.PORT), ROVWebHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    
    print(f"✅ SYSTEM ONLINE (HEADLESS MODE)")
    print(f"🌐 Connect any laptop browser to: http://<ROV_IP>:{state.PORT}\n")

    with dai.Device(pipeline) as device:
        qRgb = device.getOutputQueue(name="rgb", maxSize=1, blocking=False)
        qDepth = device.getOutputQueue(name="depth", maxSize=1, blocking=False)
        
        fps_start_time = time.time()
        fps_counter = 0
        current_fps = 0.0
        prev_gray = None
        
        while True:
            inRgb = qRgb.get()
            inDepth = qDepth.tryGet()

            fps_counter += 1
            current_time = time.time()
            if current_time - fps_start_time >= 1.0:
                current_fps = fps_counter / (current_time - fps_start_time)
                fps_counter = 0
                fps_start_time = current_time

            if state.system_state == "LIVE":
                state.latest_uncompressed_frame = inRgb.getCvFrame()
                stream_frame = state.latest_uncompressed_frame.copy()

                small_frame = cv2.resize(stream_frame, (160, 90))
                curr_gray = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
                curr_gray = cv2.GaussianBlur(curr_gray, (5, 5), 0)

                motion_score = 0.0
                is_stable = True

                if prev_gray is not None:
                    diff = cv2.absdiff(curr_gray, prev_gray)
                    motion_score = np.mean(diff)
                    if motion_score > state.MOTION_THRESHOLD:
                        is_stable = False

                prev_gray = curr_gray

                if inDepth is not None:
                    if is_stable:
                        state.depth_buffer.append(inDepth.getFrame())
                        if len(state.depth_buffer) > 60:
                            state.depth_buffer.pop(0)
                    else:
                        state.depth_buffer.clear()

                with state.state_lock:
                    client_count = state.active_clients

                if client_count > 0:
                    cv2.line(stream_frame, (310, 180), (330, 180), (0, 255, 0), 1)
                    cv2.line(stream_frame, (320, 170), (320, 190), (0, 255, 0), 1)
                    
                    buf_len = len(state.depth_buffer)
                    if not is_stable:
                        hud_text = "MOVING - CLEARING BUF"
                        hud_color = (0, 0, 255)
                    elif buf_len < 60:
                        hud_text = f"STABILIZING: {buf_len}/60"
                        hud_color = (0, 255, 255)
                    else:
                        hud_text = "LOCKED: 60/60 (READY)"
                        hud_color = (0, 255, 0)
                    
                    cv2.putText(stream_frame, f"FPS: {current_fps:.1f} | Mot: {motion_score:.1f}", 
                                (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                    cv2.putText(stream_frame, hud_text, 
                                (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, hud_color, 1)
                    
                    _, buffer = cv2.imencode('.jpg', stream_frame, [cv2.IMWRITE_JPEG_QUALITY, state.JPEG_QUALITY])
                    state.latest_jpeg = buffer.tobytes()

if __name__ == "__main__":
    main()
