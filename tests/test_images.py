import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from seo_blog_workflow.images import create_image, cover_prompt


class ImageTests(unittest.TestCase):
    def test_cover_is_not_locked_to_travel(self):
        prompt = cover_prompt({"title":"Appointment booking", "image_prompt":"Calendar and appointment slots"}, {"art_direction":"Minimal flat illustration"})
        self.assertIn("Calendar and appointment slots", prompt)
        self.assertIn("Minimal flat illustration", prompt)
        self.assertNotIn("Shanghai", prompt)
        self.assertNotIn("aircraft", prompt)
    @patch("seo_blog_workflow.images.ModelAPI")
    def test_aisa_request_and_decode(self, api):
        api.return_value.request.return_value = {"data": [{"b64_json": base64.b64encode(b"\x89PNG\r\n\x1a\nmock").decode()}]}
        with tempfile.TemporaryDirectory() as folder:
            path = create_image({"provider":"aisa", "mode":"api", "model":"gpt-image-2", "size":"1536x864"}, {"title":"Journey"}, folder)
            self.assertTrue(path.exists())
            payload = api.return_value.request.call_args.args[1]
            self.assertNotIn("response_format", payload)
            self.assertEqual(payload["n"], 1)

    @patch("seo_blog_workflow.images.ModelAPI")
    def test_url_response_fails_without_downloading(self, api):
        api.return_value.request.return_value = {"data": [{"url":"https://example.com/image"}]}
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                create_image({"provider":"aisa", "mode":"api", "model":"gpt-image-2"}, {"title":"Journey"}, folder)
            self.assertFalse((Path(folder)/"cover.png").exists())
