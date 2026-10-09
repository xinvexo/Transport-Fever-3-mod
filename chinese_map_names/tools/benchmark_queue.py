#!/usr/bin/env python3
"""Compare queue Lua work with a Git baseline; simulated API/state costs, not in-game FPS."""

import argparse
import json
from pathlib import Path
import statistics
import subprocess

from lupa.lua52 import LuaRuntime

ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "chinese_map_names"
FILES = ("events.script.lua", "queue.lua")

HARNESS = r'''
world, pending = {}, {}
metrics = {commands = 0, reads = 0, updates = 0, stateCopies = 0, commandTrace = 0}
local function copy(value)
  if type(value) ~= "table" then return value end
  local result = {}
  for k, v in pairs(value) do result[k] = copy(v) end
  return result
end
state = {
  get = function(self) metrics.stateCopies = metrics.stateCopies + 1; return copy(self.value) end,
  set = function(self, value) metrics.stateCopies = metrics.stateCopies + 1; self.value = copy(value) end,
}
api = {
  type = {ComponentType = {NAME = "name", TOWN = "town", CONSTRUCTION = "construction",
    INDUSTRY = "industry", STATION = "station", STATION_GROUP = "group", VEHICLE_DEPOT = "depot",
    WAREHOUSE = "warehouse", BASE_EDGE_STREET = "street", SIM_PERSON = "person"}},
  engine = {
    entityExists = function(entity) return world[entity] ~= nil end,
    getComponent = function(entity, kind)
      metrics.reads = metrics.reads + 1
      local item = world[entity]
      if kind == "name" then return item and {name = item.name} end
      if kind == "town" and entity <= townCount then return {} end
      if kind == "construction" and entity > townCount and entity <= townCount + factoryCount then return {} end
      if kind == "person" and entity > townCount + factoryCount then return {} end
    end,
    config = {getModParams = function() return {[""] = {}} end},
    util = {},
  },
}
local planner = {audit = function() return {samples = {}, remaining = 0} end,
  needsChineseName = function() return true end}
local names = {
  ownName = function(entity) return world[entity] and world[entity].name end,
  submitName = function(entity, name)
    assert(name == "新名称" .. entity)
    metrics.commands = metrics.commands + 1
    metrics.commandTrace = (metrics.commandTrace * 131 + entity * 17 + metrics.updates) % 2147483647
    pending[#pending + 1] = {entity = entity, name = name}
    return true
  end,
}
local modules = {
  ["xin_chinese_map_names_1::/chinese_map_names/plan.lua"] = planner,
  ["xin_chinese_map_names_1::/chinese_map_names/entity_names.lua"] = names,
  ["xin_chinese_map_names_1::/chinese_map_names/facilities.lua"] = {},
}
function ug_require(name) return assert(modules[name], name) end
function registerQueue(value) modules["xin_chinese_map_names_1::/chinese_map_names/queue.lua"] = value end
log = {message = function() end, warning = function() end}
function setup(count, withDependencies)
  townCount, factoryCount = withDependencies and 8 or 0, withDependencies and 64 or 0
  local entries = {}
  for entity = 1, count do
    local entry = {entity = entity, before = "Old " .. entity, after = "新名称" .. entity,
      attempts = 0, priority = entity <= townCount and 1 or entity <= townCount + factoryCount and 2 or 4,
      order = entity, dependencies = {}}
    if entity > townCount and entity <= townCount + factoryCount then
      entry.nativeTown = (entity - 1) % townCount + 1
      entry.nativeTownName = "新名称" .. entry.nativeTown
      entry.dependencies = {entry.nativeTown}
    end
    entries[entity] = entry
    world[entity] = {name = entry.before}
  end
  state.value = {started = true, prepareRevision = 8, queueRevision = 8, prepareAttempts = 1,
    cursor = 1, renamed = 0, failed = 0, skipped = 0, retained = 0, entries = entries}
end
function run()
  local started = os.clock()
  while not state.value.done do
    metrics.updates = metrics.updates + 1
    assert(metrics.updates < 10000, "Queue did not finish")
    events.update({}, state)
    for _, command in ipairs(pending) do world[command.entity].name = command.name end
    pending = {}
  end
  metrics.seconds = os.clock() - started
  metrics.renamed, metrics.failed, metrics.skipped = state.value.renamed, state.value.failed, state.value.skipped
  return metrics
end
'''


def source_at(baseline):
    result = {}
    for name in FILES:
        path = MOD / "content/chinese_map_names" / name
        result[name] = subprocess.check_output(
            ["git", "show", f"{baseline}:{path.relative_to(ROOT).as_posix()}"], cwd=ROOT, text=True
        ) if baseline else path.read_text(encoding="utf-8")
    return result


def sample(sources, size, dependent, profile=None):
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(HARNESS)
    lua.globals().registerQueue(lua.execute(sources["queue.lua"], name="@queue.lua"))
    lua.execute(sources["events.script.lua"], name="@events.script.lua")
    lua.execute("events = data()")
    lua.globals().setup(size, dependent)
    if profile == "visits":
        lua.execute('''
          queueLineVisits = 0
          local nativeIpairs = ipairs
          ipairs = function(value)
            local iterator, source, index = nativeIpairs(value)
            if type(value[1]) ~= "table" or value[1].entity == nil then return iterator, source, index end
            return function(source, index)
              local nextIndex, entry = iterator(source, index)
              if nextIndex then queueLineVisits = queueLineVisits + 1 end
              return nextIndex, entry
            end, source, index
          end
        ''')
    elif profile == "instructions":
        lua.execute('''
          instructionBlocks = 0
          debug.sethook(function() instructionBlocks = instructionBlocks + 1 end, "", 1000)
        ''')
    metrics = dict(lua.globals().run().items())
    if profile == "instructions":
        lua.execute("debug.sethook()")
        metrics["lua_instructions_approx"] = lua.globals().instructionBlocks * 1000
    elif profile == "visits":
        metrics["entries_ipairs_visits"] = lua.globals().queueLineVisits
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="3bb40cc")
    parser.add_argument("--sizes", type=int, nargs="+", default=[2048, 8192])
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    sources = {"baseline": source_at(args.baseline), "working": source_at(None)}
    results = []
    for size in args.sizes:
        for dependent in (False, True):
            case = {"entries": size, "scenario": "town_factory_residents" if dependent else "independent_residents"}
            for label, source in sources.items():
                samples = [sample(source, size, dependent) for _ in range(args.repeats)]
                profile = sample(source, size, dependent, profile="instructions")
                profile["entries_ipairs_visits"] = sample(source, size, dependent, profile="visits")["entries_ipairs_visits"]
                profile["seconds_median"] = statistics.median(item["seconds"] for item in samples)
                profile.pop("seconds")
                case[label] = profile
            before, after = case["baseline"], case["working"]
            for key in ("commands", "commandTrace", "reads", "updates", "renamed", "failed", "skipped"):
                assert before[key] == after[key], (case, key)
            case["time_reduction_percent"] = 100 * (1 - after["seconds_median"] / before["seconds_median"])
            results.append(case)
            print(json.dumps(case, ensure_ascii=False), flush=True)
    return results


if __name__ == "__main__":
    main()
