import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from seo_blog_workflow.runtime import connect
from seo_blog_workflow.research import AisaData, collect, initialize, plan, semrush_rows


def config():
    return {
        'sources': {'semrush': True, 'x': False},
        'product': {'industries': [], 'use_cases': [], 'website': 'https://example.com'},
        'research': {'seed_keywords': ['booking'], 'competitors': ['https://competitor.com'],
                     'language': 'en', 'country': 'us', 'max_candidates': 20},
        'selection': {'volume_min': 100, 'volume_max': None, 'kd_min': 0,
                      'kd_max': 50, 'missing_metrics': 'exclude', 'relevance_min': 60},
    }


class Data:
    def get(self, path, params):
        if path.endswith('broad-match-keywords'):
            return 'Keyword;Search Volume;CPC\nbooking app;500;1\nhard phrase;1000;2\nmissing;200;1'
        if path.endswith('domain-organic-keywords'):
            return 'Keyword;Position;Search Volume;CPC;Url\nBooking App;1;500;1;https://competitor.com/booking'
        if params['phrase'] == 'missing':
            return 'ERROR 50 :: NOTHING FOUND'
        return 'Keyword;Keyword Difficulty Index\n' + params['phrase'] + (';70' if params['phrase'] == 'hard phrase' else ';25')


class ResearchTests(unittest.TestCase):
    def test_metrics_filter_and_provenance_survive_deduplication(self):
        with connect(':memory:') as db:
            result = collect(db, config(), data=Data())
            self.assertEqual((result['queued'], result['filtered']), (1, 2))
            payload = json.loads(db.execute('SELECT payload FROM keywords').fetchone()[0])
            self.assertEqual(payload['kd'], 25)
            self.assertEqual(len(payload['sources']), 2)
            self.assertIn('https://competitor.com/booking', str(payload['sources']))
            again = collect(db, config(), data=Data())
            self.assertEqual(again['queued'], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM keywords').fetchone()[0], 1)

    def test_partial_metric_failure_can_recover_without_losing_other_candidates(self):
        class Broken(Data):
            def get(self, path, params):
                if path.endswith('keyword-difficulty') and params['phrase'] == 'booking app':
                    raise ValueError('unavailable')
                return super().get(path, params)
        with connect(':memory:') as db:
            result = collect(db, config(), data=Broken())
            self.assertEqual(result['remaining'], 1)
            self.assertEqual(len(result['failed']), 1)
            result = collect(db, config(), data=Data())
            self.assertEqual(result['queued'], 1)

    def test_x_keyword_has_verified_post_url_and_uses_missing_metric_policy(self):
        class Twitter:
            def get(self, path, params):
                return json.dumps({'tweets': [{'id': '123', 'text': 'Need an appointment app'}]})
        class Model:
            def structured(self, prompt):
                return {'candidates': [{'keyword': 'appointment app', 'post_id': '123'}]}
        settings = config()
        settings['sources'] = {'x': True, 'semrush': False}
        settings['selection']['missing_metrics'] = 'allow'
        with connect(':memory:') as db:
            result = collect(db, settings, data=Twitter(), model=Model())
            self.assertEqual(result['queued'], 1)
            payload = json.loads(db.execute('SELECT payload FROM keywords').fetchone()[0])
            self.assertEqual(payload['source_url'], 'https://x.com/i/status/123')
            self.assertIsNone(payload['kd'])

    def test_cached_success_and_failed_request_not_automatically_retried(self):
        with connect(':memory:') as db:
            initialize(db)
            with patch.dict(os.environ, {'AISA_API_KEY': 'secret'}):
                with patch('seo_blog_workflow.research.urlopen') as request:
                    request.return_value.__enter__.return_value.read.return_value = b'Keyword;KD\napp;20'
                    api = AisaData(db)
                    args = ('semrush/keyword-difficulty', {'phrase': 'app'})
                    self.assertEqual(api.get(*args), api.get(*args))
                    self.assertEqual(request.call_count, 1)
                with patch('seo_blog_workflow.research.urlopen', side_effect=TimeoutError) as request:
                    for _ in range(2):
                        with self.assertRaises(ValueError):
                            api.get('semrush/keyword-difficulty', {'phrase': 'another'})
                    self.assertEqual(request.call_count, 1)

    def test_unknown_provider_format_and_unsupported_channels_fail_explicitly(self):
        with self.assertRaises(ValueError):
            semrush_rows('{"message":"failure"}', ['keyword', 'kd'])
        settings = config()
        settings['sources']['google_trends'] = True
        with self.assertRaises(ValueError):
            plan(settings)
