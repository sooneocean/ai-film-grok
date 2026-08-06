#!/usr/bin/env python3
"""Mock backend: produces a real (silent) WAV so the closed loop can be
proven end-to-end with zero external dependencies. Used by self_test.py and
by generate_loop --demo. Never used in production routing.
"""
import os
import wave
import struct

from . import Backend, _write_ticket, _read_ticket
from pipeline_lib import LIB


class MockBackend(Backend):
    id = "mock"

    def submit(self, job):
        out = os.path.join(LIB, "pending", job["job_id"] + ".wav")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        sr = 44100
        dur = int(job.get("duration", 2))
        n = sr * dur
        # vary the tone per job so each produced file has a unique sha256
        # (real backends already differ; this only matters for the self-test)
        h = int(__import__("hashlib").sha256(job["job_id"].encode()).hexdigest()[:6], 16)
        freq = 120 + (h % 600)
        with wave.open(out, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(sr)
            frames = bytearray()
            for i in range(0, n, 1000):
                seg = min(1000, n - i)
                for s in range(seg):
                    v = int(24000 * __import__("math").sin(2 * 3.14159 * freq * (i + s) / sr))
                    frames += struct.pack("<h", v) * 2
            w.writeframes(bytes(frames))
        ticket = {"job_id": job["job_id"], "backend": "mock", "out": out, "status": "done"}
        _write_ticket(job["job_id"], ticket)
        return job["job_id"]

    def poll(self, ext_id):
        t = _read_ticket(ext_id)
        out = t.get("out")
        if out and os.path.exists(out):
            return "done", out, None
        return "submitted", None, None
