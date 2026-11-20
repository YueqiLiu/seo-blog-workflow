"""Persist read-only MCP collection results and adapt Product Hunt results."""
import asyncio
import hashlib
import json
from datetime import datetime, timezone

from .mcp_client import call, server_settings


def cached_call(db, config, server, tool, arguments, retry_failed=False):
    value = server_settings(config, server)
    identity = 'mcp-' + hashlib.sha256(json.dumps({
        'date': datetime.now(timezone.utc).date().isoformat(),
        'url': value['url'], 'tool': tool, 'arguments': arguments}, sort_keys=True).encode()).hexdigest()
    row = db.execute('SELECT * FROM research_requests WHERE id=?', (identity,)).fetchone()
    if row and row['status'] == 'success':
        return json.loads(row['response'])
    if row and (not retry_failed or row['status'] == 'started'):
        raise ValueError('MCP request needs reconciliation before retry')
    with db:
        if row:
            changed = db.execute("UPDATE research_requests SET status='started',error=NULL WHERE id=? AND status='failed'", (identity,)).rowcount
        else:
            changed = db.execute('INSERT OR IGNORE INTO research_requests VALUES (?,?,NULL,NULL)', (identity, 'started')).rowcount
        if not changed:
            raise ValueError('MCP request already running')
    try:
        result = asyncio.run(call(config, server, tool, arguments))
        if isinstance(result, dict) and result.get('status') in {'error', 'needs_auth', 'auth_required'}:
            raise ValueError('MCP source returned an error or needs authorization')
        with db:
            db.execute("UPDATE research_requests SET status='success',response=? WHERE id=?", (json.dumps(result), identity))
        return result
    except Exception as error:
        with db:
            db.execute("UPDATE research_requests SET status='failed',error=? WHERE id=?", (type(error).__name__, identity))
        raise


class ProductHuntMCP:
    def __init__(self, db, config, retry_failed=False):
        self.db = db
        self.config = config
        self.retry_failed = retry_failed

    def pages(self, options, topic):
        tool = options['mcp_tool']
        arguments = dict(options['mcp_arguments'])
        if tool == 'search_products':
            arguments.setdefault('limit', min(options['page_size'], 25))
            if not any(key in arguments for key in ('launched_within_days', 'launched_after', 'launched_before')):
                arguments['launched_within_days'] = options['days']
            arguments.setdefault('sort', 'newest')
        seen = set()
        for _ in range(options['max_pages']):
            result = cached_call(self.db, self.config, options['mcp_server'], tool, arguments, self.retry_failed)
            data = result.get('data', {})
            items = data.get('results')
            if not isinstance(items, list):
                raise ValueError('Unexpected Product Hunt MCP result; expected data.results')
            posts = []
            for item in items:
                posts.append({'id': item['slug'], 'name': item['name'], 'url': item['url'],
                              'tagline': item.get('tagline', ''), 'description': item.get('description', ''),
                              'website': item.get('website_url', '')})
            yield posts
            if not data.get('has_more'):
                return
            cursor = data.get('next_cursor')
            if not isinstance(cursor, str) or not cursor or cursor in seen:
                raise ValueError('Invalid Product Hunt MCP cursor')
            seen.add(cursor)
            arguments = dict(arguments, cursor=cursor)
