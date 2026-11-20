"""Optional remote MCP client. OAuth login is explicit; scheduled runs never prompt."""
import asyncio
import hashlib
import json
import os
import tempfile
import webbrowser
from contextlib import asynccontextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


def server_settings(config, name):
    value = config.get('mcp_servers', {}).get(name)
    if not isinstance(value, dict):
        raise ValueError('Unknown MCP server: ' + name)
    url = urlsplit(value.get('url', ''))
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('MCP server requires an HTTPS URL without embedded credentials')
    if value.get('auth', 'none') not in {'none', 'bearer', 'oauth'}:
        raise ValueError('MCP auth must be none, bearer or oauth')
    return value


def storage_path(value):
    identity = hashlib.sha256(value['url'].encode()).hexdigest()[:24]
    return Path('.mcp-auth') / (identity + '.json')


class TokenStore:
    """SDK TokenStorage interface, persisted atomically with owner-only access."""
    def __init__(self, path):
        self.path = Path(path)

    def read(self):
        if self.path.is_symlink():
            raise ValueError('OAuth token path must not be a symlink')
        if not self.path.exists():
            return {}
        if self.path.stat().st_mode & 0o077:
            raise ValueError('OAuth token file permissions must be 600')
        return json.loads(self.path.read_text())

    def write(self, field, value):
        payload = self.read()
        payload[field] = value.model_dump(mode='json', exclude_none=True)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=self.path.parent)
        try:
            with os.fdopen(descriptor, 'w') as stream:
                json.dump(payload, stream)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    async def get_tokens(self):
        from mcp.shared.auth import OAuthToken
        value = self.read().get('tokens')
        return OAuthToken.model_validate(value) if value else None

    async def set_tokens(self, tokens):
        self.write('tokens', tokens)

    async def get_client_info(self):
        from mcp.shared.auth import OAuthClientInformationFull
        value = self.read().get('client')
        return OAuthClientInformationFull.model_validate(value) if value else None

    async def set_client_info(self, client_info):
        self.write('client', client_info)


def callback_server(port):
    result = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlsplit(self.path)
            values = parse_qs(parsed.query)
            if parsed.path != '/callback' or not ('code' in values or 'error' in values):
                self.send_error(404)
                return
            result.update(values)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'Authorization received. Return to the terminal.')

        def log_message(self, *args):
            pass

    server = HTTPServer(('127.0.0.1', port), Handler)
    server.timeout = 1
    return server, result


@asynccontextmanager
async def session(config, name, login=False):
    try:
        import httpx
        from mcp.client.auth import OAuthClientProvider
        from mcp.client.session import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        from mcp.shared.auth import OAuthClientMetadata
    except ImportError:
        raise ValueError('Install MCP support with: pip install -e ".[mcp]"') from None
    value = server_settings(config, name)
    headers = {}
    auth = None
    callback = None
    try:
        mode = value.get('auth', 'none')
        if mode == 'bearer':
            token = os.environ.get(value.get('token_env', 'MCP_TOKEN'))
            if not token:
                raise ValueError('Configured MCP bearer token is missing')
            headers['Authorization'] = 'Bearer ' + token
        if mode == 'oauth':
            store = TokenStore(storage_path(value))
            if not login and await store.get_tokens() is None:
                raise ValueError('Run mcp-login --server ' + name + ' before scheduled collection')
            port = value.get('callback_port', 8769)
            if type(port) is not int or not 1024 <= port <= 65535:
                raise ValueError('Invalid MCP callback port')
            result = {}
            if login:
                callback, result = callback_server(port)

            async def redirect(url):
                if not login:
                    raise ValueError('MCP authorization expired; run mcp-login again')
                print('Opening browser for MCP authorization.', flush=True)
                webbrowser.open(url)

            async def receive():
                if not callback:
                    raise ValueError('MCP login required')
                async def wait():
                    while not result:
                        await asyncio.to_thread(callback.handle_request)
                await asyncio.wait_for(wait(), 300)
                if 'error' in result:
                    raise ValueError('MCP authorization was declined')
                return result['code'][0], result.get('state', [None])[0]

            auth = OAuthClientProvider(server_url=value['url'],
                client_metadata=OAuthClientMetadata.model_validate({
                    'client_name': 'SEO Blog Workflow',
                    'redirect_uris': [f'http://127.0.0.1:{port}/callback'],
                    'grant_types': ['authorization_code', 'refresh_token'],
                    'response_types': ['code'], 'token_endpoint_auth_method': 'none'}),
                storage=store, redirect_handler=redirect, callback_handler=receive)
        elif login:
            raise ValueError('mcp-login requires auth=oauth')
        async with httpx.AsyncClient(headers=headers, auth=auth, timeout=90, follow_redirects=False) as client:
            async with streamable_http_client(value['url'], http_client=client) as (read, write, _):
                async with ClientSession(read, write) as current:
                    await current.initialize()
                    yield current
    finally:
        if callback:
            callback.server_close()


async def tools(current):
    result = []
    cursor = None
    seen = set()
    while True:
        page = await current.list_tools(cursor=cursor)
        result.extend(page.tools)
        cursor = page.nextCursor
        if not cursor:
            return result
        if cursor in seen:
            raise ValueError('Invalid MCP tools pagination')
        seen.add(cursor)


async def inspect(config, name, login=False):
    async with session(config, name, login=login) as current:
        available = await tools(current)
        return {'server': name, 'tools': [tool.model_dump(mode='json', exclude_none=True) for tool in available]}


async def call(config, name, tool_name, arguments):
    from jsonschema import validate
    value = server_settings(config, name)
    if tool_name not in value.get('read_only_tools', []):
        raise ValueError('MCP tool must be explicitly configured in read_only_tools')
    async with session(config, name) as current:
        available = {tool.name: tool for tool in await tools(current)}
        if tool_name not in available:
            raise ValueError('Configured MCP tool was not advertised by the server')
        tool = available[tool_name]
        if tool.annotations and tool.annotations.readOnlyHint is False:
            raise ValueError('MCP tool is advertised as writing data')
        validate(arguments, tool.inputSchema)
        result = await current.call_tool(tool_name, arguments)
        if result.isError:
            raise ValueError('MCP tool returned an error')
        if result.structuredContent is not None:
            return result.structuredContent
        text = [block.text for block in result.content if block.type == 'text']
        if len(text) != 1:
            raise ValueError('MCP collector requires one JSON result or structuredContent')
        return json.loads(text[0])
