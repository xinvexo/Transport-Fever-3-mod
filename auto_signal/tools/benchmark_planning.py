"""Compare normal signal plans with a git revision using the same Lua 5.2 world.

Run from the repository with:
  python auto_signal/tools/benchmark_planning.py --baseline 3bb40cc

Counts describe executed Lua/native API calls in a simulated world. Timings are
script simulation measurements, not in-game frame times. No game files change.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import statistics
import subprocess
import time

from lupa.lua52 import lua_type


ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "auto_signal"
spec = importlib.util.spec_from_file_location("signal_test_world", MOD / "tests/test_network.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def source(name, revision):
    path = f"auto_signal/content/auto_signal/{name}.lua"
    if revision is None:
        return (ROOT / path).read_text(encoding="utf-8")
    return subprocess.check_output(
        ["git", "show", f"{revision}:{path}"], cwd=ROOT, text=True,
    )


def plain(value):
    if lua_type(value) != "table":
        return value
    return {key: plain(item) for key, item in value.items()}


def world_for(edge_count, curved, existing_stride):
    world = fixture.TrackWorld()
    for index in range(edge_count):
        edge = 100 + index
        world.add_edge(edge, index + 1, index + 2, 50)
        if curved:
            # Continuous S-bends with 50 m long base edges. Equal endpoint
            # tangents preserve connections; the same fixture feeds both builds.
            dy = 15 if index % 2 == 0 else -15
            y = 0 if index % 2 == 0 else 15
            world.set_geometry(edge, (index * 50, y, 0), ((index + 1) * 50, y + dy, 0),
                               tangent0=(50, 0, 0), tangent1=(50, 0, 0))
            # Calibrate the simulated native length from the actual cubic curve.
            points = [world.world_position(edge, i / 200) for i in range(201)]
            world.lengths[edge] = sum(
                sum((b - a) ** 2 for a, b in zip(first, second)) ** .5
                for first, second in zip(points, points[1:])
            )
            world.set_transport_edges(edge, 1)
    if existing_stride:
        for index in range(0, edge_count, existing_stride):
            world.add_signal(10000 + index, 100 + index, fraction=.5)
    world.add_signal(99999, 100 + edge_count // 2, fraction=.25)

    # Use Lua table lookups for every simulated world API so Python bridge and
    # the unit fixture's linear entity-existence scan do not dominate timings.
    lua, g = world.lua, world.lua.globals()
    g.worldComponents = lua.table()
    for (entity, kind), component in world.components.items():
        if g.worldComponents[entity] is None:
            g.worldComponents[entity] = lua.table()
        g.worldComponents[entity][kind] = component
    g.nodeTracks = world.table(dict(world.connections))
    g.nodeStreets = world.table(dict(world.street_connections))
    g.edgeOwners = world.table(world.owners)
    g.objectHosts = world.table(world.hosts)
    lua.execute("""
        api.engine.entityExists = function(entity) return worldComponents[entity] ~= nil end
        api.engine.getComponent = function(entity, kind)
            assert(worldComponents[entity], 'invalid entity')
            return worldComponents[entity][kind]
        end
        api.engine.system.streetSystem.getNodeTrackSegments = function(node) return nodeTracks[node] or {} end
        api.engine.system.streetSystem.getNodeStreetSegments = function(node) return nodeStreets[node] or {} end
        api.engine.system.streetSystem.getEdgeForEdgeObject = function(entity) return objectHosts[entity] or -1 end
        api.engine.system.streetConnectorSystem.getConstructionEntityForEdge = function(edge)
            return edgeOwners[edge] or -1
        end
        api.res.constructionRep.find = function() return 1 end
        api.res.constructionRep.get = function() return {edgeObject = {minDistToCrossing = 0}} end
    """)
    return world


def measure(sources, case, repeats):
    world = world_for(case["edges"], case["curved"], case["existing_stride"])
    lua, g = world.lua, world.lua.globals()
    geometry = lua.execute(sources["geometry"])
    spacing = lua.execute(sources["spacing"])
    g.geometryModule = geometry
    g.ug_require = lambda path: geometry if path.endswith("geometry.lua") else spacing
    network = lua.execute(sources["network"])
    g.networkModule = network
    g.sourceSide = world.source(99999)
    lua.execute("""
        metrics = {}
        local function counted(owner, key, counter)
            local original = owner[key]
            owner[key] = function(...)
                metrics[counter] = (metrics[counter] or 0) + 1
                return original(...)
            end
        end
        counted(api.engine.system.streetSystem, 'getNodeTrackSegments', 'track_queries')
        counted(api.engine.system.streetSystem, 'getNodeStreetSegments', 'street_queries')
        counted(api.engine, 'getComponent', 'component_reads')
        local observed = setmetatable({}, {__mode = 'k'})
        local function sampled(data)
            if data and not observed[data] then
                observed[data] = true
                metrics.curves = (metrics.curves or 0) + 1
                metrics.points = (metrics.points or 0) + #data.points
            end
        end
        if geometryModule.prepare then
            local prepare = geometryModule.prepare
            geometryModule.prepare = function(segments)
                local result = prepare(segments)
                for _, segment in ipairs(segments) do sampled(segment.geometry) end
                return result
            end
        end
        if geometryModule.forSegment then
            local forSegment = geometryModule.forSegment
            geometryModule.forSegment = function(segment)
                local result = forSegment(segment)
                sampled(result)
                return result
            end
        end
        function runPlan()
            local plan, reason = networkModule.plan(99999, 300, sourceSide)
            assert(plan, reason)
            return plan
        end
    """)
    plan = plain(g.runPlan())
    counts = plain(g.metrics)
    # Keep counting overhead identical for both versions. Each plan gets fresh
    # segment data; no curve or graph cache may survive into the next plan.
    timings = []
    for _ in range(repeats):
        lua.execute("collectgarbage('collect'); metrics = {}")
        start = time.perf_counter()
        actual = g.runPlan()
        timings.append((time.perf_counter() - start) * 1000)
        assert plain(actual) == plan, "plan changed between identical repeated calls"
    return plan, {**counts, "signals": plan["count"], "median_ms": round(statistics.median(timings), 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="3bb40cc")
    parser.add_argument("--repeats", type=int, default=7)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    sources = {
        label: {name: source(name, revision) for name in ("geometry", "spacing", "network")}
        for label, revision in (("baseline", args.baseline), ("current", None))
    }
    cases = [
        {"name": "straight_new_60_edges", "edges": 60, "curved": False, "existing_stride": 0},
        {"name": "curved_new_60_edges", "edges": 60, "curved": True, "existing_stride": 0},
        {"name": "curved_rebuild_60_edges", "edges": 60, "curved": True, "existing_stride": 6},
        {"name": "curved_dense_60_edges", "edges": 60, "curved": True, "existing_stride": 1},
        {"name": "curved_new_600_edges", "edges": 600, "curved": True, "existing_stride": 0},
    ]
    results = []
    for case in cases:
        before, baseline = measure(sources["baseline"], case, args.repeats)
        after, current = measure(sources["current"], case, args.repeats)
        assert before == after, f"layout differs in {case['name']}"
        results.append({**case, "identical_layout": True, "baseline": baseline, "current": current})
    print(json.dumps({"baseline_revision": args.baseline, "runtime": "lupa.lua52",
                      "timing_scope": "script simulation, not in-game timing", "cases": results}, indent=2))


if __name__ == "__main__":
    main()
