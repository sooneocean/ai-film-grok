import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from breaker import CircuitBreaker


class BreakerTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="aifilm-breaker-")
        self.path = os.path.join(self.d, "breaker.json")
        self.b = CircuitBreaker(state_path=self.path, failure_threshold=3, cooldown_sec=600)

    def test_closed_initially(self):
        self.assertFalse(self.b.is_open("x"))

    def test_trips_after_threshold(self):
        for _ in range(3):
            self.b.record_failure("x")
        self.assertTrue(self.b.is_open("x"))

    def test_open_set(self):
        self.b.record_failure("x"); self.b.record_failure("x"); self.b.record_failure("x")
        self.assertIn("x", self.b.open_set())

    def test_success_resets(self):
        for _ in range(3):
            self.b.record_failure("x")
        self.assertTrue(self.b.is_open("x"))
        self.b.record_success("x")
        self.assertFalse(self.b.is_open("x"))

    def test_half_open_after_cooldown(self):
        for _ in range(3):
            self.b.record_failure("x")
        self.assertTrue(self.b.is_open("x"))
        # simulate cooldown elapsed
        self.b.state["x"]["last_failure"] = time.time() - 1000
        self.assertFalse(self.b.is_open("x"))  # trial allowed

    def test_persists(self):
        for _ in range(3):
            self.b.record_failure("x")
        b2 = CircuitBreaker(state_path=self.path, failure_threshold=3, cooldown_sec=600)
        self.assertTrue(b2.is_open("x"))


if __name__ == "__main__":
    unittest.main()
