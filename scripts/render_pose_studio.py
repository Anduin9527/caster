"""Local-only WebGL cache builder. Open http://127.0.0.1:4186 after starting.

Uses an existing Pose Studio runtime copied into data/pose-studio-runtime.
Only writes validated render PNGs for the pinned catalog; never submits inference.
"""
from _config import API_URL, COMFY_URL, DATA_DIR
import hashlib
import io
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import unquote
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / 'integrations/pose-studio-library.json').read_text())
SIZES = tuple(p['id'] for p in json.loads((ROOT / 'integrations/canvas-presets.json').read_text()))
IDS = {str(p['id'])+'-'+size for p in MANIFEST['poses'] for size in SIZES}

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = unquote(self.path.split('?')[0])
        if path == '/':
            file = ROOT / 'scripts/pose-studio-render.html'; base = file.parent
        elif path == '/canvas-presets.json':
            file = ROOT / 'integrations/canvas-presets.json'; base = file.parent
        elif path == '/manifest.json':
            file = ROOT / 'integrations/pose-studio-library.json'; base = file.parent
        elif path.startswith('/runtime/'):
            base = DATA_DIR / 'pose-studio-runtime'; file = base / path[len('/runtime/'):]
        elif path.startswith('/library/'):
            base = DATA_DIR / 'pose-studio-library'; file = base / path[len('/library/'):]
        else:
            self.send_error(404); return
        if not file.resolve().is_relative_to(base.resolve()) or not file.is_file():
            self.send_error(404); return
        mime = {'.js':'text/javascript','.mjs':'text/javascript','.html':'text/html','.json':'application/json','.png':'image/png'}.get(file.suffix, 'application/octet-stream')
        self.send_response(200); self.send_header('Content-Type', mime); self.end_headers()
        self.wfile.write(file.read_bytes())
    def do_POST(self):
        identifier = self.path.removeprefix('/render/')
        length = int(self.headers.get('Content-Length', '0'))
        if self.headers.get('Origin') != 'http://127.0.0.1:4186' or self.path != '/render/' + identifier or identifier not in IDS or not 0 < length < 8_000_000:
            self.send_error(400); return
        blob = self.rfile.read(length)
        image = Image.open(io.BytesIO(blob)); image.load()
        if image.format != 'PNG' or image.size != tuple(map(int, identifier.split('-')[1].split('x'))):
            self.send_error(400); return
        output = io.BytesIO(); image.convert('RGB').save(output,format='PNG')
        directory = DATA_DIR / 'pose-studio-library/renders'; directory.mkdir(exist_ok=True)
        (directory / (identifier + '.png')).write_bytes(output.getvalue())
        self.send_response(200); self.end_headers(); self.wfile.write(b'OK')

if __name__ == '__main__':
    HTTPServer(('127.0.0.1',4186),Handler).serve_forever()
