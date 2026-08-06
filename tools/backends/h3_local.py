#!/usr/bin/env python3
"""Local H3 video backend (RTX 5090): t2v / i2v / r2v.

Mirrors backends/acestep.py (scripted reflux): submit writes a job ticket
recording the exact H3 command the operator should run on the 5090 (with
mode-specific placeholders), and returns the job id. poll() watches the
configured output directory for the produced .mp4; once the operator runs H3
and the file lands, poll flips to done and the loop ingests it. Human triggers
the GPU run; automation handles everything after. Tickets live under
video-library/.gen-tickets.
"""
import json
import os

from . import Backend
from pipeline_lib import VIDEO_LIB, ROOT

VTICKETS = os.path.join(VIDEO_LIB, ".gen-tickets")


def _vwrite(job_id, payload):
    os.makedirs(VTICKETS, exist_ok=True)
    with open(os.path.join(VTICKETS, job_id + ".json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _vread(job_id):
    p = os.path.join(VTICKETS, job_id + ".json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


class H3LocalBackend(Backend):
    id = "h3_local"

    def submit(self, job):
        inv = self.cfg.get("invocation", {})
        watch = os.path.join(ROOT, inv.get("watch_dir", "video-library/pending"))
        out_name = inv.get("out_pattern", "{job_id}.mp4").format(job_id=job["job_id"])
        out = os.path.join(watch, out_name)
        mode = job.get("mode", "t2v")
        cmd = inv.get("cmd", "echo H3_PLACEHOLDER").format(
            mode=mode, seed=job.get("seed", 0), prompt=job.get("prompt_hint", ""),
            image=job.get("source_image") or "", reference=job.get("reference") or "",
            duration=job.get("duration", 30), resolution=job.get("resolution", "1080p"),
            out=out, job_id=job["job_id"])
        ticket = {"job_id": job["job_id"], "backend": "h3", "cmd": cmd,
                  "out": out, "status": "submitted"}
        _vwrite(job["job_id"], ticket)
        print(f"  [h3] ticket written. Run on 5090:\n    {cmd}")
        return job["job_id"]

    def poll(self, ext_id):
        t = _vread(ext_id)
        out = t.get("out")
        if out and os.path.exists(out):
            return "done", out, None
        return "submitted", None, None
