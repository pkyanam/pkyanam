#!/usr/bin/env python3
"""Refresh the auto-generated section of README.md from the GitHub API.

Looks for the markers
    <!-- LATEST_REPOS:START -->
    <!-- LATEST_REPOS:END -->
in README.md and replaces what's between them with a freshly-fetched list of
public, non-fork repos sorted by most-recent push.

Runs unauthenticated locally (rate-limited, fine for one user) or with a
GITHUB_TOKEN / GH_TOKEN env var in CI for higher limits.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

USER = "pkyanam"
README = Path("README.md")
START = "<!-- LATEST_REPOS:START -->"
END = "<!-- LATEST_REPOS:END -->"
HOW_MANY = 6  # repos to surface

# Light visual flags so the section reads quickly. Falls back to the raw
# language name for anything not in this map.
LANG_BADGE = {
    "TypeScript": "🟦 TS",
    "JavaScript": "🟨 JS",
    "Python": "🐍 Py",
    "Rust": "🦀 Rust",
    "Swift": "🦅 Swift",
    "C++": "🔧 C++",
    "C": "🔧 C",
    "Go": "🐹 Go",
    "HTML": "🌐 HTML",
    "MDX": "📝 MDX",
    "Makefile": "🛠 Make",
}


def fetch_repos(user: str) -> list[dict]:
    """Fetch every public repo for `user`, paginating defensively."""
    repos: list[dict] = []
    page = 1
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{user}-readme-updater",
    }
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    while True:
        url = (
            f"https://api.github.com/users/{user}/repos"
            f"?per_page=100&page={page}&sort=pushed"
        )
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            batch = json.loads(resp.read())
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


def humanize(iso: str) -> str:
    """`2026-05-04T12:34:56Z` -> `3 days ago`."""
    then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    days = (datetime.now(timezone.utc) - then).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 30:
        return f"{days} days ago"
    if days < 365:
        return f"{days // 30} month{'s' if days >= 60 else ''} ago"
    years = days // 365
    return f"{years} year{'s' if years > 1 else ''} ago"


def render(repos: list[dict]) -> str:
    """Pick the top-N most-recently-pushed repos and render markdown."""
    filtered = [
        r for r in repos
        if not r.get("fork")
        and not r.get("archived")
        and r["name"].lower() != USER.lower()  # skip the profile repo itself
    ]
    filtered.sort(key=lambda r: r["pushed_at"], reverse=True)
    top = filtered[:HOW_MANY]

    out: list[str] = ["", "## 📦 Latest from my GitHub", ""]
    out.append("> Auto-refreshed daily from the GitHub API — what I'm actively pushing to.")
    out.append("")

    for r in top:
        name = r["name"]
        url = r["html_url"]
        desc = (r.get("description") or "_no description yet_").strip()
        lang = r.get("language") or "—"
        lang_label = LANG_BADGE.get(lang, lang)
        stars = r["stargazers_count"]
        when = humanize(r["pushed_at"])
        star_part = f" · ⭐ {stars}" if stars else ""
        homepage = (r.get("homepage") or "").strip()
        live = f" · [live ↗]({homepage})" if homepage.startswith("http") else ""

        out.append(f"### [{name}]({url})")
        out.append(desc)
        out.append("")
        out.append(f"`{lang_label}`{star_part} · pushed {when}{live}")
        out.append("")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out.append(
        f"<sub>Showing {len(top)} of {len(filtered)} public, non-fork repos · "
        f"last updated {today}</sub>"
    )
    out.append("")
    return "\n".join(out)


def update_readme(new_block: str) -> bool:
    text = README.read_text(encoding="utf-8")
    pattern = re.compile(
        re.escape(START) + r".*?" + re.escape(END),
        flags=re.DOTALL,
    )
    if not pattern.search(text):
        sys.exit(f"error: markers {START!r} / {END!r} not found in README.md")

    replacement = f"{START}\n{new_block}\n{END}"
    new_text = pattern.sub(replacement, text)
    if new_text == text:
        return False
    README.write_text(new_text, encoding="utf-8")
    return True


def main() -> None:
    repos = fetch_repos(USER)
    block = render(repos)
    changed = update_readme(block)
    print("README updated." if changed else "No changes.")


if __name__ == "__main__":
    main()
