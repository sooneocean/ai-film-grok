#!/usr/bin/env python3
"""Local ACE-Step backend (RTX 5090).

submit() does NOT shell out to a placeholder command (that would drop a
garbage file into pending/). Instead it writes a job ticket recording the
exact command the operator should run on the 5090, and returns the job id.
poll() watches the configured output directory for the produced file; once
the operator runs ACE-Step and the .wav lands, poll flips to done and the
loop ingests it. This is the "scripted reflux" design: human triggers the
GPU run, automation handles everything after.
"""
import os

from . import Backend, _write_ticket, _read_ticket
from pipeline_lib import LIB, ROOT


class AceStepLocalBackend(Backend):
    id = "acestep"

    def submit(self, job):
        inv = self.cfg.get("invocation", {})
        watch = os.path.join(ROOT, inv.get("watch_dir", "bgm-library/pending"))
        out_name = inv.get("out_pattern", "{job_id}.wav").format(job_id=job["job_id"])
        out = os.path.join(watch, out_name)
        cmd = inv.get("cmd", "echo ACE_STEP_PLACEHOLDER").format(
            seed=job.get("seed", 0), mood=job.get("mood", ""),
            stem=job.get("stem_profile", ""), duration=job.get("duration", 30),
            out=out, job_id=job["job_id"])
        ticket = {"job_id": job["job_id"], "backend": "acestep", "cmd": cmd,
                  "out": out, "status": "submitted"}
        _write_ticket(job["job_id"], ticket)
        print(f"  [acestep] ticket written. Run on 5090:\n    {cmd}")
        return job["job_id"]

    def poll(self, ext_id):
        t = _read_ticket(ext_id)
        out = t.get("out")
        if out and os.path.exists(out):
            return "done", out, None
        return "submitted", None, None
