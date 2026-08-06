#!/usr/bin/env python3
"""Generic REST API backend (LTX 2.3 / Grok 1.5 / H3).

One shape for all cloud sound sources. It is intentionally a thin, honest
skeleton: lazy-imports requests only when used, refuses to run without the
required auth env var (so the router silently skips it instead of 402-ing
like fish did), retries transient HTTP errors with backoff, and downloads the
finished audio to a temp file the loop then ingests.

Expected endpoint contract (fill these in per provider):
  POST {endpoint}        body={prompt, duration, seed, mood, stem, job_id}
                         -> {job_id, status:"queued"}
  GET  {endpoint}/{job_id}
                         -> {status:"done"|"failed"|"running", audio_url?}
  GET  {audio_url}       -> the wav bytes

Until you confirm each provider's real contract, submit() raises clearly.
Adding a new cloud source = one generators.json entry pointing here; no new
code.
"""
import os
import time

from . import Backend, _write_ticket, _read_ticket
from pipeline_lib import LIB

TMP = os.path.join(LIB, ".gen-tmp")


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


class ApiBackend(Backend):
    id = "api"

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
        payload = {
            "prompt": job.get("prompt_hint"), "duration": job.get("duration"),
            "seed": job.get("seed"), "mood": job.get("mood"),
            "stem": job.get("stem_profile"), "job_id": job.get("job_id"),
        }
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
        _write_ticket(job["job_id"], ticket)
        return ext_id

    def poll(self, ext_id):
        t = _read_ticket(ext_id)
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
            url = data.get("audio_url")
            if not url:
                return "failed", None, "done but no audio_url"
            os.makedirs(TMP, exist_ok=True)
            out = os.path.join(TMP, f"{ext_id}.wav")
            with open(out, "wb") as f:
                f.write(req.get(url, headers=self._headers(), timeout=120).content)
            return "done", out, None
        return "submitted", None, None
