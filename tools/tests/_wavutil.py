"""Shared helpers for the pipeline test-suite: synthesize WAVs in a tmp dir."""
import math
import os
import struct
import tempfile
import wave


def make_wav(path, sr=44100, dur=2.0, amp=24000, freq=220.0, channels=2, dc=0):
    """Write a (stereo) 16-bit sine WAV. amp in int16 units (max 32767)."""
    n = int(sr * dur)
    with wave.open(path, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sr)
        fr = bytearray()
        for i in range(n):
            v = int(amp * math.sin(2 * math.pi * freq * i / sr) + dc)
            v = max(-32768, min(32767, v))
            fr += struct.pack("<h", v) * channels
        w.writeframes(bytes(fr))
    return path


def tmp_wav(name="t.wav", **kw):
    d = tempfile.mkdtemp(prefix="aifilm-test-")
    return make_wav(os.path.join(d, name), **kw), d
