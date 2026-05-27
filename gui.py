HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Triton ROV Web Pilot</title>
    <style>
        body { background-color: #0a0a0a; color: #0f0; font-family: monospace; text-align: center; margin-top: 30px; }
        
        #video-container { display: flex; justify-content: center; gap: 10px; position: relative; width: 1290px; margin: 0 auto; }
        
        .stream-box { position: relative; width: 640px; height: 360px; border: 2px solid #0f0; box-shadow: 0px 0px 20px rgba(0,255,0,0.3); }
        
        #stream-rgb { cursor: crosshair; }
        #measure-canvas { position: absolute; top: 0; left: 0; width: 640px; height: 360px; pointer-events: none; z-index: 3; }
        
        .hud-text { position: absolute; left: 10px; font-weight: bold; text-shadow: 1px 1px 2px #000; pointer-events: none; z-index: 5; }
        #hud-fps { top: 15px; color: #0f0; }
        #hud-status { top: 35px; color: #0f0; }
        #hud-z { position: absolute; bottom: 15px; right: 15px; font-weight: bold; font-size: 16px; background: rgba(0,0,0,0.7); padding: 5px 10px; border: 1px solid #0ff; color: #0ff; pointer-events: none; z-index: 5; display: none; }
        
        #crosshair { position: absolute; top: 0; left: 0; width: 640px; height: 360px; pointer-events: none; z-index: 4; }
        .target-dot { position: absolute; width: 8px; height: 8px; background: red; border-radius: 50%; transform: translate(-50%, -50%); pointer-events: none; z-index: 10; box-shadow: 0 0 5px red; }
        
        #sync-line {
            position: absolute; height: 1px; background: #0ff; box-shadow: 0 0 12px #0ff, 0 0 4px #0ff;
            pointer-events: none; z-index: 15; display: none; transform-origin: left;
        }
        
        #disp-v-line {
            position: absolute; top: 0; height: 100%; width: 1px; background: rgba(0, 255, 255, 0.4);
            box-shadow: 0 0 8px rgba(0, 255, 255, 0.8); pointer-events: none; z-index: 15; display: none;
        }

        #disp-target {
            position: absolute; width: 16px; height: 16px; border: 2px solid #0ff; border-radius: 50%;
            box-shadow: 0 0 10px #0ff, inset 0 0 5px #0ff; pointer-events: none; z-index: 16; display: none;
            transform: translate(-50%, -50%); background: rgba(0, 255, 255, 0.1);
        }
        #disp-target::after {
            content: ''; position: absolute; top: 50%; left: 50%; width: 2px; height: 2px;
            background: #fff; border-radius: 50%; transform: translate(-50%, -50%); box-shadow: 0 0 5px #fff;
        }

        #panel { margin-top: 20px; padding: 15px; border: 1px solid #333; display: inline-block; background: #111; min-width: 650px; }
        .readout { font-size: 28px; color: #0ff; margin: 10px 0; font-weight: bold; }
        
        .btn { background: #000; color: #0f0; border: 1px solid #0f0; padding: 10px 20px; cursor: pointer; font-weight: bold; font-family: monospace; margin: 5px; transition: background-color 0.2s; }
        .btn:hover:not(:disabled) { background: #333; }
        .btn:disabled { color: #555; border-color: #555; cursor: not-allowed; }
        
        input[type=number], input[type=range] { background: #000; color: #0f0; border: 1px solid #0f0; padding: 5px; font-family: monospace; text-align: center; }
        input[type=range] { padding: 0; cursor: pointer; accent-color: #0f0; }
        
        #debug-info { margin-top: 8px; font-size: 11px; color: #555; }
        #measure-list { margin-top: 10px; font-size: 13px; text-align: left; min-height: 20px; padding: 0 5px; }
        
        #magnifier { position: absolute; border: 2px solid #0ff; border-radius: 50%; box-shadow: 0 0 15px #0ff; pointer-events: none; display: none; z-index: 20; background-color: #000; }
    </style>
</head>
<body>
    <h2>TRITON ROV // TACTICAL WEB HUD</h2>
    
    <div id="video-container">
        <div id="sync-line"></div>
        
        <div class="stream-box" id="rgb-wrapper">
            <img id="stream-rgb" width="640" height="360" draggable="false" />
            
            <div id="hud-fps" class="hud-text">FPS: 0.0 | Mot: 0.0</div>
            <div id="hud-status" class="hud-text">CONNECTING...</div>
            <div id="hud-z">Z: --- mm</div>
            
            <svg id="crosshair">
                <line x1="310" y1="180" x2="330" y2="180" stroke="#0f0" stroke-width="1"/>
                <line x1="320" y1="170" x2="320" y2="190" stroke="#0f0" stroke-width="1"/>
            </svg>
            <canvas id="measure-canvas" width="640" height="360"></canvas>
            <canvas id="magnifier" width="120" height="120"></canvas>
        </div>
        
        <div class="stream-box" id="disp-wrapper">
            <img id="stream-disp" width="640" height="360" draggable="false" />
            <div id="disp-v-line"></div>
            <div id="disp-target"></div>
            
            <div style="position: absolute; bottom: 5px; left: 10px; font-size: 12px; font-weight: bold; color:#0f0; text-shadow: 1px 1px 2px #000;">
                LIVE DISPARITY / FROZEN HEATMAP
            </div>
        </div>
    </div>
    
    <div id="panel">
        <div id="status" style="color:#aaa;">Live Stream. Press SPACE to Freeze.</div>
        <div id="result" class="readout">0.0 cm</div>
        <div id="measure-list"></div>
        <br>
        <button id="freeze-btn" class="btn" onclick="toggleFreeze()">FREEZE (SPACE)</button>
        <button id="mode-btn" class="btn" onclick="toggleMode()">MODE: DIRECT 3D</button>
        <button class="btn" onclick="clearPoints()">CLEAR ALL</button>
        <button id="capture-btn" class="btn" onclick="takeSnapshot()">SAVE TO PC</button>
        <div id="debug-info"></div>

        <div style="margin-top: 15px; border-top: 1px solid #333; padding-top: 15px; display: flex; gap: 40px; text-align: left;">
            <div style="flex: 1;">
                <label style="font-weight:bold; color:#0f0;">STABILITY BUFFER: <span id="buf-val">30</span></label>
                <input type="range" id="buf-slider" min="10" max="60" value="30" style="width: 100%; margin-top: 5px; margin-bottom: 15px;">
                
                <label style="font-weight:bold; color:#0f0;">REFRACTION MULTIPLIER (K): <span id="k-val">1.00</span></label>
                <input type="range" id="k-slider" min="0.5" max="2.0" step="0.01" value="1.00" style="width: 100%; margin-top: 5px;">
            </div>
            <div style="flex: 1;">
                <label style="font-weight:bold; color:#0f0;">TARGET HARDWARE FPS: </label>
                <input type="number" id="fps-input" value="30" min="10" max="60" style="width: 60px; margin-left: 10px;">
                <div style="font-size: 10px; color: #555; margin-bottom: 15px; margin-top: 2px;">Press 'Enter' to reboot camera nodes</div>
                
                <label style="font-weight:bold; color:#0f0;">VARIANCE STRICTNESS (σ): <span id="sig-val">2.0</span></label>
                <input type="range" id="sig-slider" min="0.5" max="5.0" step="0.1" value="2.0" style="width: 100%; margin-top: 5px;">
            </div>
        </div>
    </div>
    
    <script>
        const streamRgb = document.getElementById('stream-rgb');
        const streamDisp = document.getElementById('stream-disp');
        const canvas = document.getElementById('measure-canvas');
        const ctx = canvas.getContext('2d');
        const resultDiv = document.getElementById('result');
        const statusDiv = document.getElementById('status');
        const freezeBtn = document.getElementById('freeze-btn');
        const modeBtn = document.getElementById('mode-btn');
        const debugDiv = document.getElementById('debug-info');
        const listDiv = document.getElementById('measure-list');
        const hudFps = document.getElementById('hud-fps');
        const hudStatus = document.getElementById('hud-status');
        const hudZ = document.getElementById('hud-z');
        const mag = document.getElementById('magnifier');
        const mctx = mag.getContext('2d');
        
        const syncLine = document.getElementById('sync-line');
        const dispVLine = document.getElementById('disp-v-line');
        const dispTarget = document.getElementById('disp-target');
        
        const bufSlider = document.getElementById('buf-slider');
        const kSlider = document.getElementById('k-slider');
        const sigSlider = document.getElementById('sig-slider');
        const fpsInput = document.getElementById('fps-input');
        
        const MAG_ZOOM = 3, MAG_SIZE = 120, CAM_W = 640, CAM_H = 360;
        const COLORS = ['#ff4444','#44ff44','#44aaff','#ffff44','#ff44ff','#44ffdd','#ffaa44','#aa44ff'];
        
        let isFrozen = false;
        let measureMode = 'DIRECT';
        let pendingP1 = null;
        let measurements = [];

        function loadSavedSettings() {
            if(localStorage.getItem('triton_buf_size')) {
                bufSlider.value = localStorage.getItem('triton_buf_size');
            }
            if(localStorage.getItem('triton_refraction_k')) {
                kSlider.value = localStorage.getItem('triton_refraction_k');
            }
            if(localStorage.getItem('triton_sigma_threshold')) {
                sigSlider.value = localStorage.getItem('triton_sigma_threshold');
            }
            if(localStorage.getItem('triton_target_fps')) {
                fpsInput.value = localStorage.getItem('triton_target_fps');
            }
            
            document.getElementById('buf-val').innerText = bufSlider.value;
            document.getElementById('k-val').innerText = parseFloat(kSlider.value).toFixed(2);
            document.getElementById('sig-val').innerText = parseFloat(sigSlider.value).toFixed(1);
            
            sendSettings();
        }
        
        bufSlider.addEventListener('input', (e) => {
            document.getElementById('buf-val').innerText = e.target.value;
            localStorage.setItem('triton_buf_size', e.target.value);
        });
        kSlider.addEventListener('input', (e) => {
            document.getElementById('k-val').innerText = parseFloat(e.target.value).toFixed(2);
            localStorage.setItem('triton_refraction_k', e.target.value);
        });
        sigSlider.addEventListener('input', (e) => {
            document.getElementById('sig-val').innerText = parseFloat(e.target.value).toFixed(1);
            localStorage.setItem('triton_sigma_threshold', e.target.value);
        });
        fpsInput.addEventListener('input', (e) => {
            localStorage.setItem('triton_target_fps', e.target.value);
        });

        function sendSettings() {
            fetch('/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    size: parseInt(bufSlider.value), 
                    fps: parseInt(fpsInput.value),
                    k: parseFloat(kSlider.value),
                    sigma: parseFloat(sigSlider.value)
                })
            }).then(res => res.json()).then(data => {
                if (data.rebooting) {
                    hudStatus.innerText = "🔄 REBOOTING CAMERAS FOR NEW FPS...";
                    hudStatus.style.color = "#ff00ff";
                }
            }).catch(err => console.error("Settings error:", err));
        }

        bufSlider.addEventListener('change', sendSettings);
        kSlider.addEventListener('change', sendSettings);
        sigSlider.addEventListener('change', sendSettings);
        fpsInput.addEventListener('keydown', (e) => { if(e.key === 'Enter') sendSettings(); });

        window.addEventListener('DOMContentLoaded', loadSavedSettings);

        function fetchState() {
            if (isFrozen) return; 
            fetch('/state').then(res => res.json()).then(data => {
                if (data.disconnected) {
                    hudStatus.innerText = "⚠ OAK-D DISCONNECTED";
                    hudStatus.style.color = "#ff0000";
                    hudFps.innerText = "FPS: 0.0 | Mot: 0.0";
                    requestAnimationFrame(fetchState);
                    return;
                }
                if(data.rgb) streamRgb.src = "data:image/jpeg;base64," + data.rgb;
                if(data.disp) streamDisp.src = "data:image/jpeg;base64," + data.disp;
                
                hudFps.innerText = `FPS: ${data.fps.toFixed(1)} | Mot: ${data.motion.toFixed(1)}`;
                
                if (!data.stable) {
                    hudStatus.innerText = "MOVING - CLEARING BUF";
                    hudStatus.style.color = "#ff0000";
                } else if (data.buf_len < data.max_buf) {
                    hudStatus.innerText = `STABILIZING: ${data.buf_len}/${data.max_buf}`;
                    hudStatus.style.color = "#ffff00";
                } else {
                    hudStatus.innerText = `LOCKED: ${data.max_buf}/${data.max_buf} (READY)`;
                    hudStatus.style.color = "#00ff00";
                }
                requestAnimationFrame(fetchState);
            }).catch(err => { setTimeout(fetchState, 500); });
        }
        fetchState();
        
        function colorForIndex(i) { return COLORS[i % COLORS.length]; }
        
        function redrawCanvas() {
            ctx.clearRect(0, 0, CAM_W, CAM_H);
            measurements.forEach((m, i) => {
                const col = colorForIndex(i);
                const [x1, y1] = m.p1;
                const [x2, y2] = m.p2;

                ctx.strokeStyle = col; ctx.lineWidth = 2; ctx.beginPath();
                ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();

                [[x1,y1],[x2,y2]].forEach(([px, py]) => {
                    ctx.strokeStyle = col; ctx.lineWidth = 1.5; ctx.beginPath(); 
                    ctx.arc(px, py, 5, 0, 2 * Math.PI); ctx.stroke();
                    ctx.fillStyle = col; ctx.beginPath(); ctx.arc(px, py, 2, 0, 2 * Math.PI); ctx.fill();
                });

                const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
                ctx.font = 'bold 13px monospace';
                const tw = ctx.measureText(m.label).width;
                ctx.fillStyle = 'rgba(0,0,0,0.65)';
                ctx.fillRect(mx - tw / 2 - 4, my - 18, tw + 8, 20);
                ctx.fillStyle = col; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
                ctx.fillText(m.label, mx, my - 8);
            });

            if (pendingP1) {
                const col = colorForIndex(measurements.length);
                ctx.strokeStyle = col; ctx.lineWidth = 1.5; ctx.beginPath(); 
                ctx.arc(pendingP1[0], pendingP1[1], 5, 0, 2 * Math.PI); ctx.stroke();
                ctx.fillStyle = col; ctx.beginPath(); ctx.arc(pendingP1[0], pendingP1[1], 2, 0, 2 * Math.PI); ctx.fill();
                ctx.setLineDash([4, 3]); ctx.beginPath();
                ctx.moveTo(pendingP1[0] - 10, pendingP1[1]); ctx.lineTo(pendingP1[0] + 10, pendingP1[1]);
                ctx.moveTo(pendingP1[0], pendingP1[1] - 10); ctx.lineTo(pendingP1[0], pendingP1[1] + 10);
                ctx.stroke(); ctx.setLineDash([]);
            }
        }

        function updateList() {
            if (measurements.length === 0) { listDiv.innerHTML = ''; return; }
            listDiv.innerHTML = measurements.map((m, i) =>
                `<span style="color:${colorForIndex(i)}; margin-right:12px;">&#9632; #${i+1}: ${m.label}${m.warning ? ' &nbsp;&#9888;' : ''}</span>`
            ).join('');
        }

        function toggleMode() {
            if (measureMode === 'DIRECT') {
                measureMode = 'REF_1'; modeBtn.innerText = 'MODE: AUTO-TUNE K'; 
                if (isFrozen) statusDiv.innerText = "System Frozen. Click 2 points on KNOWN reference object.";
            } else {
                measureMode = 'DIRECT'; modeBtn.innerText = 'MODE: DIRECT 3D'; 
                if (isFrozen) statusDiv.innerText = "System Frozen. Hover to magnify, click 2 points.";
            }
            pendingP1 = null; redrawCanvas();
        }

        function toggleFreeze() {
            fetch('/toggle', { method: 'POST' }).then(res => res.json()).then(data => {
                isFrozen = (data.state === 'FROZEN');
                
                [bufSlider, kSlider, sigSlider, fpsInput].forEach(el => el.disabled = isFrozen);

                if(isFrozen) {
                    freezeBtn.innerText = 'RESUME (SPACE)'; 
                    hudZ.style.display = 'block';
                    
                    if (data.rgb) streamRgb.src = "data:image/jpeg;base64," + data.rgb;
                    if (data.disp) streamDisp.src = "data:image/jpeg;base64," + data.disp;
                    
                    fetch('/raw_depth').then(r => r.arrayBuffer()).then(buffer => {
                        window.depthData = new Uint16Array(buffer);
                    });
                    
                    let warnHTML = data.buf_len < data.max_buf ? ` [WARNING: Partial Buffer ${data.buf_len}/${data.max_buf}]` : "";
                    if (measureMode === 'DIRECT') statusDiv.innerText = `System Frozen${warnHTML}. Hover to magnify, click 2 points.`;
                    if (measureMode === 'REF_1') statusDiv.innerText = `System Frozen${warnHTML}. Click 2 points on KNOWN reference.`;
                } else {
                    freezeBtn.innerText = 'FREEZE (SPACE)'; 
                    statusDiv.innerText = 'Live Stream. Press SPACE to Freeze.';
                    hudZ.style.display = 'none';
                    mag.style.display = 'none'; 
                    syncLine.style.display = 'none';
                    dispVLine.style.display = 'none';
                    dispTarget.style.display = 'none';
                    debugDiv.innerText = '';
                    window.depthData = null;
                    clearPoints();
                    fetchState(); 
                }
            });
        }
        
        function takeSnapshot() { window.open('/snapshot', '_blank'); }
        document.addEventListener('keydown', (e) => { if(e.code === 'Space' && e.target !== fpsInput) { e.preventDefault(); toggleFreeze(); } });

        function clearPoints() {
            pendingP1 = null; measurements = [];
            document.querySelectorAll('.target-dot').forEach(e => e.remove());
            resultDiv.innerHTML = "0.0 cm"; debugDiv.innerText = '';
            redrawCanvas(); updateList();
            if(isFrozen) {
                if (measureMode === 'DIRECT') statusDiv.innerText = "System Frozen. Hover to magnify, click 2 points.";
                if (measureMode === 'REF_1') statusDiv.innerText = 'System Frozen. Click 2 points on KNOWN reference.';
            }
        }

        streamRgb.addEventListener('mousemove', function(e) {
            if (!isFrozen) return;
            const rect = streamRgb.getBoundingClientRect();
            const mouseX = e.clientX - rect.left; const mouseY = e.clientY - rect.top;
            
            syncLine.style.display = 'block';
            syncLine.style.left = mouseX + 'px';
            syncLine.style.top = mouseY + 'px';
            syncLine.style.width = (1290 - mouseX) + 'px';
            
            dispVLine.style.display = 'block';
            dispVLine.style.left = mouseX + 'px';
            dispTarget.style.display = 'block';
            dispTarget.style.left = mouseX + 'px';
            dispTarget.style.top = mouseY + 'px';

            mag.style.display = 'block'; mag.style.left = (mouseX + 15) + 'px'; mag.style.top = (mouseY - MAG_SIZE - 15) + 'px';
            const camX = mouseX * (CAM_W / rect.width); const camY = mouseY * (CAM_H / rect.height);
            const cx_round = Math.round(camX); const cy_round = Math.round(camY);
            
            if (window.depthData) {
                let z_mm = window.depthData[cy_round * CAM_W + cx_round];
                if (z_mm > 0) hudZ.innerText = `Z: ${(z_mm / 10).toFixed(1)} cm`;
                else hudZ.innerText = `Z: ---`;
            }
            
            mctx.clearRect(0, 0, MAG_SIZE, MAG_SIZE);
            mctx.drawImage(streamRgb, camX - (MAG_SIZE / 2 / MAG_ZOOM), camY - (MAG_SIZE / 2 / MAG_ZOOM), MAG_SIZE / MAG_ZOOM, MAG_SIZE / MAG_ZOOM, 0, 0, MAG_SIZE, MAG_SIZE);
            mctx.strokeStyle = 'rgba(255, 0, 0, 0.8)'; mctx.lineWidth = 1; mctx.beginPath();
            mctx.moveTo(MAG_SIZE / 2, 0); mctx.lineTo(MAG_SIZE / 2, MAG_SIZE);
            mctx.moveTo(0, MAG_SIZE / 2); mctx.lineTo(MAG_SIZE, MAG_SIZE / 2); mctx.stroke();
            mctx.fillStyle = 'red'; mctx.beginPath(); mctx.arc(MAG_SIZE/2, MAG_SIZE/2, 2, 0, 2 * Math.PI); mctx.fill();
        });

        streamRgb.addEventListener('mouseleave', () => { 
            mag.style.display = 'none'; 
            syncLine.style.display = 'none';
            dispVLine.style.display = 'none';
            dispTarget.style.display = 'none';
        });

        streamRgb.addEventListener('mousedown', function(e) {
            if(!isFrozen) { alert("Please freeze the feed (Spacebar) before measuring."); return; }
            const rect = streamRgb.getBoundingClientRect();
            const x = Math.round((e.clientX - rect.left) * (CAM_W / rect.width));
            const y = Math.round((e.clientY - rect.top) * (CAM_H / rect.height));

            if (!pendingP1) {
                pendingP1 = [x, y];
                statusDiv.innerText = `Point 1 locked (${x}, ${y}). Click point 2.`;
                redrawCanvas(); return;
            }

            const p1 = pendingP1; const p2 = [x, y];
            pendingP1 = null; statusDiv.innerText = "Calculating..."; resultDiv.innerText = "---";
            
            fetch('/measure', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ p1, p2, mode: measureMode })
            }).then(response => response.json()).then(data => {
                if (data.status === 'error') {
                    statusDiv.innerText = "Error: " + data.result; resultDiv.innerHTML = "ERR"; debugDiv.innerText = '';
                    redrawCanvas(); return;
                }
                const warnHTML = data.warning ? `<br><span style="color:#ff0; font-size:13px;">&#9888; ${data.warning}</span>` : '';
                
                if (measureMode === 'DIRECT') {
                    const label = `${data.dist_cm.toFixed(1)} cm`;
                    measurements.push({ p1, p2, label, warning: !!data.warning });
                    redrawCanvas(); updateList();
                    statusDiv.innerText = `#${measurements.length}: ${label} (Conf: ${data.confidence}) — click for next.`;
                    resultDiv.innerHTML = data.result + warnHTML;
                    debugDiv.innerText = `Z_avg=${data.avg_cam_dist_m}m | Pad1=${data.pad1}px | Pad2=${data.pad2}px`;
                    
                } else if (measureMode === 'REF_1') {
                    let actual = prompt(`Camera calculated ${data.dist_cm} cm.\n\nEnter ACTUAL length of reference in cm:`);
                    if (actual && !isNaN(actual) && parseFloat(actual) > 0) {
                        
                        let current_k = parseFloat(kSlider.value);
                        let raw_dist = data.dist_cm / current_k;
                        let new_k = parseFloat(actual) / raw_dist;
                        new_k = Math.max(0.5, Math.min(2.0, new_k));
                        
                        kSlider.value = new_k.toFixed(2);
                        document.getElementById('k-val').innerText = kSlider.value;
                        localStorage.setItem('triton_refraction_k', kSlider.value);
                        sendSettings();
                        
                        measureMode = 'DIRECT';
                        modeBtn.innerText = 'MODE: DIRECT 3D';
                        statusDiv.innerText = `Calibration saved! Slider K auto-set to ${new_k.toFixed(2)}. Click to measure.`;
                        resultDiv.innerHTML = `K = ${new_k.toFixed(2)}`;
                        
                        measurements = [];
                        redrawCanvas();
                        updateList();
                        
                    } else {
                        alert('Invalid input. Canceled.'); 
                        statusDiv.innerText = 'Frozen. Click to measure.';
                        redrawCanvas();
                    }
                }
            }).catch(err => { statusDiv.innerText = "Network Error."; redrawCanvas(); });
        });
    </script>
</body>
</html>
"""
HTML_PAGE_BYTES = HTML_PAGE.encode('utf-8')