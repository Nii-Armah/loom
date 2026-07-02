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
        self.assertIsNone(self.db.get('ghost'))


class TestLoomStage2(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path('./test_loom_db_stage2')
        self.test_dir.mkdir(exist_ok=True)
        self.db = LoomCore(data_dir=self.test_dir)
        self.db.boot()

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_delete_and_get(self):
        self.db.set('temp_key', 'secret_value')
        self.assertEqual(self.db.get('temp_key'), 'secret_value')

        self.db.delete('temp_key')
        self.assertIsNone(self.db.get('temp_key'))

    def test_delete_crash_recovery(self):
        self.db.set('persist_key', 'stay')
        self.db.set('delete_key', 'go')
        self.db.delete('delete_key')

        fresh_db = LoomCore(data_dir=self.test_dir)
        fresh_db.boot()

        self.assertEqual(fresh_db.get('persist_key'), 'stay')
        self.assertIsNone(fresh_db.get('delete_key'))

    def test_log_compaction(self):
        self.db.set('config', 'v1')
        self.db.set('config', 'v2')
        self.db.set('config', 'v3')
        self.db.set('trash', 'wasted_bytes')
        self.db.delete('trash')

        initial_size = self.db._db_file.stat().st_size

        self.db.compact()

        post_compact_size = self.db._db_file.stat().st_size

        self.assertLess(post_compact_size, initial_size)
        self.assertEqual(self.db.get('config'), 'v3')
        self.assertIsNone(self.db.get('trash'))

        fresh_db = LoomCore(data_dir=self.test_dir)
        fresh_db.boot()
        self.assertEqual(fresh_db.get('config'), 'v3')
        self.assertIsNone(fresh_db.get('trash'))


if __name__ == '__main__':
    unittest.main()