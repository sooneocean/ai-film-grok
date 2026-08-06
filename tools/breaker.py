#!/usr/bin/env python3
"""Backend circuit-breaker: stop hammering a backend that keeps failing.

Pure stdlib, state persisted next to the catalog so the breaker survives
across generate_loop invocations. A backend is "open" (excluded from routing)
after `failure_threshold` consecutive failures, and stays open for
`cooldown_sec` before a single trial call is allowed (half-open). Any success
clears the breaker.

    from breaker import CircuitBreaker
    b = CircuitBreaker()
    if b.is_open("ltx23"):        # skip in routing
        ...
    try:
        submit(...)
        b.record_success("ltx23")
    except Exception:
        b.record_failure("ltx23")  # may trip the breaker
"""
import json
import os
import time

from pipeline_lib import LIB

STATE_PATH = os.path.join(LIB, ".breaker.json")


class CircuitBreaker:
    def __init__(self, state_path=STATE_PATH, failure_threshold=3, cooldown_sec=600):
        self.path = state_path
        self.ft = failure_threshold
        self.cd = cooldown_sec
        self.state = self._load()

    # --- persistence ---
    def _load(self):
        if os.path.exists(self.path):
            try:
                return json.load(open(self.path, encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2)
        os.replace(tmp, self.path)

    # --- core ---
    def _now(self):
        return time.time()

    def is_open(self, bid):
        """True if the backend should be skipped (tripped + cooldown not elapsed)."""
        s = self.state.get(bid)
        if not s:
            return False
        if s.get("failures", 0) >= self.ft:
            if self._now() - s.get("last_failure", 0) >= self.cd:
                # cooldown elapsed -> half-open: allow one trial attempt
                return False
            return True
        return False

    def record_failure(self, bid):
        s = self.state.get(bid, {"failures": 0, "last_failure": 0})
        s["failures"] = s.get("failures", 0) + 1
        s["last_failure"] = self._now()
        self.state[bid] = s
        self._save()

    def record_success(self, bid):
        if bid in self.state:
            self.state.pop(bid)
            self._save()

    def open_set(self):
        return {bid for bid in self.state if self.is_open(bid)}

    def status(self):
        return {bid: {"failures": s.get("failures", 0),
                      "open": self.is_open(bid),
                      "last_failure": s.get("last_failure")}
                for bid, s in self.state.items()}

    def reset(self, bid=None):
        if bid:
            self.state.pop(bid, None)
        else:
            self.state = {}
        self._save()


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", nargs="?", const="*", default=None,
                    help="reset breaker for a backend id, or '*' for all")
    args = ap.parse_args()
    b = CircuitBreaker()
    if args.reset:
        if args.reset == "*":
            b.reset()
            print("reset all breakers")
        else:
            b.reset(args.reset)
            print(f"reset breaker for {args.reset}")
    else:
        st = b.status()
        if not st:
            print("no breaker state")
        for bid, s in sorted(st.items()):
            flag = "OPEN" if s["open"] else "closed"
            print(f"  {bid:10} {flag:6} failures={s['failures']}")


if __name__ == "__main__":
    main()
