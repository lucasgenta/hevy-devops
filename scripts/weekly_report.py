#!/usr/bin/env python3
"""Generate and optionally send the weekly Hevy training report.

Usage:
    # Generate & print to console
    python scripts/weekly_report.py

    # Save HTML report
    python scripts/weekly_report.py --output reports/weekly.html

    # Send via email (requires SMTP config)
    python scripts/weekly_report.py --email

    # Push notification via ntfy
    python scripts/weekly_report.py --ntfy my-topic
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from hevy.env import load_dotenv  # noqa: E402
load_dotenv()


from hevy.transform import (  # noqa: E402
    build_workout_sets_df,
    build_workout_summary_df,
    build_exercise_templates_df,
    build_routines_df,
)
from hevy.anatomy import AnatomyMapper  # noqa: E402
from hevy.reporting import (  # noqa: E402
    generate_report,
    format_html,
    format_markdown,
    send_email,
    send_ntfy,
    send_telegram,
    setup_telegram,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Weekly Hevy training report")
    parser.add_argument("--output", "-o", help="Save HTML report to file")
    parser.add_argument("--email", action="store_true", help="Send report via email")
    parser.add_argument("--ntfy", nargs="?", const="hevy-report", help="Send push notification via ntfy.sh/TOPIC")
    parser.add_argument("--telegram", action="store_true", help="Send report via Telegram")
    parser.add_argument("--telegram-setup", metavar="BOT_TOKEN", nargs="?", const="from_env",
                        help="Get your Telegram chat_id. Send a message to your bot first, then run this.")
    parser.add_argument("--weeks", type=int, default=4, help="Weeks of data to include (default: 4)")
    args = parser.parse_args()

    print("📊 Generating Hevy weekly report...")

    # Load data
    mapper = AnatomyMapper()
    sets_df = build_workout_sets_df(mapper=mapper)
    summary_df = build_workout_summary_df()
    templates_df = build_exercise_templates_df()
    routines_df = build_routines_df()

    goals_path = _PROJECT_ROOT / "goals.json"

    report = generate_report(
        sets_df=sets_df,
        summary_df=summary_df,
        templates_df=templates_df,
        routines_df=routines_df,
        goals_path=goals_path,
        weeks_back=args.weeks,
    )

    # Console output
    print("\n" + format_markdown(report))

    # Save HTML
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(format_html(report))
        print(f"✅ Report saved to {path}")

    # Email
    if args.email:
        send_email(report)

    # Ntfy push
    if args.ntfy:
        send_ntfy(report, topic=args.ntfy)

    # Telegram setup (no report needed)
    if args.telegram_setup:
        token = args.telegram_setup if args.telegram_setup != "from_env" else os.environ.get("TELEGRAM_BOT_TOKEN")  # noqa: F821
        if not token:
            print("❌ Pass the bot token: --telegram-setup YOUR_BOT_TOKEN")
            print("   Or set TELEGRAM_BOT_TOKEN in .env")
            sys.exit(1)
        setup_telegram(token)
        sys.exit(0)

    # Telegram send
    if args.telegram:
        send_telegram(report)

    print("\n✅ Done!")


if __name__ == "__main__":
    main()
