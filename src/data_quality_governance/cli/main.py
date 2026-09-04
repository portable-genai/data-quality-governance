"""Minimal stdlib CLI: certify a dataset, or verify the audit chain (argparse, no extra deps)."""

from __future__ import annotations

import argparse
import sys

from hex_service_kit.logging import configure_logging

from ..config import build_container
from ..service_factory import build_certification_service


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="data_quality_governance")
    sub = parser.add_subparsers(dest="command", required=True)

    certify_cmd = sub.add_parser("certify", help="Certify a single dataset.")
    certify_cmd.add_argument("dataset_id")
    certify_cmd.add_argument("--actor", default="cli-user@bank.example")
    certify_cmd.add_argument(
        "--tenant", default="demo-bank", help="Tenant partition (human-review-console)."
    )

    args = parser.parse_args(argv)
    container = build_container()
    # Idempotent: a process that is both an API app and a CLI configures once.
    configure_logging(container.settings.profile, service="data-quality-governance")

    if args.command == "certify":
        service = build_certification_service(container)
        result = service.certify(args.dataset_id, actor=args.actor, tenant=args.tenant)
        print(f"{result.subject}: {result.status.value} (pass_ratio {result.pass_ratio})")
        print(f"  requires_human_review: {result.requires_human_review}")
        print(f"  certified metrics: {', '.join(result.certified_metrics) or '(none)'}")
        if result.requires_human_review:
            # Rule R8 on the CLI path too: the same escalation, the same router. A surface that
            # only printed the flag would be a second place for an escalation to stop.
            ref = container.review_router.route(result, maker=args.actor, tenant=args.tenant)
            print(f"  routed to human review: {ref}")
        return 0

    return 2  # pragma: no cover - argparse requires a subcommand


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
