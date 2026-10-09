"""Compare selection-driven Lua 5.2 UI renders; native rendering is not measured."""
import argparse
import importlib.util
import json
from pathlib import Path
import statistics
import subprocess

from lupa.lua52 import LuaRuntime

MOD = Path(__file__).resolve().parents[1]
ROOT = MOD.parent
spec = importlib.util.spec_from_file_location("bulldozer_ui_fixture", MOD / "tests/test_ui.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)

SCENE = r'''
names,entities,visible,carrierSets={},{},{},{}
for i=1,lineCount do
  names[i]=string.format('Line %05d',i)
  entities[i]=i;visible[i]=i%2==0;carrierSets[i]={[1]=true}
end
local native=api.engine.entityExists
api.engine.entityExists=function(id)
  reads.exists=(reads.exists or 0)+1;return native(id)
end
'''

RUN = r'''
render('XinBulldozerLinesEntry');flushEvents()
if onlyVisible then
  local filters={carriers={},onlyVisible=true}
  windowParams.filters:set(filters)
  windowParams.lines:set(lines.read(filters))
end
render('XinBulldozerLineWindow',windowParams)
render('XinBulldozerLinesEntry');flushEvents();drawBulldozer()
function benchRun()
  reads={names=0,filters=0,visible=0,sorts=0,exists=0}
  collectgarbage('collect')
  local started=os.clock()
  local window,viewer
  for i=1,iterations do
    windowParams.selected:set(i%2==1 and {[2]=true} or {})
    window=render('XinBulldozerLineWindow',windowParams)
    render('XinBulldozerLinesEntry');flushEvents()
    viewer=drawBulldozer()
  end
  local elapsed=os.clock()-started
  local keyParts={}
  for _,id in ipairs(find(window,'DataTable')[1].rowKeys) do keyParts[#keyParts+1]=id end
  local shown={}
  for _,line in ipairs(viewer.params.showLines) do shown[#shown+1]=line.entity end
  return elapsed,reads,table.concat(keyParts,',')..'/'..headerCheck(window).value..'/'..table.concat(shown,',')
end
'''


def source(name, revision):
    path = f"bulldozer_lines/content/bulldozer_lines/{name}"
    if revision:
        return subprocess.check_output(["git", "show", f"{revision}:{path}"], cwd=ROOT, encoding="utf-8")
    return (ROOT / path).read_text(encoding="utf-8")


def measure(revision, lines, iterations, samples, only_visible):
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(fixture.HARNESS)
    g = lua.globals()
    g.lineCount, g.iterations, g.onlyVisible = lines, iterations, only_visible
    lua.execute(SCENE)
    g.lines = lua.execute(source("lines.lua", revision))
    lua.execute(source("ui_entry.script.lua", revision))
    lua.execute(RUN)
    g.benchRun()
    times, counts, signature = [], None, None
    for _ in range(samples):
        elapsed, calls, signature = g.benchRun()
        times.append(elapsed * 1000 / iterations)
        current = {key: value / iterations for key, value in calls.items()}
        assert counts is None or counts == current
        counts = current
    return {"median_ms_per_selection_render": round(statistics.median(times), 3),
            "api_calls_per_selection_render": counts}, signature


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="3bb40cc")
    parser.add_argument("--lines", type=int, default=1000)
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--samples", type=int, default=7)
    args = parser.parse_args()
    if args.lines < 2 or args.iterations < 2 or args.samples < 1:
        parser.error("Use at least 2 lines, 2 iterations and 1 sample")
    result = {"runtime": "Lua 5.2 simulated UI/native APIs; not in-game FPS", "baseline": args.baseline,
              "lines": args.lines, "iterations": args.iterations, "samples": args.samples, "cases": {}}
    for visible in (False, True):
        before, expected = measure(args.baseline, args.lines, args.iterations, args.samples, visible)
        after, actual = measure(None, args.lines, args.iterations, args.samples, visible)
        assert actual == expected, "Table/selection/map results changed"
        result["cases"]["visible_half" if visible else "all_lines"] = {
            "baseline": before, "current": after, "identical_table_and_map": True}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
