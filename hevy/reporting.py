"""Weekly training report — combines stats, overload suggestions, deload alerts, swaps, and goals."""

from __future__ import annotations

import os
import smtplib
import subprocess
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import pandas as pd

from hevy.analysis import (
    muscle_group_balance,
    best_set_by_exercise,
    weekly_volume_trend,
    workouts_over_time,
)
from hevy.predictor import suggest_all_exercises
from hevy.deload import deload_score
from hevy.goals import GoalTracker
from hevy.swaps import suggest_swaps, suggest_head_swaps


def generate_report(
    sets_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    templates_df: pd.DataFrame,
    routines_df: pd.DataFrame | None = None,
    goals_path: str | Path | None = None,
    weeks_back: int = 4,
) -> dict[str, Any]:
    """Generate a complete weekly training report.

    Returns a dict with all sections for flexible formatting.
    """
    # Filter to recent data
    cutoff = datetime.now().astimezone() - timedelta(weeks=weeks_back)
    recent_sets = sets_df[pd.to_datetime(sets_df["start_time"]) >= cutoff].copy()
    recent_summary = summary_df[pd.to_datetime(summary_df["start_time"]) >= cutoff].copy()

    report: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(),
        "period": f"Last {weeks_back} weeks",
        "stats": _build_weekly_stats(recent_summary, recent_sets),
        "deload": deload_score(summary_df, sets_df),
        "predictions": suggest_all_exercises(recent_sets, routines_df, min_sets=2)[:8],
        "swaps": suggest_swaps(sets_df, templates_df, routines_df, n_suggestions=4),
        "workout_frequency": _build_frequency_chart(recent_summary),
    }

    # Goals
    if goals_path:
        tracker = GoalTracker(sets_df, goals_path=goals_path)
        goals = tracker.list_goals()
        report["goals"] = [{
            "exercise": g.exercise,
            "current": g.current_e1rm,
            "target": g.target_weight_kg,
            "projected": g.projected_date,
            "on_track": g.on_track,
        } for g in goals if g.current_e1rm > 0]

    return report


def format_html(report: dict[str, Any]) -> str:
    """Format the report as a nice HTML email."""
    s = report["stats"]

    # Build sections
    sections = [
        _html_header(),
        _html_section("📊 Weekly Stats", _html_stats(s)),
    ]

    # Deload
    d = report["deload"]
    deload_color = "#e74c3c" if d["needs_deload"] else "#2ecc71"
    sections.append(_html_section(
        "⚠️ Fatigue & Deload", 
        f'<p style="color:{deload_color};font-size:18px;font-weight:bold;">'
        f'Score: {d["score"]:.0f}/100</p>'
        f'<p>{d["recommendation"]}</p>'
    ))

    # Overload predictions
    if report["predictions"]:
        pred_html = '<table style="width:100%;border-collapse:collapse;">'
        pred_html += '<tr style="background:#f0f2f6;"><th>Exercise</th><th>Suggested</th><th>Last</th><th>Note</th></tr>'
        for p in report["predictions"]:
            suggested = f'{p["suggested_weight_kg"]}kg × {p["suggested_reps"]}' if p["suggested_weight_kg"] else "—"
            last = f'{p["last_weight_kg"]}kg × {p["last_reps"]}' if p["last_weight_kg"] else "—"
            pred_html += f'<tr><td>{p["exercise"]}</td><td><strong>{suggested}</strong></td><td>{last}</td><td>{p["reasoning"]}</td></tr>'
        pred_html += '</table>'
        sections.append(_html_section("🏋️ Next Session Targets", pred_html))

    # Swaps
    if report["swaps"]:
        swap_html = "<ul>"
        for sw in report["swaps"]:
            swap_html += f'<li><strong>{sw["under_targeted"]}</strong> ({sw["volume_percentage"]}% of volume): '
            swap_html += f'Try {", ".join(sw["suggested_exercises"][:2])}</li>'
        swap_html += "</ul>"
        sections.append(_html_section("🔄 Exercise Swap Suggestions", swap_html))

    # Goals
    if report.get("goals"):
        goals_html = "<ul>"
        for g in report["goals"]:
            status = "✅" if g["on_track"] else "⚠️"
            goals_html += f'<li>{status} <strong>{g["exercise"]}</strong>: '
            goals_html += f'{g["current"]}kg / {g["target"]}kg'
            if g["projected"]:
                goals_html += f' (projected: {g["projected"]})'
            goals_html += "</li>"
        goals_html += "</ul>"
        sections.append(_html_section("🎯 Goal Progress", goals_html))

    sections.append(_html_footer())
    return "<html><body>" + "".join(sections) + "</body></html>"


def format_markdown(report: dict[str, Any]) -> str:
    """Format the report as plain markdown (for console)."""
    s = report["stats"]
    lines = [
        f"# 📊 Weekly Training Report",
        f"**{report['period']}** — Generated {report['generated_at'][:10]}",
        "",
        "## 📊 Stats",
        f"- Workouts: {s['workouts']}",
        f"- Total Sets: {s['total_sets']}",
        f"- Volume: {s['total_volume']:,} kg",
        f"- Avg Duration: {s['avg_duration']}",
        "",
    ]

    # Deload
    d = report["deload"]
    icon = "⚠️" if d["needs_deload"] else "✅"
    lines.append(f"## {icon} Fatigue Score: {d['score']:.0f}/100")
    lines.append(d["recommendation"])
    lines.append("")

    # Predictions
    if report["predictions"]:
        lines.append("## 🏋️ Next Session Targets")
        for p in report["predictions"]:
            suggested = f'{p["suggested_weight_kg"]}kg × {p["suggested_reps"]}' if p["suggested_weight_kg"] else "—"
            lines.append(f"- **{p['exercise']}**: → {suggested}")
            lines.append(f"  *{p['reasoning']}*")
        lines.append("")

    # Swaps
    if report["swaps"]:
        lines.append("## 🔄 Exercise Swaps")
        for sw in report["swaps"]:
            lines.append(f"- **{sw['under_targeted']}** ({sw['volume_percentage']}%): "
                        f"{', '.join(sw['suggested_exercises'][:2])}")
        lines.append("")

    return "\n".join(lines)


def send_email(
    report: dict[str, Any],
    smtp_server: str | None = None,
    smtp_port: int = 587,
    smtp_user: str | None = None,
    smtp_pass: str | None = None,
    to: str | None = None,
) -> bool:
    """Send the report via SMTP email.

    Falls back to printing instructions if SMTP isn't configured.
    """
    smtp_server = smtp_server or os.environ.get("SMTP_SERVER")
    smtp_user = smtp_user or os.environ.get("SMTP_USER")
    smtp_pass = smtp_pass or os.environ.get("SMTP_PASS")
    to = to or os.environ.get("SMTP_TO")

    if not all([smtp_server, smtp_user, smtp_pass, to]):
        print("📧 SMTP not configured. Report saved to reports/weekly_report.html")
        print("   To enable email, set: SMTP_SERVER, SMTP_USER, SMTP_PASS, SMTP_TO")
        return False

    html = format_html(report)
    msg = MIMEText(html, "html")
    msg["Subject"] = f"📊 Hevy Weekly Report — {datetime.now().strftime('%b %d, %Y')}"
    msg["From"] = smtp_user
    msg["To"] = to

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        print(f"✅ Report emailed to {to}")
        return True
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        return False


def send_telegram(
    report: dict[str, Any],
    bot_token: str | None = None,
    chat_id: str | None = None,
) -> bool:
    """Send the weekly report as a Telegram message.

    Configure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env or pass directly.
    """
    bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("📱 Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
        return False

    s = report["stats"]
    d = report["deload"]
    deload_icon = "⚠️" if d["needs_deload"] else "✅"

    lines = [
        f"📊 Hevy Weekly Report",
        f"",
        f"📅 Stats",
        f"Workouts: {s['workouts']}",
        f"Sets: {s['total_sets']}",
        f"Volume: {s['total_volume']:,.0f} kg",
        f"Avg duration: {s.get('avg_duration', '—')}",
        f"",
        f"{deload_icon} Fatigue: {d['score']:.0f}/100",
    ]

    # Top 5 predictions
    if report["predictions"]:
        lines.append(f"")
        lines.append(f"🏋️ Next Session")
        for p in report["predictions"][:5]:
            if p["suggested_weight_kg"]:
                lines.append(f"• {p['exercise']}: {p['suggested_weight_kg']}kg × {p['suggested_reps']}")

    # Swaps
    if report["swaps"]:
        lines.append(f"")
        lines.append(f"🔄 Try Adding")
        for sw in report["swaps"][:3]:
            lines.append(f"• {sw['suggested_exercises'][0]} (for {sw['under_targeted']})")

    # Goals
    if report.get("goals"):
        lines.append(f"")
        lines.append(f"🎯 Goals")
        for g in report["goals"]:
            icon = "✅" if g["on_track"] else "⚠️"
            lines.append(f"{icon} {g['exercise']}: {g['current']}kg / {g['target']}kg")

    text = "\n".join(lines)

    try:
        import httpx
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        resp = httpx.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        })
        if resp.is_success:
            print(f"✅ Report sent to Telegram chat {chat_id}")
            return True
        else:
            print(f"❌ Telegram error: {resp.text}")
            return False
    except Exception as e:
        print(f"❌ Telegram send failed: {e}")
        return False


def setup_telegram(bot_token: str) -> str | None:
    """Get the latest chat_id from a bot's updates.

    Run this after sending at least one message to your bot on Telegram.
    Returns the chat_id string, or None if no messages found.
    """
    import httpx
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        resp = httpx.get(url, timeout=10)
        data = resp.json()
        if not data.get("ok") or not data.get("result"):
            print("❌ No Telegram updates found. Send a message to your bot first, then try again.")
            return None

        # Get the most recent chat
        latest = data["result"][-1]
        chat = latest.get("message", {}).get("chat", {})
        chat_id = chat.get("id")

        if chat_id:
            print(f"✅ Found chat: {chat.get('title', chat.get('first_name', 'Unknown'))} (ID: {chat_id})")
            print(f"   Add this to your .env file:")
            print(f'   TELEGRAM_CHAT_ID={chat_id}')
            return str(chat_id)
        else:
            print("❌ Could not extract chat_id from updates.")
            return None
    except Exception as e:
        print(f"❌ Telegram setup failed: {e}")
        return None


def send_ntfy(report: dict[str, Any], topic: str | None = None) -> bool:
    """Send the report as a push notification via ntfy.sh."""
    topic = topic or os.environ.get("NTFY_TOPIC")
    if not topic:
        return False

    d = report["deload"]
    lines = [
        f"📊 Hevy Weekly Report",
        f"Workouts: {report['stats']['workouts']}",
        f"Volume: {report['stats']['total_volume']:,} kg",
        f"Fatigue: {d['score']:.0f}/100 {'⚠️' if d['needs_deload'] else '✅'}",
    ]
    if report["predictions"]:
        lines.append(f"Next targets: {len(report['predictions'])} exercises")

    try:
        subprocess.run([
            "curl", "-s", "-d", "\n".join(lines),
            f"ntfy.sh/{topic}",
        ], capture_output=True)
        return True
    except Exception:
        return False


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _build_weekly_stats(summary_df: pd.DataFrame, sets_df: pd.DataFrame) -> dict[str, Any]:
    stats = {
        "workouts": len(summary_df),
        "total_sets": len(sets_df),
        "total_volume": round(sets_df["volume_kg"].sum(), 0) if not sets_df.empty else 0,
    }
    if not summary_df.empty:
        stats["avg_duration"] = f"{summary_df['duration_min'].mean():.0f} min"
    else:
        stats["avg_duration"] = "—"

    return stats


def _build_frequency_chart(summary_df: pd.DataFrame) -> list[dict[str, Any]]:
    wf = workouts_over_time(summary_df, period="W")
    if wf.empty:
        return []
    return wf.tail(8).to_dict(orient="records")


def _html_header() -> str:
    return f"""
    <div style="background:linear-gradient(135deg,#667eea,#764ba2);padding:30px;border-radius:12px;margin-bottom:20px;">
      <h1 style="color:white;margin:0;">📊 Hevy Weekly Report</h1>
      <p style="color:rgba(255,255,255,0.8);margin:5px 0 0;">{datetime.now().strftime('%B %d, %Y')}</p>
    </div>"""


def _html_section(title: str, body: str) -> str:
    return f"""
    <div style="background:white;border-radius:10px;padding:20px;margin-bottom:16px;box-shadow:0 2px 8px rgba(0,0,0,0.06);">
      <h2 style="margin:0 0 12px 0;font-size:20px;">{title}</h2>
      {body}
    </div>"""


def _html_stats(s: dict[str, Any]) -> str:
    items = [
        ("Workouts", s["workouts"]),
        ("Total Sets", s["total_sets"]),
        ("Total Volume", f'{s["total_volume"]:,} kg'),
        ("Avg Duration", s.get("avg_duration", "—")),
    ]
    html = '<div style="display:flex;gap:16px;flex-wrap:wrap;">'
    for label, value in items:
        html += f"""
        <div style="background:#f8f9fa;padding:16px;border-radius:8px;flex:1;min-width:120px;text-align:center;">
          <div style="font-size:24px;font-weight:bold;color:#333;">{value}</div>
          <div style="font-size:13px;color:#666;">{label}</div>
        </div>"""
    html += "</div>"
    return html


def _html_footer() -> str:
    return f"""
    <div style="text-align:center;padding:20px;color:#999;font-size:12px;">
      Generated by <a href="https://github.com/lucas/hevy-scraper" style="color:#667eea;">Hevy Scraper</a>
      — {datetime.now().strftime('%Y-%m-%d %H:%M')}
    </div>"""
