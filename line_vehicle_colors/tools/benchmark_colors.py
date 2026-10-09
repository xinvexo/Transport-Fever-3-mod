"""Compare fleet synchronization in Lua 5.2; this is not an in-game benchmark."""

import argparse
import importlib.util
import json
from pathlib import Path
import statistics
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "line_vehicle_colors"
SOURCE = "line_vehicle_colors/content/line_vehicle_colors/colors.script.lua"
spec = importlib.util.spec_from_file_location("color_tests", MOD / "tests/test_colors.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def measure(source, count, line_count):
    case = fixture.ColorsTests()
    case.setUp()
    case.lua.execute(source)
    case.lua.execute("handlers = data()")
    case.g.fleetSize = count
    case.g.lineCount = line_count
    case.lua.execute("""
        local lines, members = {}, {}
        for line = 1, lineCount do
            addLine(line, vec(0.85, 0.1, 0.15))
            lines[#lines + 1], members[line] = line, {}
        end
        for offset = 0, fleetSize - 1 do
            local entity, line = 1000000 + offset, math.floor(offset * lineCount / fleetSize) + 1
            members[line][#members[line] + 1] = entity
            addVehicle(entity, line, {{part={modelId=1, color=vec(-1,-1,-1)}}})
        end
        api.engine.system.lineSystem.getLinesForPlayer = function() return lines end
        api.engine.system.transportVehicleSystem.getLineVehicles = function(line) return members[line] end
        sortItems, lineReads, modelReads = 0, 0, 0
        local sort, getComponent, modelGet = table.sort, api.engine.getComponent, api.res.modelRep.get
        table.sort = function(items, ...)
            sortItems = sortItems + #items
            return sort(items, ...)
        end
        api.engine.getComponent = function(entity, kind)
            if entity <= lineCount then lineReads = lineReads + 1 end
            return getComponent(entity, kind)
        end
        api.res.modelRep.get = function(id)
            modelReads = modelReads + 1
            return modelGet(id)
        end
        local started = os.clock()
        batches = 0
        repeat
            local before = #calls
            handlers.update(nil, state)
            assert(#calls - before <= 16, 'Command budget changed')
            batches = batches + 1
            assert(batches <= fleetSize, 'Queue failed to drain')
        until state.value.initialized and not state.value.lines and not state.value.vehicles
        elapsed = os.clock() - started
        assert(#calls == fleetSize, 'Vehicle commands changed')
        for index, command in ipairs(calls) do
            assert(command.entity == index + 999999, 'Vehicle ordering changed')
            assert(command.color.x == 0.85, 'Color changed')
        end
        local reads = lineReads
        handlers.update(nil, state)
        assert(lineReads == reads and #calls == fleetSize, 'Idle work changed')
    """)
    return {key: case.g[key] for key in ("elapsed", "batches", "sortItems", "lineReads", "modelReads")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref", help="Git revision to compare with the working tree")
    parser.add_argument("--vehicles", type=int, default=4096)
    parser.add_argument("--lines", type=int, default=64)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    if args.vehicles < 1 or args.runs < 1 or not 1 <= args.lines <= min(args.vehicles, 999999):
        parser.error("vehicles and runs must be positive; lines must be between 1 and min(vehicles, 999999)")
    sources = {}
    if args.baseline_ref:
        sources[args.baseline_ref] = subprocess.check_output(
            ["git", "show", f"{args.baseline_ref}:{SOURCE}"], cwd=ROOT, text=True)
    sources["working_tree"] = (ROOT / SOURCE).read_text(encoding="utf-8")
    report = {"scope": "Lua 5.2 simulated APIs and deep-copy state; not game frame time",
              "vehicles": args.vehicles, "lines": args.lines, "runs": args.runs, "results": {}}
    for label, source in sources.items():
        measurements = [measure(source, args.vehicles, args.lines) for _ in range(args.runs)]
        result = measurements[0].copy()
        result["elapsed"] = statistics.median(item["elapsed"] for item in measurements)
        report["results"][label] = result
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
