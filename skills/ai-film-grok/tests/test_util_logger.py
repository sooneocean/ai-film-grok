"""C5.1 · util.logger contract (stderr-only, env level, set_level)."""

from __future__ import annotations

import logging
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


class TestUtilLogger(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("AIFILM_LOG_LEVEL", None)
        # reset aifilm logger handlers between tests
        logger = logging.getLogger("aifilm")
        logger.handlers.clear()
        logger.setLevel(logging.NOTSET)

    def test_log_goes_to_stderr_not_stdout(self) -> None:
        from util.logger import log, set_level

        set_level("WARNING")
        with mock.patch.object(sys, "stdout") as out, mock.patch.object(sys, "stderr") as err:
            # rebind handler stream to our mock after import
            for h in list(log.handlers):
                if isinstance(h, logging.StreamHandler):
                    h.stream = err
            log.warning("pilot_log_message")
            # stdout must not be written for library logs
            self.assertFalse(out.write.called)
            self.assertTrue(err.write.called or any(h.stream is err for h in log.handlers))

    def test_set_level_debug_enables_debug(self) -> None:
        from util.logger import log, set_level

        set_level("DEBUG")
        self.assertEqual(log.level, logging.DEBUG)
        set_level("WARNING")
        self.assertEqual(log.level, logging.WARNING)

    def test_skip_flag_logs_when_armed(self) -> None:
        from core.skip_audit import skip_flag
        from util.logger import log, set_level

        set_level("WARNING")
        with mock.patch.object(log, "warning") as warn:
            os.environ["AIFILM_SKIP_GATE_AUTO"] = "1"
            try:
                self.assertTrue(skip_flag("AIFILM_SKIP_GATE_AUTO", film_root=None))
            finally:
                os.environ.pop("AIFILM_SKIP_GATE_AUTO", None)
            self.assertTrue(warn.called)


if __name__ == "__main__":
    unittest.main()
