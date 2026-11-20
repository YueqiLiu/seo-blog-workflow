"""Command-line interface. Export mode never implies successful publication."""
import argparse
import json
from .config import load_config
from .runtime import ModelAPI, connect, import_csv, run, safe_error


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--database", default="workflow.sqlite3")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate")
    importer = commands.add_parser("import-csv")
    importer.add_argument("path")
    commands.add_parser("status")
    runner = commands.add_parser("run")
    runner.add_argument("--collect", action="store_true")
    commands.add_parser("check-model")
    commands.add_parser("list-models")
    collector = commands.add_parser("collect")
    collector.add_argument("--execute", action="store_true")
    collector.add_argument("--retry-failed", action="store_true")
    for name in ('mcp-tools', 'mcp-login'):
        command = commands.add_parser(name)
        command.add_argument('--server', required=True)
    mcp_call = commands.add_parser('mcp-call')
    mcp_call.add_argument('--server', required=True)
    mcp_call.add_argument('--tool', required=True)
    mcp_call.add_argument('--arguments', default='{}')
    cover = commands.add_parser("generate-cover")
    cover.add_argument("--keyword", required=True)
    bundle = commands.add_parser("export-wanderchina")
    bundle.add_argument("--keyword", required=True)
    bundle.add_argument("--destination", required=True)
    pr = commands.add_parser("create-pr")
    pr.add_argument("--repository", required=True)
    pr.add_argument("--bundle", required=True)
    pr.add_argument("--branch", required=True)
    pr.add_argument("--base", default="main")
    pr.add_argument("--receipt", required=True)
    pr.add_argument("--expected-head")
    args = parser.parse_args()
    config = load_config(args.config)
    if args.command in {'mcp-tools', 'mcp-login', 'mcp-call'}:
        import asyncio
        from .mcp_client import inspect, call
        try:
            if args.command == 'mcp-call':
                result = asyncio.run(call(config, args.server, args.tool, json.loads(args.arguments)))
            else:
                result = asyncio.run(inspect(config, args.server, login=args.command == 'mcp-login'))
            print(json.dumps(result, indent=2))
        except Exception as error:
            # Provider exception groups can contain authorization URLs or headers.
            parser.exit(1, 'MCP connection failed (' + type(error).__name__ + '). Check SDK installation, server settings and authorization.\n')
        return
    if args.command == 'collect':
        from .research import plan, collect
        if not args.execute:
            print(json.dumps(plan(config), indent=2))
            return
        with connect(args.database) as db:
            report = collect(db, config, retry_failed=args.retry_failed)
        print(json.dumps(report, indent=2))
        if report['failed']:
            raise SystemExit(1)
        return
    if args.command == "create-pr":
        import os
        from pathlib import Path
        from .github_publish import GitHub, create_review
        if not os.environ.get('BLOG_GITHUB_TOKEN'):
            parser.exit(1, 'BLOG_GITHUB_TOKEN is missing in this terminal. Configure and export it before creating a PR.\n')
        receipt = Path(args.receipt)
        receipt.parent.mkdir(parents=True, exist_ok=True)
        # Reserve the receipt before remote writes. Unknown outcomes require
        # reconciliation, not blind repetition of a paid or stateful action.
        with receipt.open('x', encoding='utf-8') as stream:
            json.dump({'status':'started','repository':args.repository,'branch':args.branch},stream)
        result = create_review(GitHub(args.repository), args.bundle, args.branch, args.base,
                               expected_head=args.expected_head)
        receipt.write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
        return
    if args.command == "validate":
        print("Configuration valid")
        return
    if args.command in {"check-model", "list-models"}:
        try:
            if args.command == "list-models":
                api = ModelAPI(config["models"])
                available = api.models()
                print(json.dumps({"configured_model": config["models"]["text_model"],
                                  "listed": config["models"]["text_model"] in available,
                                  "models": available}, indent=2))
                return
            result = ModelAPI(config["models"]).structured('Return a JSON object with "ok": true.')
            print(json.dumps({"model_connection": "ok", "json_response": result.get("ok") is True}))
        except Exception as error:
            print(json.dumps({"model_connection": "failed", "error": safe_error(error)}))
            raise SystemExit(1)
        return
    with connect(args.database) as db:
        research_report = None
        if args.command == 'run' and args.collect:
            from .research import collect
            research_report = collect(db, config)
        if args.command == "import-csv":
            result = {"imported": import_csv(db, args.path)}
        elif args.command == "export-wanderchina":
            from .wanderchina import export_bundle
            result = export_bundle(db, args.keyword, args.destination, config["publication"]["timezone"])
        elif args.command == "generate-cover":
            from .images import generate_cover
            try:
                result = generate_cover(db, config, args.keyword)
            except Exception as error:
                print(json.dumps({"image_generation": "failed", "error": safe_error(error)}))
                raise SystemExit(1)
        elif args.command == "status":
            result = dict(db.execute("SELECT status,COUNT(*) FROM keywords GROUP BY status").fetchall())
        else:
            if config["publication"]["mode"] != "draft":
                raise ValueError("Only draft export is connected in this version; publication adapter pending")
            result = run(db, config)
            if research_report is not None:
                result['research'] = research_report
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
