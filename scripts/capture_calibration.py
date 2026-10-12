from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import threading
import time
import webbrowser

import cv2
from PIL import Image
from djitellopy import Tello

folder = Path("calibration_images") / time.strftime("%Y%m%d_%H%M%S")
folder.mkdir(parents=True)
lock = threading.Lock()
shared = {
    "jpeg": None, "image": None, "found": False,
    "stamp": 0, "saved": 0, "capture": False,
    "notice": "Waiting for camera..."
}

PAGE = b"""<!doctype html>
<title>Tello Camera Calibration</title>
<style>
body{background:#14202c;color:white;font:20px system-ui;margin:30px}
img{width:800px;max-width:100%;background:black}
button{font-size:22px;padding:12px;margin:15px 0}
</style>
<h1>Tello camera calibration</h1>
<p>Motors stopped. Move only the checkerboard.</p>
<img id="video"><br>
<button onclick="capture()">Capture this pose</button>
<p id="status">Waiting...</p>
<p>Show all 7 x 5 inner corners. Hold still before capturing.
Change position, distance and tilt between captures.</p>
<script>
let stopped=false;
async function refresh(){
 if(stopped)return;
 try{
  const response=await fetch('/frame.jpg?t='+Date.now());
  if(response.ok){
   const url=URL.createObjectURL(await response.blob());
   const image=document.getElementById('video');
   const old=image.src;
   image.src=url;
   if(old.startsWith('blob:'))URL.revokeObjectURL(old);
  }
  const state=await(await fetch('/state')).json();
  document.getElementById('status').textContent=
   (state.found?'BOARD DETECTED':'BOARD NOT DETECTED')+
   ' | Saved: '+state.saved+' | '+state.notice;
 }catch(e){
  document.getElementById('status').textContent='Preview disconnected';
 }
 setTimeout(refresh,150);
}
async function capture(){
 await fetch('/capture',{method:'POST'});
}
refresh();
</script>"""

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        with lock:
            if self.path.startswith("/frame.jpg"):
                body, kind = shared["jpeg"], "image/jpeg"
            elif self.path == "/state":
                fresh = time.monotonic()-shared["stamp"] < 1.5
                body = json.dumps({
                    "found": shared["found"] and fresh,
                    "saved": shared["saved"],
                    "notice": shared["notice"]
                }).encode()
                kind = "application/json"
            else:
                body, kind = PAGE, "text/html"
        self.send_response(200 if body else 503)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body or b"Waiting")
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        if self.path != "/capture":
            self.send_error(404)
            return
        with lock:
            shared["capture"] = True
        self.send_response(202)
        self.end_headers()

    def log_message(self, *args):
        pass

server = ThreadingHTTPServer(("127.0.0.1", 8080), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
tello = Tello()

try:
    tello.connect()
    tello.streamon()
    reader = tello.get_frame_read()

    print("Open http://127.0.0.1:8080", flush=True)
    print("Capture lasts up to 90 seconds. Ctrl+C stops early.",
          flush=True)
    webbrowser.open("http://127.0.0.1:8080")
    deadline = time.monotonic()+90
    last_frame = None

    while time.monotonic() < deadline:
        frame = reader.frame
        if frame is None or frame.shape[:2] != (720, 960):
            time.sleep(0.05)
            continue

        # Process only when the decoder supplies a new frame object.
        if frame is last_frame:
            time.sleep(0.02)
            continue
        last_frame = frame

        rgb = cv2.resize(frame.copy(), (320, 240),
                         interpolation=cv2.INTER_AREA)
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        found, corners = cv2.findChessboardCornersSB(gray, (7, 5))

        # Save the original image, without drawn calibration corners.
        with lock:
            requested = shared["capture"]
            shared["capture"] = False
            if requested:
                if found:
                    path = folder / f"image_{shared['saved']+1:03d}.png"
                    if cv2.imwrite(str(path), bgr):
                        shared["saved"] += 1
                        shared["notice"] = "Saved. Change the board pose."
                        print(f"Saved {path.name}", flush=True)
                    else:
                        shared["notice"] = "Could not save image."
                else:
                    shared["notice"] = "Not saved: board not detected."

        preview = bgr.copy()
        if found:
            cv2.drawChessboardCorners(preview, (7, 5), corners, found)
        preview_rgb = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)
        output = io.BytesIO()
        Image.fromarray(preview_rgb).save(
            output, format="JPEG", quality=90)

        with lock:
            shared["jpeg"] = output.getvalue()
            shared["found"] = bool(found)
            shared["stamp"] = time.monotonic()
        time.sleep(0.1)

except KeyboardInterrupt:
    print("Capture stopped.")
except Exception as error:
    print("Capture failed:", error)
finally:
    try:
        tello.end()
    except Exception as error:
        print("Cleanup:", error)
    server.shutdown()
    server.server_close()

print(f"Saved {shared['saved']} images in {folder}")
