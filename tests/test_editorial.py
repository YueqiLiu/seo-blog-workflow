import unittest
from seo_blog_workflow.editorial import audit, writing_prompt, repair_article


class EditorialTests(unittest.TestCase):
    def test_repair_bound(self):
        class BadAPI:
            calls = 0
            def structured(self, prompt):
                self.calls += 1
                return {"title": "Draft", "description": "short", "body": "Missing structure"}
        api = BadAPI()
        article, issues = repair_article(api, {"title": "Draft", "body": "Text"},
            {"website": "https://example.com"}, {}, "en", 2)
        self.assertEqual(api.calls, 2)
        self.assertTrue(issues)

    def test_detects_missing_structure(self):
        issues = audit({"title": "Short", "description": "tiny", "body": "## Intro\nNo link"}, "https://example.com")
        self.assertIn("Require exactly one H1", issues)
        self.assertIn("Missing FAQ section", issues)
        self.assertIn("Missing product website link", issues)

    def test_prompt_separates_internal_profile(self):
        prompt = writing_prompt({"website": "https://example.com"}, {"keyword": "train trip"}, "en")
        self.assertIn("INTERNAL", prompt)
        self.assertIn("transport modes", prompt)
