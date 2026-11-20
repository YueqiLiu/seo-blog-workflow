import tempfile
import unittest
import os
import json
from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path
from seo_blog_workflow.github_publish import GitHub, create_review


class FakeGitHub:
    def __init__(self): self.calls=[]
    def call(self, method, path, payload=None):
        self.calls.append((method,path,payload))
        if path.startswith('/git/ref/heads/'): return {'object':{'sha':'base'}}
        if method=='GET': return {'tree':{'sha':'tree'}}
        if path=='/pulls': return {'html_url':'https://github.com/example/site/pull/1','number':1}
        return {'sha':'generated'}


class GitHubTests(unittest.TestCase):
    def test_site_code_requires_matching_base_before_upload(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'registry.ts').write_text('export const posts = [];')
            client = FakeGitHub()
            with self.assertRaises(ValueError):
                create_review(client, folder, 'blog/test')
            self.assertEqual(client.calls, [])
            with self.assertRaises(ValueError):
                create_review(client, folder, 'blog/test', expected_head='stale')
            self.assertFalse(any(c[0] == 'POST' for c in client.calls))
            result = create_review(client, folder, 'blog/test', expected_head='base')
            self.assertEqual(result['status'], 'pr_created')

    def test_cli_transport_passes_payload_and_token_without_command_line_secret(self):
        with patch.dict(os.environ, {'BLOG_GITHUB_TOKEN':'test-token', 'BLOG_GITHUB_TRANSPORT':'gh'}):
            with patch('seo_blog_workflow.github_publish.subprocess.run') as run:
                run.return_value = SimpleNamespace(returncode=0, stdout='{"sha":"blob"}')
                result = GitHub('owner/site').call('POST', '/git/blobs', {'content':'data'})
                self.assertEqual(result['sha'], 'blob')
                args, kwargs = run.call_args
                self.assertNotIn('test-token', ' '.join(args[0]))
                self.assertEqual(kwargs['env']['GH_TOKEN'], 'test-token')
                self.assertEqual(json.loads(kwargs['input']), {'content':'data'})

    def test_draft_pr_and_no_main_write(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'article.md').write_text('# Article')
            client=FakeGitHub()
            result=create_review(client,folder,'blog/test')
            self.assertFalse(result['published'])
            self.assertTrue(client.calls[-1][2]['draft'])
            refs=[c for c in client.calls if c[1]=='/git/refs']
            self.assertEqual(refs[0][2]['ref'],'refs/heads/blog/test')
            self.assertFalse(any(c[0]=='PATCH' for c in client.calls))

    def test_secrets_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'.env').write_text('secret')
            client=FakeGitHub()
            with self.assertRaises(ValueError): create_review(client,folder,'blog/test')
            self.assertEqual(client.calls,[])
