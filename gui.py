HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Triton ROV Web Pilot</title>
    <style>
        body { background-color: #0a0a0a; color: #0f0; font-family: monospace; text-align: center; margin-top: 30px; }
        #hud-wrapper { position: relative; display: inline-block; border: 2px solid #0f0; box-shadow: 0px 0px 20px rgba(0,255,0,0.3); cursor: crosshair; }
        #video-stream { display: block; width: 640px; height: 360px; }
        #measure-canvas { position: absolute; top: 0; left: 0; width: 640px; height: 360px; pointer-events: none; }
        .target-dot { position: absolute; width: 8px; height: 8px; background: red; border-radius: 50%; transform: translate(-50%, -50%); pointer-events: none; z-index: 10; box-shadow: 0 0 5px red; }
        #panel { margin-top: 20px; padding: 15px; border: 1px solid #333; display: inline-block; background: #111; min-width: 550px; }
        .readout { font-size: 28px; color: #0ff; margin: 10px 0; font-weight: bold; }
        .btn { background: #0f0; color: #000; border: none; padding: 10px 20px; cursor: pointer; font-weight: bold; font-family: monospace; margin: 5px; }
        .btn:hover { background: #fff; }
        .btn-freeze { background: #ff0; }
        .btn-freeze:hover { background: #fff; }
        .btn-mode { background: #0af; color: #fff; }
        .btn-capture { background: #fff; color: #000; } 
        .btn-capture:hover { background: #ccc; }
        
        #debug-info { margin-top: 8px; font-size: 11px; color: #555; }
        #measure-list { margin-top: 10px; font-size: 13px; text-align: left; min-height: 20px; padding: 0 5px; }
        
        #magnifier {
            position: absolute; border: 2px solid #0ff; border-radius: 50%;
            box-shadow: 0 0 15px #0ff; pointer-events: none; display: none;
            z-index: 20; background-color: #000;
        }
    </style>
</head>
<body>
    <h2>TRITON ROV // TACTICAL WEB HUD</h2>
    <div id="hud-wrapper">
        <img id="video-stream" src="/stream" draggable="false" />
        <canvas id="measure-canvas" width="640" height="360"></canvas>
        <canvas id="magnifier" width="120" height="120"></canvas>
    </div>
    <br>
    <div id="panel">
        <div id="status" style="color:#aaa;">Live Stream. Press SPACE to Freeze.</div>
        <div id="result" class="readout">00.0 cm &plusmn; 0.0 cm</div>
        <div id="measure-list"></div>
        <br>
        <button id="freeze-btn" class="btn btn-freeze" onclick="toggleFreeze()">FREEZE (SPACE)</button>
        <button id="mode-btn" class="btn btn-mode" onclick="toggleMode()">MODE: DIRECT 3D</button>
        <button class="btn" onclick="clearPoints()">CLEAR ALL</button>
        <button id="capture-btn" class="btn btn-capture" onclick="takeSnapshot()">&#128248; SAVE TO PC</button>
        <div id="debug-info"></div>
    </div>
    
    <script>
        const wrapper = document.getElementById('hud-wrapper');
        const stream = document.getElementById('video-stream');
        const canvas = document.getElementById('measure-canvas');
        const ctx = canvas.getContext('2d');
        const resultDiv = document.getElementById('result');
        const statusDiv = document.getElementById('status');
        const freezeBtn = document.getElementById('freeze-btn');
        const modeBtn = document.getElementById('mode-btn');
        const debugDiv = document.getElementById('debug-info');
        const listDiv = document.getElementById('measure-list');
        
        const mag = document.getElementById('magnifier');
        const mctx = mag.getContext('2d');
        const MAG_ZOOM = 3, MAG_SIZE = 120, CAM_W = 640, CAM_H = 360;
        const COLORS = ['#ff4444','#44ff44','#44aaff','#ffff44','#ff44ff','#44ffdd','#ffaa44','#aa44ff'];
        
        let isFrozen = false;
        let measureMode = 'DIRECT';
        let scaleFactor = 1.0;
        let pendingP1 = null;
        let measurements = [];
        
        function colorForIndex(i) { return COLORS[i % COLORS.length]; }
        
        function redrawCanvas() {
            ctx.clearRect(0, 0, CAM_W, CAM_H);
            measurements.forEach((m, i) => {
                const col = colorForIndex(i);
                const [x1, y1] = m.p1;
                const [x2, y2] = m.p2;

                ctx.strokeStyle = col;
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.moveTo(x1, y1);
                ctx.lineTo(x2, y2);
                ctx.stroke();

                [[x1,y1],[x2,y2]].forEach(([px, py]) => {
                    ctx.strokeStyle = col; ctx.lineWidth = 1.5;
                    ctx.beginPath(); ctx.arc(px, py, 5, 0, 2 * Math.PI); ctx.stroke();
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
                ctx.strokeStyle = col; ctx.lineWidth = 1.5;
                ctx.beginPath(); ctx.arc(pendingP1[0], pendingP1[1], 5, 0, 2 * Math.PI); ctx.stroke();
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
                measureMode = 'REF_1'; modeBtn.innerText = 'MODE: SET REFERENCE'; modeBtn.style.background = '#f90';
                if (isFrozen) statusDiv.innerText = "System Frozen. Click 2 points on KNOWN reference object.";
            } else {
                measureMode = 'DIRECT'; scaleFactor = 1.0; modeBtn.innerText = 'MODE: DIRECT 3D'; modeBtn.style.background = '#0af';
                if (isFrozen) statusDiv.innerText = "System Frozen. Hover to magnify, click 2 points.";
            }
            pendingP1 = null; redrawCanvas();
        }

        function toggleFreeze() {
            fetch('/toggle', { method: 'POST' }).then(res => res.json()).then(data => {
                isFrozen = (data.state === 'FROZEN');
                if(isFrozen) {
                    freezeBtn.innerText = 'RESUME (SPACE)'; 
                    
                    let warnHTML = "";
                    if (data.buf_len < 60) {
                        statusDiv.style.color = '#ff0'; // Yellow warning
                        warnHTML = ` [WARNING: Partial Buffer ${data.buf_len}/60]`;
                    } else {
                        statusDiv.style.color = '#0ff'; // Standard cyan
                    }
                    
                    if (measureMode === 'DIRECT') statusDiv.innerText = `System Frozen${warnHTML}. Hover to magnify, click 2 points.`;
                    if (measureMode === 'REF_1') statusDiv.innerText = `System Frozen${warnHTML}. Click 2 points on KNOWN reference.`;
                    if (measureMode === 'REF_2') statusDiv.innerText = `Scale Active${warnHTML}. Click 2 points on UNKNOWN target.`;
                } else {
                    freezeBtn.innerText = 'FREEZE (SPACE)'; statusDiv.innerText = 'Live Stream. Press SPACE to Freeze.';
                    statusDiv.style.color = '#aaa'; mag.style.display = 'none'; debugDiv.innerText = '';
                    clearPoints();
                }
            });
        }
        
        function takeSnapshot() { window.open('/snapshot', '_blank'); }

        document.addEventListener('keydown', (e) => { if(e.code === 'Space') { e.preventDefault(); toggleFreeze(); } });

        function clearPoints() {
            pendingP1 = null; measurements = [];
            document.querySelectorAll('.target-dot').forEach(e => e.remove());
            resultDiv.innerHTML = "00.0 cm &plusmn; 0.0 cm"; debugDiv.innerText = '';
            redrawCanvas(); updateList();
            if(isFrozen) {
                if (measureMode === 'DIRECT') statusDiv.innerText = "System Frozen. Hover to magnify, click 2 points.";
                if (measureMode === 'REF_1') statusDiv.innerText = 'System Frozen. Click 2 points on KNOWN reference.';
                if (measureMode === 'REF_2') statusDiv.innerText = 'Scale Active. Click 2 points on UNKNOWN target.';
            }
        }

        wrapper.addEventListener('mousemove', function(e) {
            if (!isFrozen) return;
            const rect = stream.getBoundingClientRect();
            const mouseX = e.clientX - rect.left; const mouseY = e.clientY - rect.top;
            if (mouseX < 0 || mouseY < 0 || mouseX > rect.width || mouseY > rect.height) { mag.style.display = 'none'; return; }
            
            mag.style.display = 'block'; mag.style.left = (mouseX + 15) + 'px'; mag.style.top = (mouseY - MAG_SIZE - 15) + 'px';
            const camX = mouseX * (CAM_W / rect.width); const camY = mouseY * (CAM_H / rect.height);
            
            mctx.clearRect(0, 0, MAG_SIZE, MAG_SIZE);
            mctx.drawImage(stream, camX - (MAG_SIZE / 2 / MAG_ZOOM), camY - (MAG_SIZE / 2 / MAG_ZOOM), MAG_SIZE / MAG_ZOOM, MAG_SIZE / MAG_ZOOM, 0, 0, MAG_SIZE, MAG_SIZE);
            mctx.strokeStyle = 'rgba(255, 0, 0, 0.8)'; mctx.lineWidth = 1; mctx.beginPath();
            mctx.moveTo(MAG_SIZE / 2, 0); mctx.lineTo(MAG_SIZE / 2, MAG_SIZE);
            mctx.moveTo(0, MAG_SIZE / 2); mctx.lineTo(MAG_SIZE, MAG_SIZE / 2); mctx.stroke();
            mctx.fillStyle = 'red'; mctx.beginPath(); mctx.arc(MAG_SIZE/2, MAG_SIZE/2, 2, 0, 2 * Math.PI); mctx.fill();
        });

        wrapper.addEventListener('mouseleave', () => { mag.style.display = 'none'; });

        stream.addEventListener('mousedown', function(e) {
            if(!isFrozen) { alert("Please freeze the feed (Spacebar) before measuring."); return; }
            const rect = stream.getBoundingClientRect();
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
                    statusDiv.innerText = `#${measurements.length}: ${label} — click for next measurement.`;
                    resultDiv.innerHTML = data.result + warnHTML;
                    
                    if (data.avg_cam_dist_m !== undefined) {
                        debugDiv.innerText = 'Z_avg=' + data.avg_cam_dist_m + 'm';
                    }
                } else if (measureMode === 'REF_1') {
                    let actual = prompt(`Camera calculated ${data.dist_cm} cm.\\n\\nEnter ACTUAL length of reference in cm:`);
                    if (actual && !isNaN(actual) && parseFloat(actual) > 0) {
                        scaleFactor = parseFloat(actual) / data.dist_cm; measureMode = 'REF_2';
                        modeBtn.innerText = 'MODE: MEASURING TARGET'; modeBtn.style.background = '#f0f';
                        statusDiv.innerText = `Scale locked (${scaleFactor.toFixed(2)}x). Click to measure target.`;
                        resultDiv.innerHTML = 'Scale set.';
                    } else {
                        alert('Invalid input. Canceled.'); statusDiv.innerText = 'Frozen. Click to measure.';
                    }
                    redrawCanvas();
                } else if (measureMode === 'REF_2') {
                    const fd = (data.dist_cm * scaleFactor).toFixed(1);
                    const fu = (data.uncertainty_cm * scaleFactor).toFixed(1);
                    const label = `${fd} cm`;
                    measurements.push({ p1, p2, label, warning: !!data.warning });
                    redrawCanvas(); updateList();
                    statusDiv.innerText = `#${measurements.length}: ${label} \u00b1 ${fu} cm (corrected) — click for next.`;
                    resultDiv.innerHTML = `${fd} cm &plusmn; ${fu} cm` + warnHTML;
                }
            }).catch(err => { statusDiv.innerText = "Network Error."; redrawCanvas(); });
        });
    </script>
</body>
</html>
"""
HTML_PAGE_BYTES = HTML_PAGE.encode('utf-8')