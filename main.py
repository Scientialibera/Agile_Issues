"""Agile Issue Generator – CLI entry point.

Usage:
    python main.py generate --name "my-project" --description "Build a ..."
    python main.py generate --name "my-project" --file project_brief.txt
    python main.py generate --name "my-project" --description "..." --upload jira --project-key PROJ
    python main.py generate --name "my-project" --description "..." --upload devops
    python main.py serve                          # start the FastAPI server
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from app.config.config import AgileConfig
from app.core.backlog_generator import run_pipeline


def _load_config(args: argparse.Namespace) -> AgileConfig:
    if args.config and Path(args.config).exists():
        return AgileConfig.from_toml(Path(args.config))
    env_path = Path(args.env) if args.env else Path("environment.env")
    return AgileConfig.from_env(env_path if env_path.exists() else None)


def cmd_generate(args: argparse.Namespace) -> None:
    config = _load_config(args)

    if args.file:
        description = Path(args.file).read_text(encoding="utf-8")
    elif args.description:
        description = args.description
    else:
        print("Error: provide --description or --file", file=sys.stderr)
        sys.exit(1)

    df = run_pipeline(
        config,
        description,
        args.name,
        enrich=not args.no_enrich,
        include_skills=not args.no_skills,
        include_roles=not args.no_roles,
    )

    print(f"\nGenerated {len(df)} issues → {config.output_dir}/{args.name}.csv")
    print(df[["type", "title", "parent"]].to_string(index=False))

    if args.json:
        out = Path(config.output_dir) / f"{args.name}.json"
        out.write_text(json.dumps(df.to_dict(orient="records"), indent=2), encoding="utf-8")
        print(f"\nJSON saved → {out}")

    if args.upload:
        _upload(config, df, args)


def _upload(config: AgileConfig, df, args: argparse.Namespace) -> None:
    target = args.upload.lower()

    if target == "jira":
        from app.integrations.jira_client import JiraClient

        if not args.project_key:
            print("Error: --project-key required for Jira upload", file=sys.stderr)
            sys.exit(1)
        client = JiraClient(config)
        keys = client.upload_dataframe(df, args.project_key)
        print(f"\nCreated {len(keys)} Jira issues: {keys}")

    elif target == "devops":
        from app.integrations.devops_client import DevOpsClient

        client = DevOpsClient(config)
        work_items = client.upload_dataframe(df)
        print(f"\nCreated {len(work_items)} Azure DevOps work items")

    else:
        print(f"Error: unknown upload target '{target}'. Use 'jira' or 'devops'.", file=sys.stderr)
        sys.exit(1)


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="agile-issues",
        description="Generate structured Agile backlogs using Azure OpenAI function calling.",
    )
    parser.add_argument("--env", default="environment.env", help="Path to .env file")
    parser.add_argument("--config", default=None, help="Path to config.toml (overrides .env)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")

    sub = parser.add_subparsers(dest="command", required=True)

    # ── generate ─────────────────────────────────────────────
    gen = sub.add_parser("generate", help="Generate an Agile backlog")
    gen.add_argument("--name", required=True, help="Project name (used for output filenames)")
    gen.add_argument("--description", "-d", help="Project description text")
    gen.add_argument("--file", "-f", help="Read project description from a text file")
    gen.add_argument("--no-enrich", action="store_true", help="Skip description enrichment")
    gen.add_argument("--no-skills", action="store_true", help="Skip skills generation")
    gen.add_argument("--no-roles", action="store_true", help="Skip roles generation")
    gen.add_argument("--json", action="store_true", help="Also save output as JSON")
    gen.add_argument("--upload", choices=["jira", "devops"], help="Upload after generation")
    gen.add_argument("--project-key", help="Jira project key (required with --upload jira)")

    # ── serve ────────────────────────────────────────────────
    srv = sub.add_parser("serve", help="Start the FastAPI server")
    srv.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    srv.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    srv.add_argument("--reload", action="store_true", help="Enable auto-reload for development")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(name)s | %(levelname)s | %(message)s",
    )

    if args.command == "generate":
        cmd_generate(args)
    elif args.command == "serve":
        cmd_serve(args)


if __name__ == "__main__":
    main()
