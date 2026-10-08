"""Angle/quadrant regression across Lua runtimes; generates no output files."""
import importlib
import math
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'content/rail_loop/dynamic_geometry.lua').read_text(encoding='utf-8')

def verify_runtimes():
    reports = []
    for module in ['lua52', 'lua51', 'luajit21', 'lua53', 'lua54', 'lua55']:
        try:
            runtime = importlib.import_module('lupa.' + module)
        except ModuleNotFoundError:
            if module == 'lua52':
                raise
            continue  # Lupa wheels need not bundle every optional runtime.
        rt = runtime.LuaRuntime(unpack_returned_tuples=True)
        geometry = rt.execute(source)
        def lua(value):
            if isinstance(value, dict):
                return rt.table_from({k: lua(v) for k, v in value.items()})
            if isinstance(value, list):
                return rt.table_from(value)
            return value
        count, largest_piece_turn, smallest_total_turn = 0, 0, math.inf
        baseline = None
        for degrees in range(0, 360, 45):
            angle = math.radians(degrees)
            def rotate(x, y):
                return [x * math.cos(angle) - y * math.sin(angle), x * math.sin(angle) + y * math.cos(angle), 0]
            for direction in [1, 2]:
                for stored_sign in [1, -1]:
                    ap, bp = rotate(0, 0), rotate(5, 0)
                    for p in [ap, bp]:
                        p[0] += 10000
                        p[1] -= 9000
                    at, bt = rotate(0, 1), rotate(0, stored_sign)
                    segments, info = geometry.generate(lua({'p': ap, 't': at}), lua({'p': bp, 't': bt}),
                                                       lua({'direction': direction, 'extension': 0, 'elevation': 0}))
                    start, end = segments[1], segments[len(segments)]
                    for axis in range(3):
                        assert abs(start.p0[axis + 1] - ap[axis]) < 1e-6
                        assert abs(end.p1[axis + 1] - bp[axis]) < 1e-6
                    sign = 1 if direction == 1 else -1
                    for tangent, expected_sign in [(start.t0, sign), (end.t1, -sign)]:
                        n = math.hypot(tangent[1], tangent[2])
                        assert sum(tangent[i + 1] / n * at[i] * expected_sign for i in [0, 1]) > .999999
                    if baseline is None:
                        baseline = info.length
                    assert abs(info.length - baseline) < 1e-6
                    assert info.minRadius >= 55 and info.maxGrade <= .04001
                    total_turn = 0
                    for segment in segments.values():
                        previous = None
                        piece_turn = 0
                        for i in range(9):
                            _, tangent, _ = geometry.hermite(segment.p0, segment.p1, segment.t0, segment.t1, i / 8)
                            heading = math.atan2(tangent[2], tangent[1])
                            if previous is not None:
                                piece_turn += abs((heading - previous + math.pi) % (2 * math.pi) - math.pi)
                            previous = heading
                        total_turn += piece_turn
                        largest_piece_turn = max(largest_piece_turn, piece_turn)
                    # A whole return loop turns >180 degrees, each emitted edge <90.
                    assert total_turn > math.pi
                    smallest_total_turn = min(smallest_total_turn, total_turn)
                    count += 1
        assert largest_piece_turn < math.pi / 2
        reports.append({'module': module, 'runtime': rt.eval('_VERSION'), 'cases': count,
                        'largestEdgeTurnDegrees': math.degrees(largest_piece_turn),
                        'smallestLoopTotalTurnDegrees': math.degrees(smallest_total_turn)})

    return reports


class RuntimeCompatibilityTests(unittest.TestCase):
    def test_rotated_translated_and_reversed_tangents_across_available_runtimes(self):
        reports = verify_runtimes()
        self.assertIn('lua52', [report['module'] for report in reports])
        self.assertEqual(sum(report['cases'] for report in reports), 32 * len(reports))
