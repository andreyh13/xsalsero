#!/usr/bin/env python3
"""
send_daily_figure.py

Picks the next Cuban salsa (casino) figure from a curated list and emails it
to a recipient. Designed to be run once a day by a scheduler (e.g. a GitHub
Actions cron job).

How figure selection works:
    - figures.json holds the curated list, already ordered so that figures
      which depend on an earlier one (e.g. "Sombrero nuevo" needs "Sombrero")
      come later in the list.
    - state.json holds a single number: the id of the last figure we sent.
    - Each run, we send the next id in the list, and loop back to the start
      once we reach the end.

Environment variables required:
    RESEND_API_KEY   - API key for the Resend email service
    TO_EMAIL         - who receives the daily email
    FROM_EMAIL       - verified "from" address in your Resend account

Usage:
    python send_daily_figure.py            # picks next figure, sends email
    python send_daily_figure.py --dry-run  # prints the email, doesn't send it
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
FIGURES_FILE = BASE_DIR / "figures.json"
STATE_FILE = BASE_DIR / "state.json"

RESEND_API_URL = "https://api.resend.com/emails"

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_figures(path: Path) -> list[dict[str, Any]]:
    """Load the curated figure list, sorted by id so ordering is predictable."""
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    figures = data["figures"]
    return sorted(figures, key=lambda fig: fig["id"])


def load_state(path: Path) -> dict[str, Any]:
    """Load which figure we last sent. Defaults to 'nothing sent yet'."""
    if not path.exists():
        return {"last_sent_id": None}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_state(path: Path, state: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


# ---------------------------------------------------------------------------
# Selection logic
# ---------------------------------------------------------------------------

def pick_next_figure(
    figures: list[dict[str, Any]], state: dict[str, Any]
) -> dict[str, Any]:
    """
    Return the figure that comes after the last one we sent.
    Wraps around to the first figure once the list is exhausted.
    """
    last_id = state.get("last_sent_id")

    if last_id is None:
        return figures[0]

    ids = [fig["id"] for fig in figures]
    try:
        last_index = ids.index(last_id)
    except ValueError:
        # last_sent_id no longer exists in figures.json (e.g. list was edited)
        log.warning("Previous figure id %s not found, restarting from the top", last_id)
        return figures[0]

    next_index = (last_index + 1) % len(figures)
    return figures[next_index]


# ---------------------------------------------------------------------------
# Email content
# ---------------------------------------------------------------------------

def build_email_html(figure: dict[str, Any]) -> str:
    """Build a simple HTML email body for one figure."""
    return f"""
    <html>
      <body style="font-family: sans-serif; max-width: 480px; margin: auto;">
        <h2>Today's salsa figure: {figure['name']}</h2>
        <p><strong>Level:</strong> {figure['difficulty'].title()}
           &nbsp;|&nbsp; <strong>Position:</strong> {figure['position'].title()}</p>
        <p>
          <a href="{figure['video_url']}">
            Watch the video lesson
          </a>
        </p>
        {f"<p>{figure['notes']}</p>" if figure.get("notes") else ""}
        <p style="color: #888; font-size: 0.9em;">
          <a href="{figure['page_url']}">More detail on rueda.casino</a>
        </p>
      </body>
    </html>
    """


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------

def send_email(to_email: str, from_email: str, api_key: str, subject: str, html: str) -> None:
    """Send an email via the Resend API. Raises if the request fails."""
    response = requests.post(
        RESEND_API_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "from": from_email,
            "to": [to_email],
            "subject": subject,
            "html": html,
        },
        timeout=10,
    )
    response.raise_for_status()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the email instead of sending it, and don't update state.json",
    )
    args = parser.parse_args()

    figures = load_figures(FIGURES_FILE)
    state = load_state(STATE_FILE)
    figure = pick_next_figure(figures, state)

    subject = f"Salsa figure of the day: {figure['name']}"
    html = build_email_html(figure)

    if args.dry_run:
        log.info("DRY RUN - would send this email:\n%s\n%s", subject, html)
        return

    to_email = os.environ["TO_EMAIL"]
    from_email = os.environ["FROM_EMAIL"]
    api_key = os.environ["RESEND_API_KEY"]

    try:
        send_email(to_email, from_email, api_key, subject, html)
    except requests.RequestException as exc:
        log.error("Failed to send email: %s", exc)
        sys.exit(1)

    state["last_sent_id"] = figure["id"]
    save_state(STATE_FILE, state)
    log.info("Sent figure #%s (%s) to %s", figure["id"], figure["name"], to_email)


if __name__ == "__main__":
    main()
