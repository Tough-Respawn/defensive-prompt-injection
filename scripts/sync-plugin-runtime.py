#!/usr/bin/env python3
"""Copy the dependency-free Python runtime into self-contained plugin bundles."""

from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "dpi"
DESTINATIONS = [
    ROOT
    / "packages"
    / "codex"
    / "plugins"
    / "defensive-prompt-injection"
    / "runtime"
    / "dpi",
    ROOT
    / "packages"
    / "deepseek-harness"
    / "runtime"
    / "dpi",
]


def main() -> None:
    for destination in DESTINATIONS:
        destination.mkdir(parents=True, exist_ok=True)
        for source in SOURCE.glob("*.py"):
            shutil.copy2(source, destination / source.name)
        print(f"synced {SOURCE} -> {destination}")


if __name__ == "__main__":
    main()
