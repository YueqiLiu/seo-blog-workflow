import io
import json
import unittest
from http.client import IncompleteRead
from urllib.error import HTTPError
from unittest.mock import patch
from seo_blog_workflow.config import load_config
from seo_blog_workflow.runtime import ModelAPI, ModelAPIError


class AisaTests(unittest.TestCase):
    @patch.dict("os.environ", {"AISA_API_KEY": "test-only"})
    @patch("seo_blog_workflow.runtime.urlopen")
    def test_truncated_response_never_retries(self, opener):
        opener.return_value.__enter__.return_value.read.side_effect = IncompleteRead(b'{"data":', 100)
        with self.assertRaisesRegex(ModelAPIError, "provider_outcome_unknown"):
            ModelAPI({"provider":"aisa"}).request("/images/generations", {"model":"test"})
        self.assertEqual(opener.call_count, 1)

    @patch.dict("os.environ", {"AISA_API_KEY": "test-only"})
    @patch("seo_blog_workflow.runtime.urlopen")
    def test_complete_json_with_broken_http_terminator(self, opener):
        opener.return_value.__enter__.return_value.read.side_effect = IncompleteRead(b'{"data": []}', 2)
        self.assertEqual(ModelAPI({"provider":"aisa"}).request("/models"), {"data":[]})

    @patch.dict("os.environ", {"AISA_API_KEY": "test-only"})
    @patch("seo_blog_workflow.runtime.urlopen")
    def test_list_models_get(self, opener):
        opener.return_value.__enter__.return_value = io.StringIO('{"data":[{"id":"available-model"}]}')
        self.assertEqual(ModelAPI({"provider": "aisa"}).models(), ["available-model"])
        request = opener.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.full_url, "https://api.aisa.one/v1/models")

    @patch.dict("os.environ", {"AISA_API_KEY": "secret-not-for-logs"})
    @patch("seo_blog_workflow.runtime.urlopen")
    def test_safe_http_error(self, opener):
        opener.side_effect = HTTPError("https://api.aisa.one/v1/chat/completions", 403, "secret-not-for-logs", {}, None)
        with self.assertRaisesRegex(ModelAPIError, "HTTP 403: access_denied_or_gateway_policy"):
            ModelAPI({"provider": "aisa", "text_model": "test"}).text("test")

    @patch.dict("os.environ", {"AISA_API_KEY": "test-only"})
    @patch("seo_blog_workflow.runtime.urlopen")
    def test_chat_contract(self, opener):
        opener.return_value.__enter__.return_value = io.StringIO(json.dumps({"choices": [{"message": {"content": '{"relevance_score": 80}'}}]}))
        api = ModelAPI({"provider": "aisa", "text_model": "configured-model"})
        self.assertEqual(api.structured("Assess relevance"), {"relevance_score": 80})
        request = opener.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.aisa.one/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-only")
        payload = json.loads(request.data)
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["model"], "configured-model")

    def test_example(self):
        config = load_config("examples/config.aisa.json")
        self.assertEqual(config["models"]["api_key_env"], "AISA_API_KEY")

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_key(self):
        with self.assertRaises(ValueError):
            ModelAPI({"provider": "aisa", "text_model": "configured-model"}).text("test")
