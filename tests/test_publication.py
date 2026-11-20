import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from seo_blog_workflow.publication import initialize, reserve, record_delivery, confirm_publication, release_failed


class PublicationTests(unittest.TestCase):
    def test_quota_duplicate_and_receipt(self):
        db = sqlite3.connect(':memory:')
        initialize(db)
        self.assertTrue(reserve(db,'a',1,'Asia/Shanghai')[0])
        self.assertFalse(reserve(db,'a',1,'Asia/Shanghai')[0])
        self.assertFalse(reserve(db,'b',1,'Asia/Shanghai')[0])
        record_delivery(db,'a','commit-sha')
        with self.assertRaises(ValueError):
            confirm_publication(db,'a',False)
        self.assertEqual(db.execute('SELECT status FROM publications').fetchone()[0],'delivered')
        confirm_publication(db,'a',True)
        self.assertEqual(db.execute('SELECT status FROM publications').fetchone()[0],'published')

    def test_shared_database_reservations(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder)/'quota.sqlite3')
            first, second = sqlite3.connect(path), sqlite3.connect(path)
            initialize(first)
            self.assertTrue(reserve(first,'one',1,'UTC')[0])
            self.assertFalse(reserve(second,'two',1,'UTC')[0])
            with self.assertRaises(ValueError):
                release_failed(first,'one',False)
            release_failed(first,'one',True)
            self.assertTrue(reserve(second,'two',1,'UTC')[0])
            first.close()
            second.close()

    def test_local_day_rollover(self):
        db = sqlite3.connect(':memory:')
        initialize(db)
        before = datetime(2026,11,18,15,59,tzinfo=timezone.utc)
        after = datetime(2026,11,18,16,1,tzinfo=timezone.utc)
        self.assertTrue(reserve(db,'one',1,'Asia/Shanghai',before)[0])
        self.assertTrue(reserve(db,'two',1,'Asia/Shanghai',after)[0])
        self.assertFalse(reserve(db,'one',1,'Asia/Shanghai',after)[0])
