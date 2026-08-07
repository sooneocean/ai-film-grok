"""Honesty-rail R4.2 · forbid pgrep -f wide source match in production scripts."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

# Invocations only (not docs that say "never pgrep -f"):
#   ["pgrep", "-fl", ...]  /  ["pgrep", "-f", ...]  /  shell pgrep -f foo
_PGREP_INVOKE = re.compile(
    r"""(?x)
    (?:
        \[\s*["']pgrep["']\s*,\s*["'][^"']*-f[^"']*["']   # list form with -f/-fl
      | \[\s*["']pgrep["']\s*,\s*["']-f["']                 # ["pgrep", "-f"
      | (?<![`"'\w])pgrep\s+(?:-[a-zA-Z]*f[a-zA-Z]*\s+|\S+\s+)*  # shell pgrep …-f…
    )
    """
)

_SCAN_GLOBS = ("**/*.py",)


def _is_code_invoke_line(line: str) -> bool:
    s = line.strip()
    if not s or s.startswith("#"):
        return False
    # skip pure string/doc mentions without list/shell invoke
    if s.startswith(('"""', "'''", '"', "'")) and "pgrep" in s and "[" not in s:
        return False
    if "never" in s.lower() and "pgrep" in s:
        return False
    if "not pgrep" in s.lower() or "forbid" in s.lower():
        return False
    return True


class TestPgrepNoSourceMatch(unittest.TestCase):
    def test_no_pgrep_f_invocation_in_scripts(self) -> None:
        hits: list[str] = []
        for glob in _SCAN_GLOBS:
            for path in sorted(SCRIPTS.glob(glob)):
                if "__pycache__" in path.parts:
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                for i, line in enumerate(text.splitlines(), 1):
                    if not _is_code_invoke_line(line):
                        continue
                    # only flag list/shell invocations, not filter lists mentioning "pgrep"
                    if re.search(r"""\[\s*["']pgrep["']""", line) and re.search(
                        r"""["']-f[^"']*["']""", line
                    ):
                        rel = path.relative_to(SCRIPTS)
                        hits.append(f"{rel}:{i}:{line.strip()[:120]}")
                    elif re.search(r"(?<![\w`\"'])pgrep\s+-[a-zA-Z]*f", line):
                        rel = path.relative_to(SCRIPTS)
                        hits.append(f"{rel}:{i}:{line.strip()[:120]}")
        self.assertEqual(
            hits,
            [],
            msg=(
                "pgrep -f / -fl invocation forbidden in production scripts "
                "(self-match kill hazard). Use ps token filter. "
                f"hits={hits}"
            ),
        )

    def test_local_comfy_status_uses_ps_not_pgrep_invoke(self) -> None:
        from workflow_pack import local_comfy_client_status
        import inspect

        src = inspect.getsource(local_comfy_client_status)
        self.assertNotRegex(src, r"""\[\s*["']pgrep["']""")
        self.assertIn('"ps"', src)
        rep = local_comfy_client_status()
        self.assertIn("ok", rep)
        if not rep.get("skipped"):
            self.assertEqual(rep.get("method"), "ps_token")


if __name__ == "__main__":
    unittest.main()
