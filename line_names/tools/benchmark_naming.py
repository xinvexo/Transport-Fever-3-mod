"""Compare synchronous naming plans in Lua 5.2; this is not a game benchmark."""
import argparse
import json
from pathlib import Path
import statistics
import subprocess

from lupa.lua52 import LuaRuntime

MOD = Path(__file__).resolve().parents[1]
ROOT = MOD.parent

FIXTURE = r'''
benchLines,benchTowns={}, {[1]={},[2]={}}
components[1]={TOWN={},name='北京'}
components[2]={TOWN={},name='天津'}
components[100]={INDUSTRY={stockList=120,construction=110},name='北京 煤矿'}
components[101]={INDUSTRY={stockList=121,construction=111},name='天津 钢铁厂'}
components[110]={CONSTRUCTION={},town=1}
components[111]={CONSTRUCTION={},town=2}
components[120]={STOCK_LIST={stocks={{type=1}}}};stockCargo[120]={{0}}
components[121]={STOCK_LIST={stocks={{type=0}}}};stockCargo[121]={{0}}
for i=1,buildingCount do
  local id,town=100000+i*3,i%2+1
  components[id]={TOWN_BUILDING={stockList=id+1,personCapacity=id+2,town=town}}
  components[id+1]={STOCK_LIST={stocks={{type=0}}}};stockCargo[id+1]={{1}}
  components[id+2]={PERSON_CAPACITY={capacity=100}};pcBuildings[id+2]=id
  table.insert(benchTowns[town],id)
end
for i=0,1 do
  components[200+i]={STATION_GROUP={stations={220+i}},name='站点'..i,carriers={0}}
  components[220+i]={STATION={}};stationTowns[220+i]=i+1
  local building=benchTowns[i+1][1]
  catchables[220+i]={passenger={building+2},cargo={scenario=='factory' and 120+i or building+1}}
end
local cargo=scenario=='passenger' and 7 or (scenario=='factory' and 0 or 1)
for i=1,lineCount do
  local id,vehicle=1000+i,60000+i
  local load={};for c=0,7 do load[c+1]=c==cargo end
  local stops={}
  for j=0,1 do stops[j+1]={stationGroup=200+j,station=0,terminal=0,
    stopConfig={load=load},alternativeTerminals={}} end
  components[id]={LINE={stops=stops},name='原线路'..i,owner=7}
  components[vehicle]={TRANSPORT_VEHICLE={carrier=0}}
  capacities[id]={all={[cargo+1]={capacity=20,used=0}},current={}}
  vehicles[id]={vehicle};benchLines[i]=id
end
api.engine.getEntitiesWithComponent=function(kind)
  assert(kind=='INDUSTRY' or kind=='WAREHOUSE')
  return kind=='INDUSTRY' and {100,101} or {}
end
api.engine.system.lineSystem.getLinesForPlayer=function(player) assert(player==7);return benchLines end
api.engine.system.townBuildingSystem.getTown2BuildingMap=function() return benchTowns end
counts={}
local function count(key) counts[key]=(counts[key] or 0)+1 end
local nativeComponent=api.engine.getComponent
api.engine.getComponent=function(id,kind)
  count('component.'..kind);return nativeComponent(id,kind)
end
local nativeCapacity=api.engine.util.line.getLineCapacityUsages
api.engine.util.line.getLineCapacityUsages=function(id,all)
  count(all and 'capacity.all' or 'capacity.current');return nativeCapacity(id,all)
end
local nativeBuildings=api.engine.system.townBuildingSystem.getTown2BuildingMap
api.engine.system.townBuildingSystem.getTown2BuildingMap=function()
  count('townBuildingMap');return nativeBuildings()
end
function benchRun()
  advance();counts={};collectgarbage('collect')
  local started=os.clock()
  local result={}
  for i,id in ipairs(benchLines) do result[i]=benchRename({lineEntity=id}) end
  local elapsed=os.clock()-started
  assert(#warnings==0, table.concat(warnings,'\n'))
  return elapsed,counts,table.concat(result,'\n')
end
'''


def source(name, revision):
    path = f"line_names/content/line_names/{name}"
    if revision:
        return subprocess.check_output(["git", "show", f"{revision}:{path}"], cwd=ROOT, encoding="utf-8")
    return (ROOT / path).read_text(encoding="utf-8")


def measure(revision, scenario, lines, buildings, samples):
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute((MOD / "tests/runtime.lua").read_text(encoding="utf-8"))
    g = lua.globals()
    g.scenario, g.lineCount, g.buildingCount = scenario, lines, buildings
    lua.execute(FIXTURE)
    translations = json.loads((MOD / "strings.json").read_text(encoding="utf-8"))["zh_CN"]
    g.translations = lua.table_from(translations)
    lua.execute("_=function(key) return translations[key] or key end")
    modules = {name: lua.execute(source(name, revision)) for name in ("world.lua", "names.lua")}
    globals_module = lua.eval("{getDefaultWindowApi=function() return session end}")
    g.ug_require = lambda path: globals_module if path.startswith("::/") else modules[path.rsplit("/", 1)[-1]]
    lua.execute(source("naming.script.lua", revision))
    g.benchRename = g.data().renameFn
    g.benchRun()  # Warm the Lua allocator; every timed sample uses a new tick/plan.
    durations, counts, signature = [], None, None
    for _ in range(samples):
        elapsed, calls, signature = g.benchRun()
        durations.append(elapsed * 1000)
        current = dict(calls.items())
        assert counts is None or counts == current
        counts = current
    return {"median_ms": round(statistics.median(durations), 3), "api_calls": counts}, signature


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="3bb40cc")
    parser.add_argument("--lines", type=int, default=200)
    parser.add_argument("--buildings", type=int, default=10000)
    parser.add_argument("--samples", type=int, default=9)
    args = parser.parse_args()
    if args.lines < 1 or args.lines >= 10000 or args.buildings < 2 or args.samples < 1:
        parser.error("Use 1–9999 lines, at least 2 buildings and at least 1 sample")
    result = {"runtime": "Lua 5.2 simulated native APIs; not in-game FPS", "baseline": args.baseline,
              "lines_per_plan": args.lines, "town_buildings": args.buildings, "samples": args.samples, "cases": {}}
    for scenario in ("factory", "town_delivery", "passenger"):
        before, expected = measure(args.baseline, scenario, args.lines, args.buildings, args.samples)
        after, actual = measure(None, scenario, args.lines, args.buildings, args.samples)
        assert actual == expected, f"Naming changed in {scenario}"
        result["cases"][scenario] = {"baseline": before, "current": after, "identical_names": True}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
