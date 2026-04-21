#!/usr/bin/env python3
"""
CSM Filler Server — persistent Sesame CSM 1B model for instant filler generation.

Stays loaded in memory. Receives text over HTTP, returns WAV audio.
Runs in the csm-mlx Python 3.12 venv (separate from the receptionist's Python 3.14).

Usage:
  python3 csm_filler_server.py          # starts on port 8766
  curl -X POST http://localhost:8766/generate -d 'Hmm, good question.' > /tmp/filler.wav
"""

import os
os.environ["NO_TORCH_COMPILE"] = "1"

import time
import json
import numpy as np
from http.server import HTTPServer, BaseHTTPRequestHandler
from huggingface_hub import hf_hub_download
from csm_mlx import CSM, csm_1b, generate
import audiofile
import tempfile
import random

# --- Config ---
PORT = 8766
FILLERS = [
    "Hmm, good question.",
    "Let me think about that.",
    "That's interesting.",
    "Good question.",
    "Let me see.",
    "Right, let me think.",
    "Interesting.",
    "Hmm, let me think.",
]

# --- Load model once ---
print("Loading CSM 1B model...")
t0 = time.time()
csm = CSM(csm_1b())
weight = hf_hub_download(repo_id="senstella/csm-1b-mlx", filename="ckpt.safetensors")
csm.load_weights(weight)
print(f"CSM loaded in {time.time() - t0:.2f}s")
print(f"Server ready on http://localhost:{PORT}")


class CSMHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "model": "csm-1b"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/generate":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8").strip()
            
            # Parse request — plain text or JSON
            text = body
            max_ms = 5000
            try:
                data = json.loads(body)
                text = data.get("text", body)
                max_ms = data.get("max_audio_length_ms", 5000)
            except (json.JSONDecodeError, TypeError):
                pass
            
            if not text:
                # No text provided — use a random filler
                text = random.choice(FILLERS)
            
            # Generate audio
            t0 = time.time()
            try:
                audio = generate(csm, text=text, speaker=0, context=[], max_audio_length_ms=max_ms)
                gen_time = time.time() - t0
                duration = len(audio) / 24000
                
                # Write to temp WAV
                tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                audiofile.write(tmp.name, np.asarray(audio), 24000)
                tmp.close()
                
                # Read back and send
                with open(tmp.name, "rb") as f:
                    wav_data = f.read()
                os.unlink(tmp.name)
                
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("X-Gen-Time", f"{gen_time:.3f}")
                self.send_header("X-Audio-Duration", f"{duration:.3f}")
                self.send_header("X-Text", text)
                self.end_headers()
                self.wfile.write(wav_data)
                
                print(f"  Generated: '{text[:40]}' in {gen_time:.2f}s ({duration:.2f}s audio)")
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
                print(f"  Error: {e}")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress default access logs


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", PORT), CSMHandler)
    print(f"CSM Filler Server listening on port {PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down")
        server.server_close()