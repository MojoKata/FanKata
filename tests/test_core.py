import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fankata_core import config as cfgmod
from fankata_core import curve
from fankata_core import expr


class CurveTests(unittest.TestCase):
    PTS = [[20, 25], [40, 30], [60, 45], [75, 75], [85, 100]]

    def test_passes_through_points(self):
        f = curve.Interpolator(self.PTS)
        for x, y in self.PTS:
            self.assertAlmostEqual(f(x), y, places=9)

    def test_monotone_and_no_overshoot(self):
        f = curve.Interpolator(self.PTS)
        prev = -1.0
        for i in range(0, 1001):
            y = f(i / 10)
            self.assertGreaterEqual(y + 1e-9, prev)
            self.assertLessEqual(y, 100.0)
            prev = y

    def test_flat_outside_range(self):
        f = curve.Interpolator(self.PTS)
        self.assertEqual(f(0), 25)
        self.assertEqual(f(99), 100)

    def test_flat_segment_stays_flat(self):
        f = curve.Interpolator([[20, 50], [40, 50], [60, 80]])
        for x in range(20, 41):
            self.assertAlmostEqual(f(x), 50)

    def test_two_points_linear(self):
        self.assertAlmostEqual(curve.evaluate([[0, 20], [100, 100]], 50), 60)

    def test_rules(self):
        self.assertEqual(curve.point_errors(self.PTS, False), [])
        errs = curve.point_errors([[20, 25], [40, 30], [55, 35], [70, 30]], False)
        self.assertEqual(errs, [(3, "Speed at 70 °C can’t be lower than 35 % (the speed at 55 °C).")])
        self.assertTrue(curve.point_errors([[20, 10], [40, 30]], False))
        self.assertEqual(curve.point_errors([[20, 10], [40, 30]], True), [])
        self.assertTrue(curve.point_errors([[20, 30], [20, 40]], True))
        self.assertTrue(curve.point_errors([[20, 30]], True))

    def test_add_point(self):
        self.assertIsNone(curve.add_point_reason(self.PTS, 30, 27, False))
        self.assertIn("at least 25", curve.add_point_reason(self.PTS, 30, 22, False))
        self.assertIn("at most 30", curve.add_point_reason(self.PTS, 30, 35, False))
        self.assertIn("already", curve.add_point_reason(self.PTS, 40, 30, False))
        self.assertIn("below 20", curve.add_point_reason([[30, 0], [50, 50]], 10, 5, False))
        self.assertIsNone(curve.add_point_reason([[30, 0], [50, 50]], 10, 0, True))
        self.assertEqual(curve.valid_band(self.PTS, 30, False), (25, 30))

    def test_raise_to_floor_keeps_order(self):
        pts = curve.raise_to_floor([[30, 0], [50, 10], [65, 30]])
        self.assertEqual(pts, [[30, 20], [50, 20], [65, 30]])
        self.assertEqual(curve.point_errors(pts, False), [])


class ExprTests(unittest.TestCase):
    def ev(self, src, **vals):
        vals = {k.replace("__", "."): v for k, v in vals.items()}
        return expr.evaluate(expr.parse(src), lambda n: vals[n])

    def test_example(self):
        self.assertAlmostEqual(self.ev("sys.cpu * .9 + sys.gpu / 10", sys__cpu=54.2, sys__gpu=48.0), 53.58)

    def test_precedence(self):
        self.assertEqual(self.ev("2 + 3 * 4 ^ 2"), 50)
        self.assertEqual(self.ev("2 ^ 3 ^ 2"), 512)          # right-associative
        self.assertEqual(self.ev("-2 ^ 2"), -4)
        self.assertEqual(self.ev("(2 + 3) * 4"), 20)
        self.assertEqual(self.ev("10 - 4 - 3"), 3)
        self.assertEqual(self.ev("2 ^ -1"), 0.5)

    def test_custom_names_are_bare(self):
        self.assertEqual(self.ev("loop * 2", loop=21), 42)

    def test_syntax_errors(self):
        for bad in ["", "1 +", "(1 + 2", "1 2", "sys.", "user.derp", "3 $ 4", "* 2"]:
            with self.assertRaises(expr.ExprError, msg=bad):
                expr.parse(bad)

    def test_unknown_with_suggestion(self):
        with self.assertRaises(expr.ExprError) as cm:
            expr.check("sys.cpu * .9 + sys.gppu / 10", {"sys.cpu", "sys.gpu"})
        self.assertEqual(cm.exception.suggestion, "sys.gpu")
        self.assertEqual(cm.exception.pos, 15)

    def test_division_by_zero(self):
        with self.assertRaises(expr.EvalError):
            self.ev("1 / (sys.a - sys.a)", sys__a=3)

    def test_cycles(self):
        self.assertEqual(expr.find_cycle({"a": ["b"], "b": ["a"]}), ["a", "b", "a"])
        self.assertIsNone(expr.find_cycle({"a": ["b"], "b": []}))

    def test_probeset(self):
        ps = expr.ProbeSet({"sys.coolant": 33.9, "sys.gone": None}, {"loop": "(sys.coolant - 25) * 2 + 25",
                                                                    "twice": "loop * 2", "bad": "sys.gone + 1"})
        self.assertAlmostEqual(ps.value("loop"), 42.8)
        self.assertAlmostEqual(ps.value("twice"), 85.6)
        v, err = ps.try_value("bad")
        self.assertIsNone(v)
        self.assertIn("can’t be read", err)

    def test_names(self):
        self.assertTrue(expr.is_valid_custom_name("derp_2"))
        for bad in ["2derp", "_derp", "de rp", "sys.cpu", ""]:
            self.assertFalse(expr.is_valid_custom_name(bad), bad)


class ConfigTests(unittest.TestCase):
    def sample(self):
        c = cfgmod.default_config()
        c.probes.append(cfgmod.ProbeDef("loop", '(sys.coolant - 25) * 2 + 25'))
        c.fans["nct6798:pwm2"] = cfgmod.FanSettings(name='CPU "Fan"', curve="Quiet", probe="sys.cpu")
        return c

    def test_round_trip(self):
        c = self.sample()
        self.assertEqual(cfgmod.loads(cfgmod.dumps(c)).to_dict(), c.to_dict())

    def test_validate(self):
        known = frozenset({"sys.cpu", "sys.coolant"})
        c = self.sample()
        self.assertEqual(cfgmod.validate(c, known), [])
        c.fans["x:pwm1"] = cfgmod.FanSettings(curve="Nope")
        c.probes.append(cfgmod.ProbeDef("a", "b + 1"))
        c.probes.append(cfgmod.ProbeDef("b", "a + 1"))
        c.curves.append(cfgmod.CurveDef("Quiet", [[0, 50], [10, 40]]))
        errs = "\n".join(cfgmod.validate(c, known))
        for needle in ["unknown curve “Nope”", "reference themselves", "used twice", "can’t be lower"]:
            self.assertIn(needle, errs)

    def test_users(self):
        c = self.sample()
        c.probes.append(cfgmod.ProbeDef("twice", "loop * 2"))
        self.assertEqual(cfgmod.users_of_curve(c, "Quiet"), ["nct6798:pwm2"])
        self.assertEqual(cfgmod.users_of_probe(c, "loop"), ["probe twice"])


if __name__ == "__main__":
    unittest.main()
