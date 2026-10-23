import math
from pathlib import Path
import tempfile
import unittest

from thermal import Config, STRATEGIES, command_flow, compare, neighbours, simulate, summarize
from storage import list_experiments, records_csv, save_experiment


class ThermalTests(unittest.TestCase):
    def test_zero_current_equilibrium(self):
        cfg = Config(duration_s=60, current_a=0, ambient_c=25, inlet_c=25, initial_c=25)
        for strategy in STRATEGIES:
            rows = simulate(cfg, strategy)
            self.assertTrue(all(r['max_c'] == 25 and r['min_c'] == 25 for r in rows))

    def test_energy_balance_one_step_without_cooling(self):
        cfg = Config(duration_s=60)
        r = simulate(cfg, 'No cooling')[1]
        expected = sum(cfg.current_a**2 * (0.018*(1+0.025*i)) for i in range(10))
        stored = sum((r[f'cell_{i+1}_c'] - cfg.initial_c) * 70 for i in range(10))
        self.assertAlmostEqual(stored, expected, places=8)

    def test_internal_coupling_is_symmetric(self):
        for i in range(10):
            for j in neighbours(i):
                self.assertIn(i, neighbours(j))

    def test_cooling_reduces_temperature(self):
        cfg = Config()
        results = compare(cfg)
        self.assertLess(results['Fixed flow']['summary']['peak_c'], results['No cooling']['summary']['peak_c'])

    def test_fixed_pump_energy_integral(self):
        cfg = Config(duration_s=600, max_flow_lpm=1.5)
        rows = simulate(cfg, 'Fixed flow')
        self.assertAlmostEqual(rows[-1]['pump_wh'], 2*1.5**3*600/3600)
        self.assertEqual(summarize(rows,cfg)['seconds_above_limit'], 0)

    def test_fault_reduces_flow_not_command(self):
        cfg = Config(duration_s=120, blockage=0.8, fault_at_s=60)
        rows = simulate(cfg, 'Fixed flow')
        self.assertAlmostEqual(rows[60]['actual_lpm'], 1.0)
        self.assertAlmostEqual(rows[61]['actual_lpm'], 0.2)
        self.assertEqual(rows[61]['command_lpm'], 1.0)
        healthy = simulate(Config(duration_s=120), 'Fixed flow')
        self.assertGreater(rows[-1]['max_c'], healthy[-1]['max_c'])

    def test_hysteresis(self):
        cfg = Config()
        self.assertEqual(command_flow('Thermostatic', 38, False, cfg), (1.0, True))
        self.assertEqual(command_flow('Thermostatic', 36, True, cfg), (1.0, True))
        self.assertEqual(command_flow('Thermostatic', 35, True, cfg), (0.0, False))

    def test_controller_limits(self):
        cfg = Config(max_flow_lpm=0.5)
        self.assertEqual(command_flow('Adaptive proportional', 20, False, cfg)[0], 0)
        self.assertEqual(command_flow('Adaptive proportional', 80, False, cfg)[0], 0.5)

    def test_invalid_inputs(self):
        for settings in [{'current_a':float('nan')}, {'blockage':1}, {'max_flow_lpm':0},
                         {'duration_s':60.5}, {'profile':'invalid'}]:
            with self.assertRaises(ValueError):
                Config(**settings)

    def test_alert_duration_includes_every_interval(self):
        cfg = Config(duration_s=60, initial_c=50, warning_c=45, current_a=0)
        rows = simulate(cfg, 'No cooling')
        self.assertEqual(summarize(rows,cfg)['seconds_above_limit'], 60)

    def test_hot_inlet_can_heat_cells(self):
        cfg = Config(duration_s=60, initial_c=20, ambient_c=20, inlet_c=40, current_a=0)
        self.assertGreater(simulate(cfg,'Fixed flow')[-1]['max_c'], 20)
        tiny = Config(duration_s=60, initial_c=33.00000000000001,
                      ambient_c=33, inlet_c=25, current_a=0)
        rows = simulate(tiny, 'Adaptive proportional')
        self.assertTrue(all(25 <= r['min_c'] <= r['max_c'] <= tiny.initial_c for r in rows))

    def test_extreme_supported_scenario_finite(self):
        cfg = Config(duration_s=3600, current_a=25, ambient_c=45, inlet_c=40,
                     initial_c=50, max_flow_lpm=2, blockage=.95, fault_at_s=0)
        for strategy in STRATEGIES:
            rows = simulate(cfg, strategy)
            self.assertEqual(len(rows), 3601)
            self.assertTrue(all(math.isfinite(r['max_c']) for r in rows))

    def test_storage_and_csv(self):
        cfg = Config(duration_s=60)
        rows = simulate(cfg)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'experiments.db'
            identifier = save_experiment(path, cfg, 'Adaptive proportional', rows, summarize(rows,cfg))
            self.assertEqual(list_experiments(path)[0][0], identifier)
        self.assertEqual(len(records_csv(rows).splitlines()), 62)


if __name__ == '__main__':
    unittest.main()
