import shutil
import unittest
from pathlib import Path
from loom import LoomCore


class TestLoomStage1(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path('./test_loom_db')
        self.test_dir.mkdir(exist_ok=True)
        self.db = LoomCore(data_dir=self.test_dir)
        self.db.boot()

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_write_and_read(self):
        self.db.set('user_123', '{"name": "Stanley"}')
        self.assertEqual(self.db.get('user_123'), '{"name": "Stanley"}')

    def test_overwrite_isolation(self):
        self.db.set('status', 'active')
        self.db.set('status', 'inactive')
        self.assertEqual(self.db.get('status'), 'inactive')

    def test_crash_recovery(self):
        self.db.set('session_1', 'token_a')
        self.db.set('session_2', 'token_b')
        self.db.set('session_1', 'token_c')

        fresh_db = LoomCore(data_dir=self.test_dir)
        fresh_db.boot()

        self.assertEqual(fresh_db.get('session_2'), 'token_b')
        self.assertEqual(fresh_db.get('session_1'), 'token_c')

    def test_missing_key(self):
        self.assertIsNone(self.db.get("ghost"))


if __name__ == '__main__':
    unittest.main()