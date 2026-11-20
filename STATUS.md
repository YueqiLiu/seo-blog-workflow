# Implementation status

Reviewed 2026-11-20. Version 0.1.0 is an open-source preview.

## Working

- CSV normalization and exact keyword deduplication in SQLite.
- Configurable volume, KD, missing-metric policy and relevance threshold.
- Model relevance using a manually supplied product profile.
- OpenAI-compatible text APIs and explicit AISA provider settings.
- Structured article generation, bounded repairs, failure isolation and backups.
- Markdown export, template covers and synchronous base64 PNG image APIs.
- AISA live text and single-cover generation validated by the owner.
- AISA X search and Semrush seed/domain collection, metric filtering, provenance,
  persistent request caching and partial-failure recovery implemented with mock tests.
- Official Product Hunt GraphQL launch collection with topic/date settings,
  pagination, model keyword extraction, source URLs and cached recovery implemented.
- Optional remote MCP client with tool discovery, read-only calls, schema validation,
  bearer authentication and SDK-backed persistent OAuth. Product Hunt MCP collection
  feeds the existing queue. Real public discovery and search returned two products.
- Explicit GitHub draft PR delivery tested live on a Next.js website. Owner merged
  PR #9; production article and PNG returned HTTP 200 with expected content.
- WanderChina-specific JSON/image bundle export. Its renderer was adapted in
  the separate website repository and an article was pushed manually.

## Not yet implemented or verified

- Product website fetching and editable derived profiles.
- Google Trends collection. Live Product Hunt and AISA X/Semrush account tests
  remain pending. Website-specific bundle export still requires adaptation.
- Browser OAuth login verification and MCP stdio/legacy SSE transports.
- Automatic PR merging and programmatic deployment verification.
- Actual daily successful-publication quotas and scheduled recovery.
- Automatic source verification or factual readiness judgments.
- Semantic article deduplication, cloud storage and asynchronous image adapters.
- Docker execution verification. Installation and unit tests are verified locally;
  CI covers Python 3.10 and 3.12 after push.

## Next milestones

1. Generic GitHub publication adapter with draft/PR/publish states and explicit
   publication verification; transactional quota and idempotent recovery.
2. Product website profiles and optional collection adapters with tests.
3. End-to-end acceptance, clean examples, installation docs and public release.

Personal case fixtures, databases, generated output, and OAuth credentials are
excluded from the initial repository. The legacy `export-wanderchina` adapter
is a site-specific example and requires its own website renderer.
