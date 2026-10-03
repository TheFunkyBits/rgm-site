#!/usr/bin/env python3
"""Separately authorized static-site publication; inspection is read-only."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from rgm_site_tools.static_pages_gateway import StaticPagesGateway
from rgm_site_tools.static_site_release import StaticSiteRelease


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("begin", "inspect", "reconcile"))
    parser.add_argument("--site-root", type=Path, required=True)
    parser.add_argument("--git", type=Path, required=True)
    parser.add_argument("--site-commit", required=True)
    parser.add_argument("--site-base")
    parser.add_argument("--confirm-site")
    arguments = parser.parse_args()
    try:
        if arguments.operation == "inspect":
            if arguments.confirm_site is not None or arguments.site_base is not None:
                raise ValueError("Read-only inspection rejects mutation confirmation and base selection")
        elif arguments.confirm_site != f"site-{arguments.site_commit}":
            raise ValueError(
                "A separate site-publication approval and exact selected-commit confirmation are required"
            )
        if arguments.operation == "begin" and arguments.site_base is None:
            raise ValueError("Begin requires the reviewed remote-main base")
        if arguments.operation == "reconcile" and arguments.site_base is not None:
            raise ValueError("Reconcile must use the retained original site selection")
        route = StaticSiteRelease(
            arguments.site_root,
            arguments.git,
            StaticPagesGateway(os.environ.get("RGM_PAGES_TOKEN", "")),
        )
        result = (
            route.begin(arguments.site_commit, arguments.site_base)
            if arguments.operation == "begin"
            else (
                route.reconcile(arguments.site_commit)
                if arguments.operation == "reconcile"
                else route.inspect(arguments.site_commit)
            )
        )
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Static site operation stopped: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
