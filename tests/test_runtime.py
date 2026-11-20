import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from seo_blog_workflow.config import load_config
from seo_blog_workflow.runtime import connect, import_csv, run


class FakeAPI:
    def structured(self, prompt):
        if prompt.startswith("Assess"):
            return {"relevance_score": 90, "reason": "Useful product use case"}
        return {"title": "Booking guide", "description": "A practical guide to planning a useful appointment booking website for your business.", "body": "# Booking\n\n[Website](https://example.com)\n\n## Plan\nUseful steps.\n\n## Build\nUseful steps.\n\n## FAQ\n### Who is this for?\nBusinesses.\n### How to start?\nPlan.\n### What next?\nBuild."}


class RuntimeTests(unittest.TestCase):
    def test_completed_drafts_do_not_starve_new_keywords(self):
        config = load_config('config.example.json')
        config['publication']['daily_target'] = 1
        with tempfile.TemporaryDirectory() as folder:
            config['publication']['output_directory'] = folder
            db = connect(':memory:')
            for keyword in ('first', 'second'):
                db.execute('INSERT INTO keywords(keyword,payload) VALUES (?,?)',
                           (keyword, json.dumps({'keyword': keyword, 'search_volume': 500, 'kd': 20})))
            db.commit()
            self.assertEqual(run(db, config, FakeAPI())['exported'], 1)
            second = run(db, config, FakeAPI())
            self.assertEqual((second['exported'], second['skipped_complete']), (1, 1))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM keywords WHERE status='draft'").fetchone()[0], 2)

    def test_missing_cover_is_restored_without_rewriting_article(self):
        config = load_config('config.example.json')
        with tempfile.TemporaryDirectory() as folder:
            config['publication']['output_directory'] = folder
            db = connect(':memory:')
            import_csv(db, 'examples/keywords.csv')
            run(db, config, FakeAPI())
            row = db.execute('SELECT * FROM keywords').fetchone()
            cover = Path(row['output_path']).parent / 'cover.svg'
            cover.unlink()
            class NoCalls:
                def structured(self, prompt):
                    raise AssertionError('Article and relevance must be reused')
            self.assertEqual(run(db, config, NoCalls())['exported'], 1)
            self.assertTrue(cover.is_file())

    def test_image_interruption_preserves_article_and_releases_generator_lock(self):
        config = load_config('config.example.json')
        with tempfile.TemporaryDirectory() as folder:
            config['publication']['output_directory'] = str(Path(folder) / 'output')
            path = str(Path(folder) / 'workflow.sqlite3')
            db = connect(path)
            import_csv(db, 'examples/keywords.csv')
            with patch('seo_blog_workflow.images.create_image', side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    run(db, config, FakeAPI())
            db.close()
            db = connect(path)
            self.assertIsNotNone(db.execute('SELECT article FROM keywords').fetchone()[0])
            class NoCalls:
                def structured(self, prompt):
                    raise AssertionError('Saved article must survive a process interruption')
            self.assertEqual(run(db, config, NoCalls())['exported'], 1)
            db.close()

    def test_second_generator_skips_while_first_persists_stages(self):
        config = load_config('config.example.json')
        with tempfile.TemporaryDirectory() as folder:
            config['publication']['output_directory'] = str(Path(folder) / 'output')
            path = str(Path(folder) / 'workflow.sqlite3')
            first, second = connect(path), connect(path)
            import_csv(first, 'examples/keywords.csv')
            nested = []
            class Concurrent(FakeAPI):
                def structured(self, prompt):
                    nested.append(run(second, config, FakeAPI()))
                    return super().structured(prompt)
            self.assertEqual(run(first, config, Concurrent())['exported'], 1)
            self.assertTrue(all(item['status'] == 'skipped_already_running' for item in nested))
            first.close()
            second.close()

    def test_unrepaired_draft_does_not_export_or_block_next(self):
        config = load_config("config.example.json")
        with tempfile.TemporaryDirectory() as folder:
            config["publication"]["output_directory"] = folder
            db = connect(":memory:")
            for keyword in ("bad", "good"):
                db.execute("INSERT INTO keywords(keyword,payload) VALUES (?,?)", (keyword, json.dumps({"keyword":keyword,"search_volume":500,"kd":20})))
            db.commit()
            class WeakAPI(FakeAPI):
                def structured(self, prompt):
                    if not prompt.startswith("Assess") and '"keyword": "bad"' in prompt:
                        return {"title":"Incomplete", "description":"short", "body":"Unusable"}
                    return super().structured(prompt)
            report = run(db, config, WeakAPI())
            self.assertEqual(report["needs_revision"], 1)
            self.assertEqual(report["exported"], 1)
            self.assertEqual(db.execute("SELECT status FROM keywords WHERE keyword='bad'").fetchone()[0], "needs_revision")

    def test_import_generate_resume(self):
        config = load_config("config.example.json")
        with tempfile.TemporaryDirectory() as folder:
            config["publication"]["output_directory"] = folder
            db = connect(":memory:")
            self.assertEqual(import_csv(db, "examples/keywords.csv"), 1)
            self.assertEqual(import_csv(db, "examples/keywords.csv"), 0)
            report = run(db, config, FakeAPI())
            self.assertEqual(report["exported"], 1)
            row = db.execute("SELECT * FROM keywords").fetchone()
            self.assertEqual(row["status"], "draft")
            self.assertIsNone(row["published_at"])
            self.assertTrue(Path(row["output_path"]).exists())
            class NoCalls:
                def structured(self, prompt):
                    raise AssertionError("Saved article must be reused")
            self.assertEqual(run(db, config, NoCalls())["failed"], 0)

    def test_failure_isolation(self):
        config = load_config("config.example.json")
        with tempfile.TemporaryDirectory() as folder:
            config["publication"]["output_directory"] = folder
            db = connect(":memory:")
            for keyword in ("bad", "good"):
                db.execute("INSERT INTO keywords(keyword,payload) VALUES (?,?)", (keyword, json.dumps({"keyword": keyword,"search_volume":500,"kd":20})))
            db.commit()
            class PartialAPI(FakeAPI):
                def structured(self, prompt):
                    if '"keyword": "bad"' in prompt:
                        raise RuntimeError("Provider failed")
                    return super().structured(prompt)
            report = run(db, config, PartialAPI())
            self.assertEqual((report["failed"], report["exported"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
