"""Read public Product Hunt launches through its official GraphQL API."""
import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen


QUERY = '''query Launches($first: Int!, $after: String, $topic: String,
                         $since: DateTime!, $until: DateTime!, $order: PostsOrder!) {
  posts(first: $first, after: $after, topic: $topic, postedAfter: $since,
        postedBefore: $until, order: $order) {
    nodes { id name tagline description url website votesCount }
    pageInfo { hasNextPage endCursor }
  }
}'''


def settings(research):
    value = research.get('product_hunt', {})
    topics = value.get('topics', [])
    if not isinstance(topics, list) or any(not isinstance(t, str) or not re.fullmatch(r'[a-z0-9-]+', t) for t in topics):
        raise ValueError('Product Hunt topics must be topic slugs')
    result = {'topics': list(dict.fromkeys(topics)), 'days': value.get('days', 1),
              'page_size': value.get('page_size', 20), 'max_pages': value.get('max_pages', 1),
              'order': value.get('order', 'NEWEST'), 'transport': value.get('transport', 'api')}
    if result['transport'] not in {'api', 'mcp'}:
        raise ValueError('Product Hunt transport must be api or mcp')
    if result['transport'] == 'mcp':
        if topics:
            raise ValueError('Use mcp_arguments.category for MCP category filtering; leave topics empty')
        result['mcp_server'] = value.get('mcp_server', 'producthunt')
        result['mcp_tool'] = value.get('mcp_tool', 'search_products')
        result['mcp_arguments'] = value.get('mcp_arguments', {})
        if result['mcp_tool'] not in {'search_products', 'get_product_leaderboard'}:
            raise ValueError('Product Hunt collection requires a search or leaderboard tool')
        if not isinstance(result['mcp_arguments'], dict):
            raise ValueError('mcp_arguments must be an object')
    for field, maximum in (('days', 31), ('page_size', 50), ('max_pages', 100)):
        if type(result[field]) is not int or not 1 <= result[field] <= maximum:
            raise ValueError('Invalid Product Hunt ' + field)
    if result['order'] not in {'NEWEST', 'VOTES', 'RANKING', 'FEATURED_AT'}:
        raise ValueError('Invalid Product Hunt order')
    return result


class ProductHunt:
    def __init__(self, db, retry_failed=False):
        self.db = db
        self.retry_failed = retry_failed

    def page(self, variables):
        identity = 'product-hunt-' + hashlib.sha256(json.dumps(variables, sort_keys=True).encode()).hexdigest()
        row = self.db.execute('SELECT * FROM research_requests WHERE id=?', (identity,)).fetchone()
        if row and row['status'] == 'success':
            return json.loads(row['response'])
        if row and (not self.retry_failed or row['status'] == 'started'):
            raise ValueError('Product Hunt request needs reconciliation before retry')
        token = os.environ.get('PRODUCT_HUNT_TOKEN')
        if not token:
            raise ValueError('PRODUCT_HUNT_TOKEN is missing')
        with self.db:
            if row:
                changed = self.db.execute("UPDATE research_requests SET status='started',error=NULL WHERE id=? AND status='failed'", (identity,)).rowcount
            else:
                changed = self.db.execute('INSERT OR IGNORE INTO research_requests VALUES (?,?,NULL,NULL)', (identity, 'started')).rowcount
            if not changed:
                raise ValueError('Product Hunt request already running')
        request = Request('https://api.producthunt.com/v2/api/graphql',
                          data=json.dumps({'query': QUERY, 'variables': variables}).encode(),
                          headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
                                   'Accept': 'application/json', 'User-Agent': 'seo-blog-workflow'})
        try:
            with urlopen(request, timeout=90) as response:
                payload = json.load(response)
            if payload.get('errors'):
                raise ValueError('Product Hunt GraphQL error')
            posts = payload['data']['posts']
            if not isinstance(posts['nodes'], list) or type(posts['pageInfo']['hasNextPage']) is not bool:
                raise ValueError('Unexpected Product Hunt response')
            with self.db:
                self.db.execute("UPDATE research_requests SET status='success',response=? WHERE id=?",
                                (json.dumps(posts), identity))
            return posts
        except Exception as error:
            detail = 'HTTP ' + str(error.code) if isinstance(error, HTTPError) else type(error).__name__
            with self.db:
                self.db.execute("UPDATE research_requests SET status='failed',error=? WHERE id=?", (detail, identity))
            raise ValueError('Product Hunt request failed: ' + detail) from None

    def pages(self, options, topic):
        # Stable UTC windows allow resumable daily runs without changing cache keys.
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        variables = {'first': options['page_size'], 'after': None, 'topic': topic,
                     'since': (today - timedelta(days=options['days'] - 1)).isoformat(),
                     'until': (today + timedelta(days=1)).isoformat(), 'order': options['order']}
        seen = set()
        for _ in range(options['max_pages']):
            page = self.page(variables)
            yield page['nodes']
            info = page['pageInfo']
            if not info['hasNextPage']:
                return
            cursor = info.get('endCursor')
            if not isinstance(cursor, str) or not cursor or cursor in seen:
                raise ValueError('Invalid Product Hunt pagination cursor')
            seen.add(cursor)
            variables = dict(variables, after=cursor)
