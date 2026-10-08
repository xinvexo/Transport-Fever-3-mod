#!/usr/bin/env python3
"""Package selected mods (all by default) and optionally install them locally."""

import argparse
import json
from pathlib import Path
import re
import shutil
import stat
import zipfile


ROOT = Path(__file__).resolve().parents[1]
BASE_RESOURCES = ("mod.json", "_metadata", "content")
MOD_RESOURCES = {
    "auto_alternatives": (*BASE_RESOURCES, "strings.json"),
    "auto_signal": (*BASE_RESOURCES, "strings.json"),
    "bulldozer_lines": (*BASE_RESOURCES, "strings.json"),
    "chinese_map_names": (*BASE_RESOURCES, "strings.json"),
    "clear_catchment": BASE_RESOURCES,
    "interchange_pack": (*BASE_RESOURCES, "strings.json"),
    "line_names": (*BASE_RESOURCES, "strings.json"),
    "line_vehicle_colors": BASE_RESOURCES,
    "station_rows": BASE_RESOURCES,
    "tidy_fields": (*BASE_RESOURCES, "strings.json"),
}


def is_link(path):
    """Include Windows junctions and other reparse points, even on Python 3.10."""
    return path.is_symlink() or bool(
        getattr(path.lstat(), "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def ignored(path):
    return (path.name.lower() in {".ds_store", "thumbs.db", "desktop.ini", "__pycache__"}
            or path.name.startswith("._") or path.suffix.lower() in {".pyc", ".pyo"})


def overlaps(left, right):
    return left == right or left in right.parents or right in left.parents


def check_tree(path):
    """Reject links before traversing or replacing an existing resource tree."""
    if is_link(path):
        raise ValueError(f"Refusing a linked resource or destination: {path}")
    if path.is_dir():
        for child in path.iterdir():
            check_tree(child)


class ModPackage:
    def __init__(self, root, resources=BASE_RESOURCES):
        self.root = root.resolve()
        self.resources = resources
        manifest = json.loads((self.root / "mod.json").read_text(encoding="utf-8"))
        self.mod_id = manifest.get("modId") if isinstance(manifest, dict) else None
        if not isinstance(self.mod_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", self.mod_id):
            raise ValueError(f"Invalid Mod ID in {self.root / 'mod.json'}")

    def resource_files(self):
        def visit(path):
            if ignored(path):
                return
            if is_link(path):
                raise ValueError(f"Refusing a linked resource: {path}")
            if path.is_dir():
                for child in sorted(path.iterdir()):
                    yield from visit(child)
            elif path.is_file():
                yield path
            else:
                raise ValueError(f"Unsupported resource: {path}")

        for name in self.resources:
            source = self.root / name
            if not source.exists():
                raise ValueError(f"Missing mod resource: {source}")
            yield from visit(source)

    def package(self):
        files = list(self.resource_files())
        directory = self.root / "dist"
        if directory.exists() or directory.is_symlink():
            check_tree(directory)
        directory.mkdir(exist_ok=True)
        archive_path = directory / f"{self.mod_id}.zip"
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for source in files:
                archive.write(source, (Path(self.mod_id) / source.relative_to(self.root)).as_posix())
        return archive_path

    def install(self, parent):
        files = list(self.resource_files())
        parent = parent.expanduser().resolve()
        destination = parent / self.mod_id
        if destination.exists() or destination.is_symlink():
            if is_link(destination):
                raise ValueError(f"Refusing a linked destination: {destination}")
        resolved = destination.resolve()
        if resolved.parent != parent or overlaps(resolved, self.root) or overlaps(resolved, ROOT):
            raise ValueError(f"Refusing an installation overlapping the source repository: {destination}")
        if destination.exists():
            try:
                manifest = json.loads((destination / "mod.json").read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                raise ValueError(f"Refusing to overwrite an unrecognized mod: {destination}") from error
            if not isinstance(manifest, dict) or manifest.get("modId") != self.mod_id:
                raise ValueError(f"Refusing to overwrite a different mod: {destination}")

        # Validate every replacement before deleting anything. Only the resource
        # whitelist is replaced; sibling mods and other top-level files remain.
        for name in self.resources:
            target = destination / name
            if target.exists() or target.is_symlink():
                check_tree(target)
        destination.mkdir(parents=True, exist_ok=True)
        for name in self.resources:
            target = destination / name
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
        for source in files:
            target = destination / source.relative_to(self.root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mods", nargs="*", metavar="MOD",
                        help="Mod directories; the existing positional form is also supported")
    parser.add_argument("--mods", dest="selected_mods", nargs="+", action="extend", metavar="MOD",
                        help="Only process these mods; defaults to all: " + ", ".join(MOD_RESOURCES))
    parser.add_argument("--install", type=Path, metavar="TARGET_PARENT",
                        help="Also install each selected mod into TARGET_PARENT/<Mod ID>")
    args = parser.parse_intermixed_args(argv)
    if args.mods and args.selected_mods:
        parser.error("Use either --mods or positional mod names, not both")
    selected = list(dict.fromkeys(args.selected_mods or args.mods or MOD_RESOURCES))
    unknown = set(selected) - MOD_RESOURCES.keys()
    if unknown:
        parser.error("Unknown mod directories: " + ", ".join(sorted(unknown)))
    try:
        for name in selected:
            mod = ModPackage(ROOT / name, MOD_RESOURCES[name])
            print(f"Packaged: {mod.package()}")
            if args.install is not None:
                print(f"Installed: {mod.install(args.install)}")
    except (OSError, ValueError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
