"""Optional interface integration checks; skipped without dashboard packages."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None

import storage

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(AppTest is None, 'Install requirements.txt to test the interface')
class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        original = storage.connect
        self.redirect = patch('storage.connect', lambda path: original(Path(self.folder.name)/'test.db'))
        self.redirect.start()
        self.app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=30).run()

    def tearDown(self):
        self.redirect.stop()
        self.folder.cleanup()

    def widget(self, kind, label):
        return next(w for w in getattr(self.app, kind) if w.label == label)

    def assert_healthy(self):
        self.assertEqual(len(self.app.exception), 0, [e.message for e in self.app.exception])

    def test_initial_dashboard(self):
        self.assert_healthy()
        self.assertEqual(self.app.title[0].value, 'ThermoGuard')
        self.assertEqual(self.app.metric[0].value, '30.0 °C')

    def test_long_experiment_and_replay(self):
        self.widget('slider', 'Duration (seconds)').set_value(3600)
        self.widget('button', 'Apply and simulate').click().run()
        self.widget('slider', 'Replay time (seconds)').set_value(3600).run()
        self.assert_healthy()
        self.assertEqual(self.app.session_state.cfg.duration_s, 3600)

    def test_alert_and_local_save(self):
        self.widget('selectbox', 'Cooling strategy').select('No cooling').run()
        self.widget('slider', 'Replay time (seconds)').set_value(1200).run()
        self.assert_healthy()
        self.assertTrue(any('Temperature alert' in e.value for e in self.app.error))
        self.widget('button', 'Save this experiment locally').click().run()
        self.assert_healthy()
        self.assertTrue(any('Saved experiment #' in e.value for e in self.app.success))


if __name__ == '__main__':
    unittest.main()
