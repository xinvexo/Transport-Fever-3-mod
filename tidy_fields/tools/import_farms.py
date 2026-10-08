#!/usr/bin/env python3
"""Import the vanilla farm model layouts for the construction update scripts."""

import argparse
from pathlib import Path
import re
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
FARMS = ("farm", "livestock_farm", "cotton_farm", "rubber_farm", "forest")


def import_farms(game):
    destination = ROOT / "content/tidy_fields/generated"
    destination.mkdir(parents=True, exist_ok=True)
    for farm in FARMS:
        with ZipFile(game / "base/content/industries" / f"{farm}.zip") as archive:
            source = archive.read(f"{farm}/{farm}.script.lua").decode("utf-8-sig")
        generated = source[source.index("local generatedData ="):source.index("--End Generated")].replace("\r\n", "\n")

        # These scripts live in our mod; resolve the vanilla models in their original scope.
        def resource(match):
            name = match.group(1)
            if not name.startswith("::"):
                name = "::" + (name if name.startswith("/") else f"/industries/{farm}/{name}")
            return '"' + name + '"'

        generated = re.sub(r'"([^"\n]+\.mdl)"', resource, generated)
        script = (
            '-- Vanilla generated model layout, imported by tools/import_farms.py.\n'
            'local industryutil = require "::/industries/industryutil.lua"\n'
            'local layout = require "xin_tidy_fields_1::/tidy_fields/layout.lua"\n\n'
            + generated
            + '\nfunction data()\n'
            + '  return { updateFn = layout.wrap(industryutil.makeIndustryUpdateFn(generatedData)) }\n'
            + 'end\n'
        )
        with (destination / f"{farm}.script.lua").open("w", encoding="utf-8", newline="\n") as output:
            output.write(script)
        print(f"Imported {farm}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game", type=Path, help="Transport Fever 3 installation directory")
    import_farms(parser.parse_args().game)
