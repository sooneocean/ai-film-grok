import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backends.api import ApiBackend


class ApiReadinessGateTests(unittest.TestCase):
    def test_refuses_placeholder_endpoint(self):
        b = ApiBackend({"endpoint": "REPLACE_ME: https://x", "auth_env": "X"})
        with self.assertRaises(RuntimeError):
            b._auth()

    def test_refuses_missing_auth_env(self):
        b = ApiBackend({"endpoint": "https://api.x/v1", "auth_env": "MISSING_KEY"})
        # env not set -> must refuse (so router silently skips it, no 402)
        old = os.environ.pop("MISSING_KEY", None)
        try:
            with self.assertRaises(RuntimeError):
                b._auth()
        finally:
            if old is not None:
                os.environ["MISSING_KEY"] = old

    def test_ok_when_configured(self):
        b = ApiBackend({"endpoint": "https://api.x/v1", "auth_env": "OK_KEY"})
        os.environ["OK_KEY"] = "tok"
        try:
            b._auth()  # should not raise
        finally:
            os.environ.pop("OK_KEY", None)


if __name__ == "__main__":
    unittest.main()
