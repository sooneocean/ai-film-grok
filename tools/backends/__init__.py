#!/usr/bin/env python3
"""Generator backend abstraction.

A "backend" is any sound source that can turn a gap spec into an audio file:
the local ACE-Step on the 5090, LTX 2.3, Grok 1.5, H3, or a Mock used for
self-tests. The router and generate_loop only ever talk to this interface,
so plugging in a new source is purely a generators.json entry + (optionally)
a small subclass.

Every backend implements:
    submit(job) -> ext_id          # hand the job off, return an external id
    poll(ext_id) -> (status, audio_path|None, error)
        status in {submitted, running, done, failed}
"""
import abc
import os
import json
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline_lib import LIB

TICKETS = os.path.join(LIB, ".gen-tickets")


class Backend(abc.ABC):
    id = ""

    def __init__(self, cfg):
        self.cfg = cfg

    @abc.abstractmethod
    def submit(self, job):
        ...

    @abc.abstractmethod
    def poll(self, ext_id):
        ...


def _write_ticket(job_id, payload):
    os.makedirs(TICKETS, exist_ok=True)
    with open(os.path.join(TICKETS, job_id + ".json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _read_ticket(job_id):
    p = os.path.join(TICKETS, job_id + ".json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def get_backend(id, cfg):
    kind = cfg.get("kind")
    if id == "mock" or cfg.get("_mock"):
        from .mock import MockBackend
        return MockBackend(cfg)
    if cfg.get("_mock_video"):
        from .mock_video import MockVideoBackend
        return MockVideoBackend(cfg)
    if kind == "local":
        from .acestep import AceStepLocalBackend
        return AceStepLocalBackend(cfg)
    if kind == "api":
        from .api import ApiBackend
        return ApiBackend(cfg)
    if kind == "video_api":
        from .video_api import VideoApiBackend
        return VideoApiBackend(cfg)
    if kind == "video_local":
        from .h3_local import H3LocalBackend
        return H3LocalBackend(cfg)
    raise ValueError(f"unknown backend kind {kind!r} for {id}")
