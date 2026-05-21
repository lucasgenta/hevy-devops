#!/usr/bin/env python3
"""CLI entry point for the Hevy scraper.

Usage:
    python scripts/scrape.py [--api-key KEY] [--output-dir PATH]

The API key can also be set via the HEVY_API_KEY environment variable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure the project root is on sys.path so `hevy` is importable
_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from hevy.env import load_dotenv  # noqa: E402
load_dotenv()

from hevy import HevyClient, HevyScraper, JsonStorage  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape all data from the Hevy API into local JSON files.",
    )
    parser.add_argument(
        "--api-key",
        help="Hevy API key (default: $HEVY_API_KEY)",
        default=None,
    )
    parser.add_argument(
        "--output-dir",
        help="Directory to write scraped data (default: data/raw)",
        default="data/raw",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Seconds to wait between pagination requests (default: 0.5)",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("HEVY_API_KEY")
    if not api_key:
        parser.error(
            "API key is required. Pass --api-key or set the HEVY_API_KEY environment variable."
        )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    client = HevyClient(api_key)
    storage = JsonStorage(root=output_dir)
    scraper = HevyScraper(client=client, storage=storage)

    print(f"Scraping Hevy API -> {output_dir.resolve()}")
    print(f"Delay: {args.delay}s between pagination requests\n")

    summary = scraper.scrape_all(delay=args.delay)

    print("\n=== Scrape Complete ===")
    print(json.dumps(
        {k: v for k, v in summary.items() if k != "files"},
        indent=2,
    ))

    total_files = sum(
        len(v) if isinstance(v, list) else 1
        for v in summary.values()
        if isinstance(v, (list, dict))
    )
    print(f"\nTotal files written: ~{total_files}")

    client.close()


if __name__ == "__main__":
    main()
