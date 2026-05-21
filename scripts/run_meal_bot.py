#!/usr/bin/env python3
"""Launch the Telegram Meal Logger Bot.

Listens for food descriptions via Telegram, parses them with the LLM,
and saves structured meal entries to the nutrition storage.

Usage:
    python scripts/run_meal_bot.py

Requires TELEGRAM_BOT_TOKEN in .env (already configured for weekly reports).
"""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path

# Must add project root to sys.path BEFORE any project imports
_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from hevy.env import load_dotenv  # noqa: E402

load_dotenv()


def main() -> None:
    """Start the Telegram meal logger bot."""
    from nutrition.storage import NutritionStorage
    from nutrition.telegram_bot import MealLoggerBot

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token:
        print("❌ TELEGRAM_BOT_TOKEN not set. Add it to your .env file.")
        print("   Get one from https://t.me/BotFather")
        sys.exit(1)

    if not chat_id:
        print("⚠️  No TELEGRAM_CHAT_ID set — bot will respond to ALL chats.")
        print("   Set it in .env to restrict to a single chat.")
        print("   Run: python -c 'from hevy.reporting import setup_telegram; print(setup_telegram(\"YOUR_TOKEN\"))'")
        print()

    storage = NutritionStorage(root=str(_PROJECT_ROOT / "data" / "nutrition"))

    bot = MealLoggerBot(
        storage=storage,
        bot_token=token,
        chat_id=chat_id,
    )

    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, lambda *_: bot.stop())
    signal.signal(signal.SIGTERM, lambda *_: bot.stop())

    bot.run()


if __name__ == "__main__":
    main()
