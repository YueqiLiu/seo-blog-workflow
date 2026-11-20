import json
import os
import unittest
from unittest.mock import patch

from seo_blog_workflow.product_hunt import ProductHunt, settings
from seo_blog_workflow.research import collect, initialize, plan
from seo_blog_workflow.runtime import connect
from test_research import config, Data


class ProductHuntTests(unittest.TestCase):
    def test_graphql_variables_token_and_cache(self):
        posts = {'nodes': [], 'pageInfo': {'hasNextPage': False, 'endCursor': None}}
        with connect(':memory:') as db:
            initialize(db)
            with patch.dict(os.environ, {'PRODUCT_HUNT_TOKEN': 'private-token'}):
                with patch('seo_blog_workflow.product_hunt.urlopen') as call:
                    call.return_value.__enter__.return_value.read.return_value = json.dumps({'data': {'posts': posts}}).encode()
                    api = ProductHunt(db)
                    variables = {'first': 20, 'topic': 'travel', 'since': '2026-11-20T00:00:00+00:00'}
                    self.assertEqual(api.page(variables), posts)
                    self.assertEqual(api.page(variables), posts)
                    self.assertEqual(call.call_count, 1)
                    request = call.call_args.args[0]
                    self.assertEqual(request.full_url, 'https://api.producthunt.com/v2/api/graphql')
                    self.assertEqual(json.loads(request.data)['variables'], variables)
                    self.assertNotIn('private-token', request.data.decode())

    def test_graphql_error_not_cached_as_success(self):
        with connect(':memory:') as db:
            initialize(db)
            with patch.dict(os.environ, {'PRODUCT_HUNT_TOKEN': 'private-token'}):
                with patch('seo_blog_workflow.product_hunt.urlopen') as call:
                    call.return_value.__enter__.return_value.read.return_value = b'{"errors":[{"message":"denied"}]}'
                    api = ProductHunt(db)
                    for _ in range(2):
                        with self.assertRaises(ValueError):
                            api.page({'first': 20})
                    self.assertEqual(call.call_count, 1)
                    self.assertEqual(db.execute('SELECT status FROM research_requests').fetchone()[0], 'failed')

    def test_pagination_cursor_and_page_limit(self):
        with connect(':memory:') as db:
            api = ProductHunt(db)
            with patch.object(api, 'page', side_effect=[
                {'nodes': [{'id': '1'}], 'pageInfo': {'hasNextPage': True, 'endCursor': 'next'}},
                {'nodes': [{'id': '2'}], 'pageInfo': {'hasNextPage': False, 'endCursor': 'last'}}]) as page:
                batches = list(api.pages(settings({'product_hunt': {'max_pages': 2}}), 'travel'))
                self.assertEqual(len(batches), 2)
                self.assertEqual(page.call_args_list[1].args[0]['after'], 'next')
                self.assertEqual(page.call_args_list[1].args[0]['topic'], 'travel')

    def test_launch_provenance_and_extraction_cache(self):
        class Launches:
            def pages(self, options, topic):
                yield [{'id': '7', 'name': 'Booking', 'tagline': 'Appointments',
                        'description': 'Book a session', 'url': 'https://www.producthunt.com/posts/booking',
                        'website': 'https://example.com/booking'}]
        class Model:
            calls = 0
            def structured(self, prompt):
                self.calls += 1
                return {'candidates': [{'keyword': 'booking app', 'post_id': '7'}]}
        cfg = config()
        cfg['sources'] = {'product_hunt': True, 'semrush': False, 'x': False}
        cfg['selection']['missing_metrics'] = 'allow'
        model = Model()
        with connect(':memory:') as db:
            result = collect(db, cfg, model=model, product_hunt=Launches())
            self.assertEqual(result['queued'], 1)
            collect(db, cfg, model=model, product_hunt=Launches())
            self.assertEqual(model.calls, 1)
            payload = json.loads(db.execute('SELECT payload FROM keywords').fetchone()[0])
            self.assertEqual(payload['source'], 'product_hunt')
            self.assertEqual(payload['sources'][0]['product_url'], 'https://example.com/booking')

    def test_ph_failure_does_not_block_semrush(self):
        class Broken:
            def pages(self, options, topic):
                raise ValueError('unavailable')
        cfg = config()
        cfg['sources']['product_hunt'] = True
        with connect(':memory:') as db:
            result = collect(db, cfg, data=Data(), model=object(), product_hunt=Broken())
            self.assertEqual(result['queued'], 1)
            self.assertEqual(result['failed'][0]['stage'], 'product_hunt')

    def test_invalid_settings_and_disabled_source(self):
        with self.assertRaises(ValueError):
            settings({'product_hunt': {'page_size': 0}})
        cfg = config()
        cfg['research']['product_hunt'] = {'page_size': 0}
        self.assertIsNone(plan(cfg)['product_hunt'])
