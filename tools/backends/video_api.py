#!/usr/bin/env python3
"""Generic REST video API backend (Grok Video 1.5 / any OAuth video source).

Mirrors backends/api.py (cloud, Bearer/OAuth, poll + download) but for video:
  - payload adds `mode` (t2v/i2v/r2v) and conditionally `image_url` (i2v) /
    `reference_url` (r2v);
  - poll downloads the finished *video* (mp4) instead of an audio wav.

Expected endpoint contract (fill these in per provider):
  POST {endpoint}   body={mode, prompt, duration, seed, mood, scene, job_id,
                        image_url?, reference_url?}
                   -> {job_id, status:"queued"}
  GET  {endpoint}/{job_id}
                   -> {status:"done"|"failed"|"running", video_url?}
  GET  {video_url} -> the mp4 bytes

Until the real contract is confirmed, submit() raises clearly (endpoint still
REPLACE_ME). Adding another cloud video source = one generators.json entry
pointing here; no new code. Tickets live under video-library/.gen-tickets so
the video lane stays independent of the bgm lane.
"""
import json
import os
import time

from . import Backend
from pipeline_lib import VIDEO_LIB

VTICKETS = os.path.join(VIDEO_LIB, ".gen-tickets")
VTMP = os.path.join(VIDEO_LIB, ".gen-tmp")


def _requests():
    try:
        import requests
        return requests
    except ImportError:
        raise RuntimeError(
            "the `requests` package is required for API backends. "
            "Install it in the managed venv, or this backend stays excluded.")


def _backoff(n):
    return min(2 ** n, 30)


def _vwrite(job_id, payload):
    os.makedirs(VTICKETS, exist_ok=True)
    with open(os.path.join(VTICKETS, job_id + ".json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _vread(job_id):
    p = os.path.join(VTICKETS, job_id + ".json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


class VideoApiBackend(Backend):
    id = "video_api"

    def _auth(self):
        env = self.cfg.get("auth_env")
        if env and not os.environ.get(env):
            raise RuntimeError(
                f"backend {self.id} requires env {env} (set it, or it stays "
                f"excluded from routing).")
        ep = self.cfg.get("endpoint")
        if not ep or str(ep).startswith("REPLACE_ME"):
            raise RuntimeError(
                f"backend {self.id} endpoint not configured in generators.json "
                f"(set `endpoint` + `auth_env`).")

    def _headers(self):
        env = self.cfg.get("auth_env")
        tok = os.environ.get(env, "") if env else ""
        return {"Authorization": f"Bearer {tok}"} if tok else {}

    def submit(self, job):
        self._auth()
        req = _requests()
        ep = self.cfg["endpoint"]
        mode = job.get("mode", "t2v")
        payload = {
            "mode": mode,
            "prompt": job.get("prompt_hint"),
            "duration": job.get("duration"),
            "seed": job.get("seed"),
            "mood": job.get("mood"),
            "scene": job.get("scene"),
            "job_id": job.get("job_id"),
        }
        # mode-specific source media
        if mode == "i2v":
            img = job.get("source_image") or job.get("image")
            if img:
                payload["image_url"] = img
        elif mode == "r2v":
            ref = job.get("reference") or job.get("reference_image")
            if ref:
                payload["reference_url"] = ref
        for attempt in range(4):
            try:
                r = req.post(ep, json=payload, headers=self._headers(), timeout=60)
                if r.status_code >= 500:
                    raise RuntimeError(f"HTTP {r.status_code}")
                if r.status_code >= 400:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(_backoff(attempt))
        data = r.json()
        ext_id = data.get("job_id") or job["job_id"]
        ticket = {"job_id": job["job_id"], "backend": self.id, "ext_id": ext_id,
                  "endpoint": ep, "status": "submitted"}
        _vwrite(job["job_id"], ticket)
        return ext_id

    def poll(self, ext_id):
        t = _vread(ext_id)
        self._auth()
        req = _requests()
        ep = t.get("endpoint") or self.cfg["endpoint"]
        for attempt in range(4):
            try:
                r = req.get(f"{ep}/{t['ext_id']}", headers=self._headers(), timeout=60)
                if r.status_code >= 500:
                    raise RuntimeError(f"HTTP {r.status_code}")
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(_backoff(attempt))
        data = r.json()
        status = data.get("status")
        if status == "failed":
            return "failed", None, data.get("error", "provider reported failure")
        if status == "done":
            url = data.get("video_url")
            if not url:
                return "failed", None, "done but no video_url"
            os.makedirs(VTMP, exist_ok=True)
            out = os.path.join(VTMP, f"{ext_id}.mp4")
            with open(out, "wb") as f:
                f.write(req.get(url, headers=self._headers(), timeout=300).content)
            return "done", out, None
        return "submitted", None, None
