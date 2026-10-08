#!/usr/bin/env python3
"""Compatibility entry point for the repository's shared packaging tool."""

from pathlib import Path
import sys


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    mod_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(mod_root.parent / "tools"))
    from package_mod import main

    main([mod_root.name, *sys.argv[1:]])
