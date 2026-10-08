"""Run each mod's tests in a separate process without generating build files."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MODS = tuple(sorted(path.name for path in ROOT.iterdir()
                    if (path / 'mod.json').is_file() and (path / 'tests').is_dir()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mods', nargs='*', help='Mod directories; defaults to all mods')
    args = parser.parse_args()
    selected = args.mods or MODS
    unknown = set(selected) - set(MODS)
    if unknown:
        parser.error('Unknown mod directories: ' + ', '.join(sorted(unknown)))
    failed = []
    suites = [('repository tools', ROOT, 'tools/tests')]
    suites.extend((mod, ROOT / mod, 'tests') for mod in selected)
    for name, directory, tests in suites:
        print(f'Running {name}', flush=True)
        result = subprocess.run(
            [sys.executable, '-B', '-X', 'utf8', '-m', 'unittest', 'discover', '-s', tests, '-v'],
            cwd=directory,
        )
        if result.returncode:
            failed.append(name)
    if failed:
        print('Failed: ' + ', '.join(failed), file=sys.stderr)
        return 1
    print(f'Passed: repository tools and {len(selected)} mod suites')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
