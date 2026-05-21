"""Telegram meal logger bot.

Listens for food descriptions via Telegram, parses them with the LLM,
and saves structured meal entries. No dashboard needed — just send a message.

Usage:
    Send: "ate 200g chicken and 150g rice for lunch"
    Bot:  "✅ Logged: Lunch — 505 kcal, 66g protein"

Commands:
    /today   — Get today's macro totals
    /week    — Get weekly macro averages
    /help    — Show instructions
    /history — Show recent conversation
    /clear   — Clear conversation history
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx

from hevy.env import load_dotenv
from nutrition.analysis import daily_totals, macro_percentages, period_totals
from nutrition.models import FoodItem, MealEntry
from nutrition.storage import NutritionStorage

load_dotenv()

# ---------------------------------------------------------------------------
# LLM prompt for parsing food descriptions
# ---------------------------------------------------------------------------

FOOD_ESTIMATE_PROMPT = """Estimate nutritional values per 100g for this food item.

Food: {food_name}

Return ONLY valid JSON:
{{
  "energy_kcal_100g": 123,
  "protein_100g": 12.3,
  "carbs_100g": 23.4,
  "fat_100g": 5.6
}}

Base on standard USDA/European food data for this specific item. Keep it realistic."""

FOOD_PARSE_SYSTEM_PROMPT = """You are a food parser. Convert natural language food descriptions into structured JSON data.

Rules:
1. Extract all food items — name only, quantity in grams, and meal type.
2. If quantity is given in units (e.g. "1 apple", "2 eggs"), estimate realistic gram amounts.
3. If no quantity is given, estimate a standard serving size (chicken breast ~200g, rice ~150g cooked, apple ~150g).
4. Classify meal_type as: "breakfast", "lunch", "dinner", "snack".
5. Return ONLY the food names and amounts — do NOT estimate nutritional values (those will be looked up from a real database).
6. Return ONLY valid JSON — no markdown, no explanation, no extra text.

Output format:
{
  "meal_type": "lunch",
  "foods": [
    {"name": "Chicken breast", "amount_g": 200},
    {"name": "White rice cooked", "amount_g": 150}
  ]
}

IMPORTANT: Only output the structure. No nutritional estimates."""

DAILY_SUMMARY_PROMPT = """Here is the user's food log for today.

{day_data}

Give a brief friendly summary of their day's nutrition in 3-4 lines:
- Total calories and macros
- How it compares to their goals
- Any suggestions for the next meal (if applicable)

Keep it concise and encouraging."""


# ---------------------------------------------------------------------------
# Per-chat conversation history
# ---------------------------------------------------------------------------

class ChatHistory:
    """Stores recent interactions per Telegram chat for context.

    Each chat gets a JSON file at ``data/meal_bot_history/{chat_id}.json``.
    Keeps the last 20 messages for LLM context.
    """

    MAX_MESSAGES = 20
    _BASE_DIR = Path(__file__).resolve().parents[1] / "data" / "meal_bot_history"

    @classmethod
    def for_chat(cls, chat_id: int | str) -> ChatHistory:
        """Get (or create) history for a specific chat."""
        inst = cls.__new__(cls)
        inst._chat_id = str(chat_id)
        inst._path = cls._BASE_DIR / f"{inst._chat_id}.json"
        return inst

    def get_messages(self) -> list[dict[str, str]]:
        """Load the conversation history for this chat."""
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text())
            return data.get("messages", [])
        except (json.JSONDecodeError, OSError):
            return []

    def add_message(self, role: str, content: str) -> None:
        """Add a message and persist. Trims to MAX_MESSAGES."""
        messages = self.get_messages()
        messages.append({"role": role, "content": content, "timestamp": datetime.now().isoformat()})
        # Trim to max
        if len(messages) > self.MAX_MESSAGES:
            messages = messages[-self.MAX_MESSAGES:]
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps({"chat_id": self._chat_id, "messages": messages}, indent=2))

    def get_llm_context(self, n_last: int = 6) -> list[dict[str, str]]:
        """Get the last N exchanges for LLM context (excludes timestamps)."""
        messages = self.get_messages()
        recent = messages[-n_last:]
        return [{"role": m["role"], "content": m["content"]} for m in recent]

    def clear(self) -> None:
        """Delete the history file."""
        if self._path.exists():
            self._path.unlink()

    def summary(self) -> str:
        """Get a short summary of recent activity."""
        messages = self.get_messages()
        user_msgs = sum(1 for m in messages if m.get("role") == "user")
        food_entries = sum(1 for m in messages if "kcal" in m.get("content", ""))
        return f"{len(messages)} messages ({user_msgs} from you, ~{food_entries} meals logged)"


# ---------------------------------------------------------------------------
# Telegram Bot
# ---------------------------------------------------------------------------

class MealLoggerBot:
    """Long-polling Telegram bot that logs meals via natural language."""

    def __init__(
        self,
        storage: NutritionStorage,
        bot_token: str | None = None,
        chat_id: str | None = None,
        llm_provider: str = "deepseek",
        poll_interval: float = 2.0,
    ) -> None:
        self._storage = storage
        self._token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self._target_chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
        self._llm_provider_name = llm_provider
        self._poll_interval = poll_interval
        self._offset = 0  # track last processed update ID
        self._running = False
        self._histories: dict[str, ChatHistory] = {}  # cache per-chat history

        if not self._token:
            raise ValueError(
                "Telegram bot token required. Set TELEGRAM_BOT_TOKEN in .env"
            )

    def _get_history(self, chat_id: int) -> ChatHistory:
        """Get or create chat history for a given chat."""
        cid = str(chat_id)
        if cid not in self._histories:
            self._histories[cid] = ChatHistory.for_chat(chat_id)
        return self._histories[cid]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the bot loop. Blocks forever."""
        self._running = True
        print(f"🤖 Meal Logger Bot started (polling every {self._poll_interval}s)")

        # Send startup message
        self._send_message(
            "🤖 *Meal Logger Bot is online!*\n\n"
            "Send me what you eat, like:\n"
            "`ate 200g chicken and rice for lunch`\n\n"
            "Commands:\n"
            "/today — today's totals\n"
            "/week — weekly averages\n"
            "/help — full instructions"
        )

        while self._running:
            try:
                self._poll()
            except KeyboardInterrupt:
                print("\n👋 Bot stopped")
                self._running = False
                break
            except Exception as e:
                print(f"❌ Poll error: {e}")
                time.sleep(5)

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def _poll(self) -> None:
        """Fetch new messages from Telegram."""
        url = f"https://api.telegram.org/bot{self._token}/getUpdates"
        params: dict[str, Any] = {
            "offset": self._offset,
            "timeout": 10,
            "allowed_updates": ["message"],
        }

        try:
            response = httpx.get(url, params=params, timeout=15)
            data = response.json()
        except Exception as e:
            print(f"❌ Telegram poll failed: {e}")
            time.sleep(self._poll_interval)
            return

        if not data.get("ok"):
            print(f"❌ Telegram API error: {data}")
            time.sleep(self._poll_interval)
            return

        for update in data.get("result", []):
            self._offset = update["update_id"] + 1
            message = update.get("message")
            if not message:
                continue

            # Check if this is from our target chat or allow any chat
            chat_id = message.get("chat", {}).get("id")
            text = message.get("text", "").strip()

            if not text:
                continue

            # If a target chat is set, only respond to that chat
            if self._target_chat_id and str(chat_id) != str(self._target_chat_id):
                continue

            self._handle_message(chat_id, text)

        # Sleep between polls
        time.sleep(self._poll_interval)

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    def _handle_message(self, chat_id: int, text: str) -> None:
        """Route an incoming message to the right handler."""
        print(f"💬 Received: {text[:80]}... (chat {chat_id})")

        # Save user message to history
        history = self._get_history(chat_id)
        history.add_message("user", text)

        if text.startswith("/"):
            self._handle_command(chat_id, text)
        else:
            self._handle_food_log(chat_id, text, history)

    def _handle_command(self, chat_id: int, text: str) -> None:
        """Handle slash commands."""
        cmd = text.split()[0].lower()

        if cmd == "/start" or cmd == "/help":
            self._send_message(
                chat_id,
                "🥗 *Meal Logger Bot*\n\n"
                "Just tell me what you ate! Examples:\n\n"
                "`ate 200g chicken breast and rice for lunch`\n"
                "`had 2 eggs and toast for breakfast`\n"
                "`protein shake and banana - snack`\n"
                "`dinner: salmon 150g with broccoli`\n\n"
                "You can also follow up:\n"
                "`make that 300g instead` (corrects last entry)\n"
                "`add an apple too` (adds to last meal)\n\n"
                "Commands:\n"
                "/today — show today's totals\n"
                "/week — weekly averages\n"
                "/history — recent conversation\n"
                "/clear — reset conversation memory\n"
                "/help — this message\n\n"
                "_Tip: include amounts in grams for accuracy!_",
            )

        elif cmd == "/today":
            self._send_daily_summary(chat_id)

        elif cmd == "/week":
            self._send_weekly_summary(chat_id)

        elif cmd == "/history":
            history = self._get_history(chat_id)
            summary = history.summary()
            msgs = history.get_messages()
            lines = [f"📝 *Chat History* — {summary}", ""]
            for m in msgs[-10:]:
                role_icon = "🧑" if m["role"] == "user" else "🤖"
                content = m["content"][:60] + ("..." if len(m["content"]) > 60 else "")
                lines.append(f"{role_icon} {content}")
            if not msgs:
                lines.append("No history yet.")
            self._send_message(chat_id, "\n".join(lines))

        elif cmd == "/clear":
            history = self._get_history(chat_id)
            history.clear()
            self._send_message(chat_id, "🧹 Conversation history cleared!")

        else:
            self._send_message(chat_id, f"❓ Unknown command: {cmd}\nTry /help")

    def _handle_food_log(self, chat_id: int, text: str, history: ChatHistory | None = None) -> None:
        """Parse a food message via LLM and log it."""
        # Tell user we're processing
        self._send_message(chat_id, "🧠 Parsing your meal...")

        # Get recent context from history for the LLM
        context = history.get_llm_context() if history else []

        # Parse (with conversation context for corrections/follow-ups)
        result = self._parse_food_text(text, context)

        if not result or "foods" not in result or not result["foods"]:
            self._send_message(
                chat_id,
                "😅 Sorry, I couldn't understand that. Try:\n"
                "`ate 200g chicken and rice for lunch`\n\n"
                "Or /help for more examples.",
            )
            return

        # Create meal entries
        meal_type = result.get("meal_type", "snack")
        entries: list[MealEntry] = []
        foods_summary: list[str] = []

        for food_data in result["foods"]:
            food = FoodItem(
                barcode="telegram",
                name=food_data.get("name", "Unknown"),
                energy_kcal_100g=food_data.get("energy_kcal_100g", 0),
                protein_100g=food_data.get("protein_100g", 0),
                carbs_100g=food_data.get("carbs_100g", 0),
                fat_100g=food_data.get("fat_100g", 0),
            )
            amount = food_data.get("amount_g", 100)
            entry = MealEntry.create(food=food, amount_g=amount, meal_type=meal_type)
            self._storage.save_entry(entry)
            entries.append(entry)

            # Build summary line
            kcal = entry.energy_kcal
            prot = entry.protein
            foods_summary.append(
                f"{food.name} ({amount}g, {kcal:.0f} kcal, {prot:.1f}g protein)"
            )

        # Calculate total for this meal
        total_kcal = sum(e.energy_kcal for e in entries)
        total_protein = sum(e.protein for e in entries)
        total_carbs = sum(e.carbs for e in entries)
        total_fat = sum(e.fat for e in entries)

        # Build response
        emoji = {"breakfast": "🌅", "lunch": "☀️", "dinner": "🌙", "snack": "🍪"}
        meal_emoji = emoji.get(meal_type, "🍽️")

        response = (
            f"{meal_emoji} *{meal_type.title()} Logged!*\n\n"
            + "\n".join(f"• {s}" for s in foods_summary)
            + f"\n\n*Total*: {total_kcal:.0f} kcal"
            f" | P:{total_protein:.1f}g C:{total_carbs:.1f}g F:{total_fat:.1f}g"
        )

        self._send_message(chat_id, response)

        # Save assistant response to history
        if history:
            history.add_message("assistant", response)

    # ------------------------------------------------------------------
    # LLM parsing
    # ------------------------------------------------------------------

    def _parse_food_text(self, text: str, context: list[dict[str, str]] | None = None) -> dict[str, Any] | None:
        """Parse food description via LLM, then hydrate with real API data.

        Args:
            text: The current message.
            context: Recent conversation history for LLM context.

        Returns:
            Dict with meal_type + foods (each with API-hydrated nutrition), or None.
        """
        # Step 1: LLM extracts food names + amounts
        parsed = self._llm_extract_foods(text, context)
        if not parsed:
            return None

        # Step 2: Look up each food in the Open Food Facts API
        from nutrition.client import OpenFoodFactsClient
        client = OpenFoodFactsClient()
        try:
            for food in parsed.get("foods", []):
                name = food.get("name", "")
                api_data = self._lookup_food(client, name)
                if api_data:
                    food["energy_kcal_100g"] = api_data["energy_kcal_100g"]
                    food["protein_100g"] = api_data["protein_100g"]
                    food["carbs_100g"] = api_data["carbs_100g"]
                    food["fat_100g"] = api_data["fat_100g"]
                    food["name"] = api_data["name"]
                else:
                    estim = self._estimate_food(name)
                    if estim:
                        food["energy_kcal_100g"] = estim.get("energy_kcal_100g", 0)
                        food["protein_100g"] = estim.get("protein_100g", 0)
                        food["carbs_100g"] = estim.get("carbs_100g", 0)
                        food["fat_100g"] = estim.get("fat_100g", 0)
                        print(f"⚠️ Estimated '{name}' from LLM (not in API)")
                    else:
                        food["energy_kcal_100g"] = 0
                        food["protein_100g"] = 0
                        food["carbs_100g"] = 0
                        food["fat_100g"] = 0
            client.close()
        except Exception as e:
            print(f"⚠️ API lookup error: {e}")
            client.close()

        return parsed

    def _llm_extract_foods(self, text: str, context: list[dict[str, str]] | None = None) -> dict[str, Any] | None:
        """Step 1: Use LLM to extract food names and amounts from text.

        Args:
            text: The current message from the user.
            context: Recent conversation history for context (corrections, follow-ups).

        Returns:
            Parsed JSON dict with meal_type and foods list, or None.
        """
        from hevy.llm.providers import LLMProvider

        try:
            messages = list(context or [])
            messages.append({"role": "user", "content": text})

            provider = LLMProvider(provider=self._llm_provider_name, max_tokens=1024)
            response = provider.chat(
                messages=messages,
                system_prompt=FOOD_PARSE_SYSTEM_PROMPT,
            )
            provider.close()

            content = response.content.strip()
            json_str = self._extract_json(content)
            if not json_str:
                return None
            return json.loads(json_str)
        except Exception as e:
            print(f"❌ LLM parse error: {e}")
            return None

    def _estimate_food(self, name: str) -> dict[str, float] | None:
        """Fallback: ask LLM to estimate nutritional values for a specific food.

        Only used when the Open Food Facts API has no match.
        """
        from hevy.llm.providers import LLMProvider

        try:
            provider = LLMProvider(provider=self._llm_provider_name, max_tokens=512)
            prompt = FOOD_ESTIMATE_PROMPT.format(food_name=name)
            response = provider.chat(
                messages=[{"role": "user", "content": prompt}],
            )
            provider.close()

            json_str = self._extract_json(response.content)
            if json_str:
                return json.loads(json_str)
        except Exception as e:
            print(f"⚠️ LLM estimation failed for '{name}': {e}")

        return None

    def _lookup_food(self, client, name: str) -> dict[str, float] | None:
        """Look up a food's nutritional data from the Open Food Facts API.

        Only returns results for packaged/branded products where the API
        has accurate label data. For generic whole foods, returns None
        so the LLM estimation fallback is used instead.
        """
        try:
            search_words = set(w.lower() for w in name.split() if len(w) > 2)
            if not search_words:
                return None

            # Try NL search first, then global
            results = client.search(name, page_size=3)
            if not results:
                results = client.search_all_countries(name, page_size=3)

            for r in results:
                if r.energy_kcal_100g <= 0:
                    continue

                rn_lower = r.name.lower()

                # Stricter matching: the result name should contain the
                # searched name as a contiguous substring (not just individual words)
                name_lower = name.lower()
                if name_lower in rn_lower:
                    return {
                        "name": r.name,
                        "energy_kcal_100g": r.energy_kcal_100g,
                        "protein_100g": r.protein_100g,
                        "carbs_100g": r.carbs_100g,
                        "fat_100g": r.fat_100g,
                    }

                # OR require ALL search words to appear in the result name
                # AND the result name must not have extra "processed food" words
                processed_indicators = {"cookie", "cake", "cracker", "paste", "sauce",
                                        "bar", "chip", "candy", "soup", "sausage",
                                        "nugget", "pudding", "snack", "spread"}
                has_extra_words = processed_indicators & set(rn_lower.split())
                all_match = all(w in rn_lower for w in search_words)

                if all_match and not has_extra_words:
                    return {
                        "name": r.name,
                        "energy_kcal_100g": r.energy_kcal_100g,
                        "protein_100g": r.protein_100g,
                        "carbs_100g": r.carbs_100g,
                        "fat_100g": r.fat_100g,
                    }

        except Exception as e:
            print(f"⚠️ API lookup failed for '{name}': {e}")

        return None

    # ------------------------------------------------------------------
    # Summaries
    # ------------------------------------------------------------------

    def _send_daily_summary(self, chat_id: int) -> None:
        """Send today's macro totals."""
        today_str = date.today().isoformat()
        entries = self._storage.load_day(today_str)

        if not entries:
            self._send_message(chat_id, "🍽️ No meals logged today yet. Send me what you eat!")
            return

        totals = daily_totals(entries)
        macros = macro_percentages(entries)

        # Count by meal type
        by_type: dict[str, int] = {}
        for e in entries:
            by_type[e.meal_type] = by_type.get(e.meal_type, 0) + 1

        meal_counts = " | ".join(f"{k.title()}: {v}" for k, v in sorted(by_type.items()))

        lines = [
            f"📊 *Today's Nutrition ({today_str})*",
            "",
            f"🔥 *{totals['energy_kcal']:.0f} kcal*",
            f"💪 Protein: {totals['protein_g']:.1f}g",
            f"🍚 Carbs:   {totals['carbs_g']:.1f}g",
            f"🧈 Fat:     {totals['fat_g']:.1f}g",
            f"🌾 Fiber:   {totals['fiber_g']:.1f}g",
            "",
            f"*Macro split*: P:{macros['protein_pct']}% / C:{macros['carbs_pct']}% / F:{macros['fat_pct']}%",
            "",
            f"*Meals*: {meal_counts}",
            f"🍽️ {len(entries)} total items",
        ]

        self._send_message(chat_id, "\n".join(lines))

    def _send_weekly_summary(self, chat_id: int) -> None:
        """Send weekly macro averages."""
        from datetime import timedelta

        today = date.today()
        start = today - timedelta(days=7)
        entries_by_day = self._storage.load_range(start.isoformat(), today.isoformat())

        if not entries_by_day:
            self._send_message(chat_id, "📭 No meal data for the past week.")
            return

        df = period_totals(entries_by_day)
        days_logged = len(df)
        avg_cal = df["energy_kcal"].mean()
        avg_protein = df["protein_g"].mean()
        avg_carbs = df["carbs_g"].mean()
        avg_fat = df["fat_g"].mean()

        lines = [
            "📊 *Weekly Averages (last 7 days)*",
            "",
            f"Days logged: {days_logged}/7",
            "",
            f"🔥 Avg *{avg_cal:.0f} kcal*/day",
            f"💪 Avg protein: {avg_protein:.1f}g",
            f"🍚 Avg carbs:   {avg_carbs:.1f}g",
            f"🧈 Avg fat:     {avg_fat:.1f}g",
        ]

        # Calculate totals for the week
        total_cal = df["energy_kcal"].sum()
        total_protein = df["protein_g"].sum()
        lines.append("")
        lines.append(f"*Week total*: {total_cal:.0f} kcal, {total_protein:.1f}g protein")

        self._send_message(chat_id, "\n".join(lines))

    # ------------------------------------------------------------------
    # Telegram API helpers
    # ------------------------------------------------------------------

    def _send_message(self, chat_id: int | None = None, text: str = "") -> bool:
        """Send a message to a Telegram chat."""
        chat_id = chat_id or self._target_chat_id
        if not chat_id:
            return False

        try:
            url = f"https://api.telegram.org/bot{self._token}/sendMessage"
            resp = httpx.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
            return resp.is_success
        except Exception as e:
            print(f"❌ Telegram send failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_json(text: str) -> str | None:
        """Extract a JSON object or array from text, handling markdown fences."""
        # Try JSON code block first
        match = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
        if match:
            return match.group(1)

        # Try raw JSON object
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return match.group(0)

        return None
