# SEO Blog Workflow

Research keywords, assess their relevance to your product, generate articles and
covers, and deliver reviewed files to GitHub as draft pull requests. Configure
your industry, use cases, keyword sources, metric ranges and model APIs.

**v0.1.0 preview** runs locally with Python and SQLite. It supports Product Hunt
through its official API or MCP, X and Semrush through AISA, and CSV import.
Text and image providers use configurable OpenAI-compatible endpoints.
See [STATUS.md](STATUS.md) for tested capabilities and remaining work.

This preview exports drafts and creates PRs on explicit request. Website layout
adaptation and merging are manual steps. The daily target currently limits
exports per run; an unattended daily publication scheduler is on the roadmap.

## Install

Requires Python 3.10+.

```sh
git clone https://github.com/YueqiLiu/seo-blog-workflow.git
cd seo-blog-workflow
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[mcp]'
cp examples/config.aisa.json config.json
```

Edit `config.json` with your product website, name, industries and use cases.
The relevance model uses this supplied profile; automatic website analysis is
planned. Pick a model available to your provider account.

Set the key in the same terminal. In macOS's default zsh, run the first line,
wait for its prompt, then paste your key and press Enter. Run the export next.

```zsh
read -rs 'AISA_API_KEY?Paste your AISA key and press Enter: '
export AISA_API_KEY
```

The program reads exported environment variables. `.env.example` documents the
names; `.env` files are not automatically loaded. For another provider, copy
`config.example.json`, set its `base_url`, `text_model`, and `api_key_env`, and
export the corresponding key.

```sh
seo-blog validate
seo-blog check-model
seo-blog import-csv examples/keywords.csv
seo-blog run
seo-blog status
```

The example CSV contains **synthetic sample metrics** for an appointment-booking
use case. Replace it with your own research. `check-model`, `run`, image API
generation and executed data collection can incur provider charges. Inspect
generated Markdown, images and editorial reports in `output/`.

## Local quick start

### AISA model gateway

Copy `examples/config.aisa.json` to `config.json`, edit the product information,
and set `AISA_API_KEY` in your shell. Choose a model available to your account;
`gpt-5.4-mini` is the model shown in AISA's chat documentation, not a guaranteed account
entitlement. Then use the commands below. No Kubernetes deployment is required.

`provider: "aisa"` defaults to `https://api.aisa.one/v1` and the environment
variable `AISA_API_KEY`. Text relevance and article generation use non-streaming
`POST /chat/completions` with Bearer authentication. Other OpenAI-compatible
providers remain supported through explicit `base_url` and `api_key_env`.

The AISA example uses template images without an image API charge. AISA's native
image models may use different request/response formats; those are not certified
by this integration. The existing image API adapter requires synchronous PNG
`b64_json` responses and is not a universal AISA image adapter.

To generate covers during `run`, replace the `images` block with:

```json
{"mode":"api","provider":"aisa","model":"gpt-image-2","api_key_env":"AISA_API_KEY","size":"1536x864","timeout_seconds":300}
```

Choose an image model and size supported by your account. `mode=template` creates
a local SVG card; `mode=none` skips image generation. URL-based responses and
asynchronous image jobs require additional adapters.

Owner-run live tests generated three drafts and an AISA PNG cover. Automated
tests use mocked provider responses and synthetic fixtures.

Requires Python 3.10+. Install with `pip install -e .`, copy
`config.example.json` to `config.json`, edit the product and `text_model`, and
set `LLM_API_KEY` in your shell environment. The program does not load `.env`
automatically.

```sh
seo-blog validate
seo-blog import-csv examples/keywords.csv
seo-blog run
seo-blog status
```

CSV fields: `keyword`, `search_volume`, `kd`, `source_url`, `source`. Missing
metrics follow the configured policy. Relevance is assessed by the model.
Source URLs are retained as evidence; remote page contents are not fetched yet.
Draft export is the only enabled mode; it never records a successful publication.
Do not enable scheduled execution until a publishing adapter is configured.

Tests: `PYTHONPATH=src python -m unittest discover -s tests`.

Generated and saved drafts now undergo editorial checks and up to two targeted
model revisions per run. Configure `editorial.max_repair_attempts` from 0 to 5
to change the cap. Failed checks produce `needs_revision` and do not block other
articles. Each revision can incur model charges. Retries on a later run have a
new per-run allowance. Original article JSON is retained in the output folder.
The checks cover structure, metadata, FAQ, product links and selected internal
note leaks; they do not establish factual accuracy or publication readiness.
`editorial-audit.json` explicitly records the remaining fact-check limitation.

Copy `config.example.json` to `config.json`. Configure your product website,
industries, use cases, source switches, metric ranges, relevance threshold, and
daily successful-publication target. Disabled sources require no credentials.
Keep credentials in environment variables, never configuration files.

The configured daily publication target is not yet enforced by a publisher:
`run` currently uses the remaining target as a per-run export cap. Drafts do not
count as published, so repeated runs are not a daily publishing scheduler.
Failed articles do not block completed articles. A zero target stops new exports.
Missing Semrush data is excluded by default and can be explicitly allowed.

Planned stages: collect → enrich → relevance → deduplicate → generate → validate
→ publish → verify. Persist stage state, use unique publication identifiers and
worker leases, and reserve quota transactionally to prevent concurrent overrun.

Product website content is untrusted input. Website fetching must block private
networks and validate redirects; extracted text cannot override system rules.
Users must be able to edit the resulting product profile before selection.

## Research and delivery

### AISA keyword research

Copy `examples/config.aisa-research.json` to `config.json`, edit your product,
seed keywords, X search queries and competitor domains, then export `AISA_API_KEY`.
The same key accesses AISA data endpoints and its model gateway. A different
text model provider can be configured independently.

```sh
seo-blog collect
seo-blog collect --execute
seo-blog run
# Or collect and generate with one invocation:
seo-blog run --collect
```

`collect` displays a plan. `--execute` makes paid calls. Semrush discovery uses
broad-match keywords and competitor organic keywords. X search uses the Latest
results page and the configured text model to extract keyword phrases with
validated post IDs. Collection currently processes the first returned page.
Metric enrichment processes `research.max_candidates` pending terms per run
(default 20). This limits processing volume, not provider spend. Each discovery
input and each uncached metric lookup may incur charges. X extraction also uses
the text API. Review your plan and the provider's current pricing before execution.

The collector preserves keyword, volume, KD, source URLs and all discovery
sources in SQLite. Identical normalized phrases share one candidate. Collection
filters metric ranges first; generation then uses the existing model relevance
assessment. Missing data follows `selection.missing_metrics`. Source pages are
retained as references and are not automatically downloaded for rewriting.

Successful discovery requests are cached per UTC day, metric calls per UTC
month, and X extraction per prompt. Failed or interrupted requests are held for
inspection. After checking AISA usage, `collect --execute --retry-failed` retries
recorded failures. Requests left in `started` need manual reconciliation.
Completed candidates survive other source failures. `run --collect` proceeds
with available queued keywords and includes collection errors in its report.
Google Trends enabled in `sources` produces an explicit error until its collector
is implemented. Disabled sources make no requests.

### Product Hunt launches

Enable `sources.product_hunt` and export `PRODUCT_HUNT_TOKEN` from the
[official API dashboard](https://www.producthunt.com/v2/oauth/applications).
Use a public-read developer or OAuth access token. This credential is independent
of `AISA_API_KEY`. The program reads environment variables from its own terminal
and does not load `.env` automatically.

`research.product_hunt` supports `topics` (topic slugs; empty means all topics),
`days` (1–31 UTC calendar days including today), `page_size` (1–50), `max_pages`
(1–100 per topic), and `order` (`NEWEST`, `VOTES`, `RANKING`, `FEATURED_AT`).
The AISA research example includes these settings with Product Hunt disabled.
Enable the switch when its token is configured, then use the same `collect` or
`run --collect` commands. No additional command is needed.

The collector queries the official GraphQL API, caches each page for its daily
window, and feeds launch names, taglines and descriptions into the configured
text model. Candidate records preserve the Product Hunt post URL, launch title
and product website URL. Extracted source IDs must match fetched launches.
Model extraction results are cached. Partial pages remain usable after a later
page fails. API failures are isolated from other channels.

Product Hunt is the source of launch data. Its
[API documentation](https://api.producthunt.com/v2/docs) asks business users to
contact Product Hunt for commercial permission. This adapter uses its GraphQL
API. Its [official MCP](https://www.producthunt.com/mcp/install?client=vscode)
is supported through the MCP connection described below. Product Hunt GraphQL credential
testing is pending.

### MCP connections

Install the optional official Python SDK integration:

```sh
pip install -e '.[mcp]'
seo-blog --config examples/config.producthunt-mcp.json mcp-tools --server producthunt
seo-blog --config examples/config.producthunt-mcp.json mcp-call --server producthunt --tool search_products --arguments '{"query":"booking","limit":2}'
```

Remote Streamable HTTP servers are configured under `mcp_servers`. Each has an
HTTPS `url`, an `auth` mode (`none`, `bearer`, or `oauth`), and an explicit
`read_only_tools` list. Bearer authentication reads `token_env` (default
`MCP_TOKEN`). Requests validate tool arguments against the server's JSON schema
and reject tools advertised as writing data. Tool results and source content
are untrusted input. Keep tool allowlists limited to the research functions
you reviewed. Other providers can be inspected and called through the same
client; automatic keyword ingestion currently has a Product Hunt adapter.

The Product Hunt MCP example uses its public `search_products` tool, which was
verified live without credentials. Discovery and a two-result search succeeded.
Set your product profile and desired query before enabling collection. Its
`missing_metrics=allow` setting permits terms without Semrush metrics; set
`sources.semrush=true` to enrich them, and use `missing_metrics=exclude` when
metrics are required.

```sh
seo-blog --config examples/config.producthunt-mcp.json collect
seo-blog --config examples/config.producthunt-mcp.json collect --execute
seo-blog --config examples/config.producthunt-mcp.json run --collect
```

`research.product_hunt.transport=mcp` selects MCP in place of GraphQL.
`mcp_server`, `mcp_tool` and `mcp_arguments` select the connection and search.
Supported collector tools are `search_products` and `get_product_leaderboard`.
For search, `days` supplies `launched_within_days` unless explicit dates are
provided, and `page_size` supplies `limit` up to 25. Configure category filters
in `mcp_arguments.category` and leave API `topics` empty. `max_pages` bounds cursor
pagination. MCP date windows use the server's Pacific-time semantics. The
leaderboard tool accepts its own `date` argument; API `days`, `order` and topic
filters do not apply to it. Results enter the same extraction, metric and
relevance pipeline as API results.

For an OAuth server, set `auth=oauth` and run:

```sh
seo-blog --config config.json mcp-login --server producthunt
```

This explicitly opens the browser and listens on loopback port 8769 (configurable
as `callback_port`). The SDK handles discovery, client registration, PKCE,
state validation and refresh. OAuth tokens and client information are saved
in `.mcp-auth/` with owner-only file permissions. This directory is ignored by
Git. Run future commands from the same directory; for container scheduling,
mount its private persistent storage. Existing credentials from Codex or other
MCP clients are not automatically imported. Scheduled runs can refresh stored
tokens, and require `mcp-login` again if interactive authorization is needed.
OAuth support is SDK-backed and covered by local tests; a real browser login
has not yet been tested. Legacy SSE and stdio transports are not implemented.

Request contracts follow the official AISA references:
[Semrush](https://aisa.one/catalog/apis/semrush) and
[X search](https://aisa.one/tools/twitter-advanced-search).
These new adapters have fixture and mocked HTTP tests. Live account validation
is still required before enabling scheduled collection.

### Draft GitHub PR delivery (explicit command)

The `create-pr` command uploads a reviewed bundle to a unique `blog/...` branch
and opens a draft PR. Configure `BLOG_GITHUB_TOKEN` with access limited to the
target repository (Contents and Pull requests read/write). No workflow-write or
merge permission is requested. Never put the token in arguments or JSON files.

```sh
seo-blog --config config.json create-pr --repository owner/site --bundle output/release --branch blog/article-unique-id --receipt output/pr-receipt.json
```

Only run after checking every file in the bundle. Allowed extensions are not a
secret scanner: review JSON/Markdown for private material. Existing receipt files
block re-execution. If a request fails, inspect the remote branch and PR before
retrying; the command currently requires manual reconciliation. The receipt is
not an article publication record and this command is not yet connected to the
daily quota module. No automatic merge or live deployment verification occurs.

Reviewed Markdown, MDX, JSON and PNG/JPEG/WebP/SVG files can be included in a bundle.
TypeScript registry changes additionally require `--expected-head COMMIT_SHA`;
the command verifies the target branch still matches before uploading. Build
the bundle against that commit. This protects existing site updates while
keeping site-specific registry code outside the publisher. It does not adapt a
site's renderer automatically. For Python SSL connection issues, install and
verify GitHub CLI, then set `BLOG_GITHUB_TRANSPORT=gh` to use it with the same
exported `BLOG_GITHUB_TOKEN`.

## Roadmap

- Connect the optional Google Trends adapter.
- Add editable website-derived product profiles and structured model scoring.
- Add Supabase migrations, recoverable queue state and publication reservations.
- Add generic GitHub publishing, verified live state and daily reservations.
- Verify Docker build and add scheduling examples, onboarding and release checks.

## Development

```sh
python -m unittest discover -s tests
```

Tests use synthetic data and mocked paid APIs. With MCP extras installed, the
OAuth storage and SDK boundary tests also run. GitHub Actions runs this suite
on Python 3.10 and 3.12. No API keys are needed for tests.

## License

MIT. External services retain their own access, billing and usage terms.
