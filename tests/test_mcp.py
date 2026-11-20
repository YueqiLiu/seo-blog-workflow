import asyncio
import importlib.util
import json
import os
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from seo_blog_workflow.mcp_client import TokenStore, server_settings
from seo_blog_workflow.mcp_sources import ProductHuntMCP, cached_call
from seo_blog_workflow.research import initialize, collect
from seo_blog_workflow.runtime import connect
from test_research import config


class MCPTests(unittest.TestCase):
    def test_token_store_atomic_owner_only_file(self):
        class Value:
            def model_dump(self, **kwargs):
                return {'access_token': 'private'}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tokens.json'
            store = TokenStore(path)
            store.write('tokens', Value())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(store.read()['tokens']['access_token'], 'private')
            os.chmod(path, 0o644)
            with self.assertRaises(ValueError):
                store.read()

    def test_server_url_rejects_embedded_credentials(self):
        with self.assertRaises(ValueError):
            server_settings({'mcp_servers': {'x': {'url': 'https://secret@example.com/mcp'}}}, 'x')

    def test_request_cache_and_explicit_failure_retry(self):
        cfg = {'mcp_servers': {'ph': {'url': 'https://mcp.producthunt.com/mcp'}}}
        with connect(':memory:') as db:
            initialize(db)
            with patch('seo_blog_workflow.mcp_sources.call') as call:
                call.return_value = {'status': 'ok', 'data': {'results': []}}
                first = cached_call(db, cfg, 'ph', 'search_products', {})
                self.assertEqual(first, cached_call(db, cfg, 'ph', 'search_products', {}))
                self.assertEqual(call.call_count, 1)
            with patch('seo_blog_workflow.mcp_sources.call', side_effect=ValueError) as call:
                for _ in range(2):
                    with self.assertRaises(ValueError):
                        cached_call(db, cfg, 'ph', 'search_products', {'query': 'other'})
                self.assertEqual(call.call_count, 1)

    def test_mcp_collection_preserves_product_links(self):
        cfg = config()
        cfg['sources'] = {'product_hunt': True}
        cfg['research']['product_hunt'] = {'transport': 'mcp', 'mcp_server': 'ph', 'topics': []}
        cfg['mcp_servers'] = {'ph': {'url': 'https://mcp.producthunt.com/mcp'}}
        cfg['selection']['missing_metrics'] = 'allow'
        class Model:
            def structured(self, prompt):
                return {'candidates': [{'keyword': 'booking app', 'post_id': 'booking'}]}
        result = {'status': 'ok', 'data': {'results': [
            {'slug': 'booking', 'name': 'Booking', 'url': 'https://www.producthunt.com/products/booking',
             'tagline': 'Manage appointments', 'website_url': 'https://example.com'}], 'has_more': False}}
        with connect(':memory:') as db:
            with patch('seo_blog_workflow.mcp_sources.call', return_value=result):
                report = collect(db, cfg, model=Model())
            self.assertEqual(report['queued'], 1)
            payload = json.loads(db.execute('SELECT payload FROM keywords').fetchone()[0])
            self.assertEqual(payload['source_url'], 'https://www.producthunt.com/products/booking')
            self.assertEqual(payload['product_url'], 'https://example.com')

    @unittest.skipUnless(importlib.util.find_spec('jsonschema'), 'MCP optional dependencies not installed')
    def test_call_rejects_write_tool_and_validates_input(self):
        from seo_blog_workflow.mcp_client import call
        cfg = {'mcp_servers': {'ph': {'url': 'https://mcp.producthunt.com/mcp', 'read_only_tools': ['search']}}}
        tool = SimpleNamespace(name='search', inputSchema={'type': 'object', 'required': ['query']},
                               annotations=SimpleNamespace(readOnlyHint=False))
        class Session:
            async def list_tools(self, cursor=None):
                return SimpleNamespace(tools=[tool], nextCursor=None)
            async def call_tool(self, name, arguments):
                raise AssertionError('must reject before execution')
        @asynccontextmanager
        async def session(*args, **kwargs):
            yield Session()
        with patch('seo_blog_workflow.mcp_client.session', session):
            with self.assertRaises(ValueError):
                asyncio.run(call(cfg, 'ph', 'search', {'query': 'booking'}))
            tool.annotations.readOnlyHint = True
            with self.assertRaises(Exception):
                asyncio.run(call(cfg, 'ph', 'search', {}))

    @unittest.skipUnless(importlib.util.find_spec('mcp'), 'MCP SDK not installed')
    def test_scheduled_oauth_requires_prior_login_without_opening_browser(self):
        from unittest.mock import AsyncMock
        from seo_blog_workflow.mcp_client import inspect
        cfg = {'mcp_servers': {'ph': {'url': 'https://mcp.producthunt.com/mcp', 'auth': 'oauth'}}}
        with patch.object(TokenStore, 'get_tokens', AsyncMock(return_value=None)):
            with patch('webbrowser.open') as browser:
                with self.assertRaises(ValueError):
                    asyncio.run(inspect(cfg, 'ph'))
                browser.assert_not_called()
