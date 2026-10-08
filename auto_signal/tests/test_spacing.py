"""Exercise the Lua planner with concrete layouts and an independent count oracle."""

from pathlib import Path
import random
import unittest

from lupa.lua52 import LuaRuntime


ROOT = Path(__file__).resolve().parents[1]


class SpacingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        cls.planner = cls.lua.execute(
            (ROOT / "content/auto_signal/spacing.lua").read_text()
        )["plan"]

    def plan(self, intervals, minimum, maximum=None, layout=None):
        argument = self.lua.table_from(
            [self.lua.table_from(interval) for interval in intervals]
        )
        lua_layout = self.lua.table_from(layout) if layout is not None else None
        result = self.planner(argument, minimum, maximum, lua_layout)
        return [result[index] for index in range(1, len(result) + 1)]

    def assert_valid(self, points, intervals, minimum):
        for point in points:
            self.assertTrue(
                any(start - 1e-9 <= point <= end + 1e-9
                    for start, end in intervals),
                f"Position {point} lies outside {intervals}",
            )
        for left, right in zip(points, points[1:]):
            self.assertGreaterEqual(right - left + 1e-9, minimum)

    def test_1050_metres_uses_350_metre_gaps(self):
        self.assertEqual(self.plan([(0, 1050)], 300), [0, 350, 700, 1050])

    def test_exact_multiple_uses_minimum_spacing(self):
        self.assertEqual(self.plan([(0, 900)], 300), [0, 300, 600, 900])

    def test_short_section_places_one_signal_in_middle(self):
        self.assertEqual(self.plan([(20, 100)], 300), [60])
        self.assertEqual(self.plan([(42, 42)], 300), [42])

    def test_single_signal_uses_nearest_available_position(self):
        self.assertEqual(self.plan([(0, 10), (80, 100)], 300), [80])
        self.assertEqual(self.plan([(0, 10), (90, 100)], 300), [10])
        intervals = [(0, 10), (80, 100)]
        self.assertEqual(self.plan(intervals, 300, layout={"phase": 0}), [0])
        self.assertEqual(self.plan(intervals, 300, layout={"phase": 0.25}), [10])
        self.assertEqual(self.plan(intervals, 300, layout={"phase": 1}), [100])

    def test_empty_section(self):
        self.assertEqual(self.plan([], 300), [])

    def test_track_joints_shift_positions_without_reducing_count(self):
        intervals = [(0, 349.5), (350.5, 699.5), (700.5, 1050)]
        points = self.plan(intervals, 300)
        self.assertEqual(points, [0, 349.5, 699.5, 1050])
        self.assert_valid(points, intervals, 300)

    def test_narrow_allowed_intervals(self):
        intervals = [(0, 0), (1, 1), (300, 300), (301, 301), (600, 600)]
        self.assertEqual(self.plan(intervals, 300), [0, 300, 600])

    def test_quantity_limit_still_covers_whole_section(self):
        self.assertEqual(self.plan([(0, 1050)], 300, 3), [0, 525, 1050])
        self.assertEqual(self.plan([(0, 1050)], 300, 2), [0, 1050])
        self.assertEqual(self.plan([(0, 1050)], 300, 1), [525])

    def test_default_quantity_limit(self):
        points = self.plan([(0, 2000000)], 50)
        self.assertEqual(len(points), 1000)
        self.assertEqual((points[0], points[-1]), (0, 2000000))
        self.assert_valid(points, [(0, 2000000)], 50)

    def test_compact_layout_leaves_room_at_both_ends(self):
        self.assertEqual(
            self.plan([(0, 1050)], 300, layout={"spread": 0, "phase": 0.5}),
            [75, 375, 675, 975],
        )
        self.assertEqual(
            self.plan([(0, 1050)], 300, layout={"spread": 0.5, "phase": 0.5}),
            [37.5, 362.5, 687.5, 1012.5],
        )

    def test_alternative_layouts_keep_count_and_minimum_across_unavailable_ranges(self):
        intervals = [(10, 390), (420, 785), (810, 1570)]
        minimum = 226
        default = self.plan(intervals, minimum)
        self.assertEqual(len(default), 7)
        self.assertEqual(
            self.plan(intervals, minimum, layout={"spread": 1, "phase": 0.5}),
            default,
        )
        alternatives = []
        for spread, phase in [(0, 0.5), (0.5, 0.5), (0, 0.25), (0, 0.75), (0, 0), (0, 1)]:
            with self.subTest(spread=spread, phase=phase):
                options = {"spread": spread, "phase": phase}
                points = self.plan(intervals, minimum, layout=options)
                self.assertEqual(len(points), 7)
                self.assert_valid(points, intervals, minimum)
                self.assertEqual(points, self.plan(intervals, minimum, layout=options))
                alternatives.append(points)
        self.assertTrue(any(points != default for points in alternatives))

    def test_reduced_count_can_reposition_signals_at_the_same_minimum(self):
        points = self.plan([(0, 1050)], 300, 3, {"spread": 0, "phase": 0.5})
        self.assertEqual(points, [225, 525, 825])
        self.assert_valid(points, [(0, 1050)], 300)

    def test_fractional_track_endpoints(self):
        for tenths in range(10):
            first = tenths / 10
            for minimum in [50, 100, 300, 2000]:
                for count in [2, 3, 4, 10, 100]:
                    last = first + (count - 1) * minimum
                    with self.subTest(first=first, minimum=minimum, count=count):
                        intervals = [(first, last)]
                        points = self.plan(intervals, minimum)
                        self.assertEqual(len(points), count)
                        self.assert_valid(points, intervals, minimum)
                        self.assertAlmostEqual(points[0], first)
                        self.assertAlmostEqual(points[-1], last)

    @staticmethod
    def optimal_integer_count(intervals, minimum):
        # With integer boundaries and spacing, any feasible layout can move
        # left to integer positions. Dynamic programming over those positions
        # gives an independent maximum-cardinality oracle for these cases.
        first, last = intervals[0][0], intervals[-1][1]
        allowed = {
            position
            for start, end in intervals
            for position in range(start, end + 1)
        }
        best = {}
        for position in range(first, last + 1):
            count = best.get(position - 1, 0)
            if position in allowed:
                count = max(count, 1 + best.get(position - minimum, 0))
            best[position] = count
        return best[last]

    def test_seeded_layouts_have_maximum_feasible_count(self):
        randomizer = random.Random(48271)
        for case in range(250):
            intervals = []
            cursor = randomizer.randint(0, 100)
            for _ in range(randomizer.randint(1, 12)):
                end = cursor + randomizer.randint(0, 50)
                intervals.append((cursor, end))
                cursor = end + randomizer.randint(1, 70)
            minimum = randomizer.randint(1, 150)
            maximum = randomizer.randint(1, 30)
            with self.subTest(case=case, intervals=intervals, minimum=minimum):
                points = self.plan(intervals, minimum, maximum)
                self.assert_valid(points, intervals, minimum)
                self.assertEqual(
                    len(points),
                    min(maximum, self.optimal_integer_count(intervals, minimum)),
                )
                self.assertEqual(points, self.plan(intervals, minimum, maximum))
                if len(points) > 1:
                    self.assertAlmostEqual(points[0], intervals[0][0])
                    self.assertAlmostEqual(points[-1], intervals[-1][1])


if __name__ == "__main__":
    unittest.main()
