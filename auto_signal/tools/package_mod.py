#!/usr/bin/env python3
"""Package the game resources and optionally install this mod locally."""

import argparse
import json
from pathlib import Path
import shutil
import zipfile


ROOT = Path(__file__).resolve().parents[1]
MOD_ID = "xin_auto_signal_1"
RESOURCES = ("mod.json", "strings.json", "_metadata", "content")


def resource_files():
    for name in RESOURCES:
        source = ROOT / name
        if not source.exists():
            raise ValueError(f"Missing mod resource: {source}")
        if source.is_dir():
            yield from sorted(path for path in source.rglob("*") if path.is_file())
        else:
            yield source


def package():
    files = list(resource_files())
    archive_path = ROOT / "dist" / f"{MOD_ID}.zip"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for source in files:
            archive.write(source, (Path(MOD_ID) / source.relative_to(ROOT)).as_posix())
    return archive_path


def install(parent):
    destination = parent.expanduser().resolve() / MOD_ID
    if destination.exists():
        try:
            manifest = json.loads((destination / "mod.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ValueError(f"Refusing to overwrite an unrecognized mod: {destination}") from error
        if not isinstance(manifest, dict) or manifest.get("modId") != MOD_ID:
            raise ValueError(f"Refusing to overwrite a different mod: {destination}")

    destination.mkdir(parents=True, exist_ok=True)
    for name in RESOURCES:
        source, target = ROOT / name, destination / name
        if source.is_dir():
            # Replace only this mod's resource directories, including obsolete
            # scripts from an earlier version. Leave all sibling mods alone.
            if target.is_symlink() or target.is_file():
                target.unlink()
            elif target.exists():
                shutil.rmtree(target)
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--install",
        type=Path,
        metavar="TARGET_PARENT",
        help="Also install into TARGET_PARENT/xin_auto_signal_1",
    )
    arguments = parser.parse_args()
    try:
        archive_path = package()
        print(f"Packaged: {archive_path}")
        if arguments.install is not None:
            print(f"Installed: {install(arguments.install)}")
    except (OSError, ValueError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
