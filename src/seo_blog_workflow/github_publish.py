"""GitHub review delivery using an atomic tree commit; never merges PRs."""
import base64
import json
import os
import subprocess
from pathlib import Path, PurePosixPath
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError


class GitHub:
    def __init__(self, repository, token_env='BLOG_GITHUB_TOKEN'):
        parts = repository.split('/')
        if len(parts) != 2 or any(not p or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.' for c in p) for p in parts):
            raise ValueError('Expected owner/repository')
        self.root = 'https://api.github.com/repos/' + repository
        self.token_env = token_env

    def call(self, method, path, payload=None):
        token = os.environ.get(self.token_env)
        if not token:
            raise ValueError('GitHub token environment variable is missing')
        if os.environ.get('BLOG_GITHUB_TRANSPORT') == 'gh':
            environment = os.environ.copy()
            environment['GH_TOKEN'] = token
            command = ['gh', 'api', '--hostname', 'github.com', '--method', method,
                       self.root.removeprefix('https://api.github.com/') + path]
            if payload is not None:
                command += ['--input', '-']
            result = subprocess.run(command,
                input=json.dumps(payload) if payload is not None else None,
                text=True, capture_output=True, env=environment, timeout=120)
            if result.returncode:
                detail = result.stderr.replace(token, '[redacted]')[:600]
                raise RuntimeError(f'GitHub CLI failed at {method} {path}: {detail}')
            return json.loads(result.stdout)
        request = Request(self.root + path, method=method,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={'Authorization':'Bearer '+token, 'Accept':'application/vnd.github+json',
                     'Content-Type':'application/json', 'User-Agent':'seo-blog-workflow'})
        try:
            with urlopen(request, timeout=60) as response:
                return json.load(response)
        except HTTPError as error:
            detail = 'Response did not contain a GitHub error message'
            try:
                response = json.loads(error.read(8192))
                message = response.get('message')
                if isinstance(message, str):
                    detail = message.replace(token, '[redacted]')[:400]
            except (ValueError, UnicodeError):
                pass
            raise RuntimeError(f'GitHub HTTP {error.code} at {method} {path}: {detail}; reconcile branch/PR before retry') from None


def create_review(client, bundle, branch, base='main', title='Add generated blog article', expected_head=None):
    """A unique branch is required. Existing refs fail closed; never force push."""
    if not branch.startswith('blog/') or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_/.' for c in branch) or '..' in branch:
        raise ValueError('Use a unique blog/... branch')
    root = Path(bundle).resolve()
    files = sorted(p for p in root.rglob('*') if p.is_file())
    if not files:
        raise ValueError('Empty release bundle')
    entries = []
    # Explicitly reviewed site registry code requires a pinned base commit.
    for file in files:
        relative = file.relative_to(root).as_posix()
        if file.is_symlink() or not file.resolve().is_relative_to(root) or any(part.startswith('.') for part in PurePosixPath(relative).parts):
            raise ValueError('Unsafe bundle path')
        is_site_code = file.suffix.lower() in {'.ts', '.tsx'}
        if is_site_code and not expected_head:
            raise ValueError('Site code requires --expected-head to prevent overwriting newer changes')
        if file.suffix.lower() not in {'.md','.mdx','.json','.png','.jpg','.jpeg','.webp','.svg'} and not is_site_code:
            raise ValueError('Unsupported release file: '+relative)
        if file.stat().st_size > 10 * 1024 * 1024:
            raise ValueError('Release file exceeds 10 MiB')
        entries.append((relative,file.read_bytes()))
    head = client.call('GET','/git/ref/heads/'+quote(base,safe=''))['object']['sha']
    if expected_head is not None and expected_head != head:
        raise ValueError('Base branch changed; rebuild the release bundle against the current commit')
    tree = client.call('GET','/git/commits/'+head)['tree']['sha']
    blobs = []
    for path, data in entries:
        print('Uploading '+path, flush=True)
        sha = client.call('POST','/git/blobs',{'content':base64.b64encode(data).decode(), 'encoding':'base64'})['sha']
        blobs.append({'path':path,'mode':'100644','type':'blob','sha':sha})
    new_tree = client.call('POST','/git/trees',{'base_tree':tree,'tree':blobs})['sha']
    commit = client.call('POST','/git/commits',{'message':title,'tree':new_tree,'parents':[head]})['sha']
    client.call('POST','/git/refs',{'ref':'refs/heads/'+branch,'sha':commit})
    pr = client.call('POST','/pulls',{'title':title,'head':branch,'base':base,'draft':True,
        'body':'Generated article review. Check factual accuracy, image rendering, links and deployment before merging. This PR does not confirm live publication.'})
    return {'status':'pr_created','pr_url':pr['html_url'],'pr_number':pr['number'],'commit':commit,'branch':branch,'published':False}
