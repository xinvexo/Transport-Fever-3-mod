"""Install this mod with a local path for refreshing its read-only checker."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
mod_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(mod_root.parent / 'tools'))
from package_mod import ModPackage, MOD_RESOURCES

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent', type=Path)
    parser.add_argument('--enable-checker',action='store_true',help='Explicitly enable the costly native comparison checker')
    parser.add_argument('--observe',action='store_true',help='Only log existing preview results; never calculate proposals')
    parser.add_argument('--validate-twelve',action='store_true',help='One idle-only native acceptance run of the twelve supported variants')
    args = parser.parse_args()
    package = ModPackage(mod_root, MOD_RESOURCES[mod_root.name])
    installed = package.install(args.parent)
    scripts = installed / 'content/interchanges'
    directory = json.dumps(scripts.as_posix(), ensure_ascii=False)
    enabled = 'true' if args.enable_checker else 'false'
    observe = 'true' if args.observe else 'false'
    validate = 'true' if args.validate_twelve else 'false'
    (scripts / 'diagnostic_config.lua').write_text(
        f'return {{ enabled = {enabled}, observe = {observe}, validateTwelve = {validate}, directory = {directory}, loader = loadfile }}\n', encoding='utf-8')
    print(f'Installed diagnostic build: {installed}')
