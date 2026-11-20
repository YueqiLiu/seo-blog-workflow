import copy
import json
import tempfile
import unittest
from pathlib import Path
from seo_blog_workflow.config import load_config
from seo_blog_workflow.runtime import connect, import_csv, run


class FakeAPI:
    def structured(self, prompt):
        if prompt.startswith("Assess"):
            return {"relevance_score": 90, "reason": "Useful product use case"}
        return {"title": "Booking guide", "description": "A practical guide to planning a useful appointment booking website for your business.", "body": "# Booking\n\n[Website](https://example.com)\n\n## Plan\nUseful steps.\n\n## Build\nUseful steps.\n\n## FAQ\n### Who is this for?\nBusinesses.\n### How to start?\nPlan.\n### What next?\nBuild."}


class RuntimeTests(unittest.TestCase):
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
