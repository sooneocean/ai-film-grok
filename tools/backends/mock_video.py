#!/usr/bin/env python3
"""Mock video backend: produces a real (tiny) MP4 via ffmpeg so the video
closed loop can be proven end-to-end with zero external video-API dependency.

Mirrors backends/mock.py (audio) for the video lane. Used by self_test.py and
generate_loop_video --demo. Never used in production routing. Requires ffmpeg
(the video lane's one external dep) to synthesize the clip; if ffmpeg is
absent, it writes a minimal placeholder .mp4 instead.
"""
import os
import shutil
import subprocess

from . import Backend, _write_ticket, _read_ticket
from pipeline_lib import VIDEO_LIB

VTMP = os.path.join(VIDEO_LIB, ".gen-tmp")


class MockVideoBackend(Backend):
    id = "mock_video"

    def submit(self, job):
        os.makedirs(VTMP, exist_ok=True)
        out = os.path.join(VTMP, job["job_id"] + ".mp4")
        dur = max(1, int(job.get("duration", 2)))
        ff = shutil.which("ffmpeg")
        if ff:
            r = subprocess.run([ff, "-y", "-f", "lavfi", "-i",
                                f"testsrc=size=320x240:rate=24:duration={dur}",
                                "-pix_fmt", "yuv420p", out],
                               capture_output=True, text=True)
            if r.returncode != 0:
                open(out, "wb").write(b"\x00\x00\x00\x18ftypmp42")
        else:
            open(out, "wb").write(b"\x00\x00\x00\x18ftypmp42")
        ticket = {"job_id": job["job_id"], "backend": "mock_video", "out": out, "status": "done"}
        _write_ticket(job["job_id"], ticket)
        return job["job_id"]

    def poll(self, ext_id):
        t = _read_ticket(ext_id)
        out = t.get("out")
        if out and os.path.exists(out):
            return "done", out, None
        return "submitted", None, None
