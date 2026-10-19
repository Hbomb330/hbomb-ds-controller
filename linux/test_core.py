import tempfile
import unittest
from pathlib import Path
from controller_hub import deadzone, load_profiles, save_profiles

class CoreTests(unittest.TestCase):
    def test_center_drift_removed(self):
        self.assertEqual(deadzone(.03, -.04, .12), (0, 0))
    def test_range_and_direction(self):
        x, y = deadzone(1, 1, .12)
        self.assertAlmostEqual(x*x+y*y, 1)
        self.assertAlmostEqual(x, y)
        self.assertEqual(deadzone(-1, 0, .12), (-1, 0))
    def test_profile_roundtrip_and_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'profiles.json'
            profile = {'test-guid': {'name':'Test controller', 'deadzone':.14}}
            save_profiles(profile, path)
            self.assertEqual(load_profiles(path), (profile, ''))
            path.write_text('{corrupt')
            data, error = load_profiles(path)
            self.assertEqual(data, {})
            self.assertTrue(error)
            path.write_text('{"bad":{"deadzone":1}}')
            self.assertTrue(load_profiles(path)[1])

if __name__ == '__main__':
    unittest.main()
