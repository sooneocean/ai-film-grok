"""Tombstone — lipsync node service removed (v2.40)."""

from audio.lipsync_backend import LIPSYNC_FROZEN_MSG


def main() -> int:
    print(LIPSYNC_FROZEN_MSG)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
