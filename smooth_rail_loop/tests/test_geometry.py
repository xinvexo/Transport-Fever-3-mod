"""Check the actual prefab Hermite curves against native rail limits."""
from pathlib import Path
import unittest

from lupa.lua52 import LuaRuntime
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def samples(segment, count=1001):
    p0, p1, t0, t1 = [np.array(list(segment[k].values())) for k in ("p0", "p1", "t0", "t1")]
    u = np.linspace(0, 1, count)[:, None]
    p = (2*u**3-3*u*u+1)*p0 + (u**3-2*u*u+u)*t0 + (-2*u**3+3*u*u)*p1 + (u**3-u*u)*t1
    t = (6*u*u-6*u)*p0 + (3*u*u-4*u+1)*t0 + (-6*u*u+6*u)*p1 + (3*u*u-2*u)*t1
    dd = (12*u-6)*p0 + (6*u-4)*t0 + (-12*u+6)*p1 + (6*u-2)*t1
    speed = np.linalg.norm(t[:, :2], axis=1)
    radius = speed**3 / np.maximum(abs(t[:, 0]*dd[:, 1]-t[:, 1]*dd[:, 0]), 1e-14)
    grade = abs(t[:, 2]) / speed
    return p, t, radius, grade


class PrefabGeometryTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.geometry = self.lua.execute((ROOT / "content/rail_loop/prefab_geometry.lua").read_text(encoding="utf-8"))

    def test_native_curvature_grade_continuity_and_ground_connections(self):
        for kind, elevation in (("raised", 16), ("lowered", -12)):
            with self.subTest(kind=kind):
                segments, info = self.geometry.generate(kind)
                previous = None
                all_points = []
                for segment in segments.values():
                    p, t, radius, grade = samples(segment)
                    self.assertTrue(np.isfinite(p).all() and np.isfinite(t).all())
                    self.assertGreaterEqual(float(radius.min()), 55)
                    self.assertLessEqual(float(grade.max()), 0.085)
                    self.assertGreater(float(np.linalg.norm(p[-1]-p[0])), 1)
                    if previous is not None:
                        np.testing.assert_allclose(previous[0], p[0], atol=1e-8)
                        np.testing.assert_allclose(previous[1], t[0]/np.linalg.norm(t[0]), atol=1e-8)
                    previous = p[-1], t[-1]/np.linalg.norm(t[-1])
                    all_points.append(p)
                all_points = np.concatenate(all_points)
                np.testing.assert_allclose(all_points[0], [-2.5, 0, 0], atol=1e-8)
                np.testing.assert_allclose(all_points[-1], [2.5, 0, 0], atol=1e-8)
                first = np.array(list(segments[1].t0.values()))
                last = np.array(list(segments[len(segments)].t1.values()))
                np.testing.assert_allclose(first/np.linalg.norm(first), [0, 1, 0], atol=1e-8)
                np.testing.assert_allclose(last/np.linalg.norm(last), [0, -1, 0], atol=1e-8)
                self.assertAlmostEqual(float(all_points[:, 2].max() if elevation > 0 else all_points[:, 2].min()), elevation)
                self.assertLessEqual(float(np.ptp(all_points[:, 0])), 141)
                self.assertLessEqual(float(np.ptp(all_points[:, 1])), 186)
                self.assertLessEqual(info.depth, 211)
                self.assertEqual(info.spacing, 5)
                self.assertEqual(info.elevation, elevation)

    def test_level_turnouts_and_clearance_for_a_future_center_mainline(self):
        for kind in ("raised", "lowered"):
            segments, info = self.geometry.generate(kind)
            crossings = {-2.5: [], 2.5: []}
            for segment in segments.values():
                points, _, _, _ = samples(segment)
                beginning_of_grade = (abs(points[:, 2]) > .001) & (abs(points[:, 2]) < 1)
                if beginning_of_grade.any():
                    self.assertGreater(float(np.min(abs(points[beginning_of_grade, 0]) - 2.5)), 6)
                for x in crossings:
                    indices = np.where((points[:-1, 0] - x) * (points[1:, 0] - x) < 0)[0]
                    for index in indices:
                        a, b = points[index:index + 2]
                        fraction = (x - a[0]) / (b[0] - a[0])
                        p = a + fraction * (b - a)
                        if p[1] > 1:
                            crossings[x].append(p)
                            self.assertEqual(segment.kind, 'BRIDGE' if kind == 'raised' else 'TUNNEL')
            for points in crossings.values():
                self.assertEqual(len(points), 1)
                self.assertAlmostEqual(points[0][2], info.elevation, delta=.02)
            self.assertEqual(info.mainlineStart, -25)
            self.assertEqual(info.mainlineEnd, 25)
            self.assertGreater(info.loopDepth - info.mainlineEnd, 160)

    def test_structure_regions_have_correct_height_and_only_one_kind(self):
        for kind, structure in (("raised", "BRIDGE"), ("lowered", "TUNNEL")):
            with self.subTest(kind=kind):
                segments, _ = self.geometry.generate(kind)
                self.assertEqual(segments[1].kind, "NORMAL")
                self.assertEqual(segments[len(segments)].kind, "NORMAL")
                self.assertEqual({s.kind for s in segments.values()}, {"NORMAL", structure})
                for s in segments.values():
                    p, _, _, _ = samples(s, 33)
                    if s.kind == "BRIDGE":
                        self.assertGreaterEqual(float(p[:, 2].min()), 5-1e-7)
                    elif s.kind == "TUNNEL":
                        self.assertLessEqual(float(p[:, 2].max()), -10+1e-7)

    def test_no_planar_self_crossings(self):
        for kind in ("raised", "lowered"):
            with self.subTest(kind=kind):
                segments, _ = self.geometry.generate(kind)
                points = np.concatenate([samples(s, 9)[0][:-1, :2] for s in segments.values()])
                points = np.vstack([points, list(segments[len(segments)].p1.values())[:2]])
                def orient(a, b, c):
                    return (b[0]-a[0])*(c[:, 1]-a[1])-(b[1]-a[1])*(c[:, 0]-a[0])
                for i in range(len(points)-3):
                    a, b = points[i:i+2]
                    c, d = points[i+2:-1], points[i+3:]
                    first = orient(a, b, c) * orient(a, b, d)
                    second = ((d[:, 0]-c[:, 0])*(a[1]-c[:, 1])-(d[:, 1]-c[:, 1])*(a[0]-c[:, 0]))
                    second *= ((d[:, 0]-c[:, 0])*(b[1]-c[:, 1])-(d[:, 1]-c[:, 1])*(b[0]-c[:, 0]))
                    self.assertFalse(np.any((first < -1e-7) & (second < -1e-7)))


if __name__ == "__main__":
    unittest.main()
