#!/usr/bin/env python3
"""
Scrape climbing-history.org and write climbers.yaml.

Two-pass:
  1. Scrape ~6 curated list pages to discover the universe of climbers we
     care about (anyone with a qualifying hard ascent).
  2. For each discovered climber, hit the per-climber ascents API
     (/api/v1/climber/{id}/ascents) which returns full style data —
     including FLASHES, which the public lists don't expose (the public
     "Hard Sport Climbing Onsights" list excludes flashes like Ondra's
     historic 9a+ flash of Super Crackinette).

The API returns one row per ascent with `ascent_style` ("Worked",
"Flash", "Onsight"), `climb_type`, `climb_grade`, `ascent_dt_end`, `fa`,
and `successful` — everything we need.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

try:
    from bs4 import BeautifulSoup
    import yaml
except ImportError as e:
    sys.stderr.write(f"Missing dep: {e}. pip install -r requirements.txt\n")
    sys.exit(1)


REPO_ROOT = Path(__file__).resolve().parent.parent
YAML_PATH = REPO_ROOT / "climbers.yaml"

BASE = "https://climbing-history.org"
UA = "climber-tier-chart/1.0 (+https://github.com/tbhochman/climber-tier-chart)"

# Discovery lists — used only to find climber IDs we care about.
DISCOVERY_LISTS = [
    "/list/5/",   # sport ascents 9b+
    "/list/13/",  # sport ascents 9a+ by women
    "/list/14/",  # boulder ascents 8C+
    "/list/20/",  # boulder flashes 8B+
    "/list/37/",  # sport onsights 8c+
    "/list/42/",  # sport onsights 8b+ by women
]

STYLE_MAP = {
    "Worked":  "redpoint",
    "Flash":   "flash",
    "Onsight": "onsight",
}

# Pre-filter at fetch time: only keep grades that could possibly contribute
# to the leaderboard. Build.py applies stricter thresholds per style.
SPORT_KEEP = {"8c+", "9a", "9a+", "9b", "9b+", "9c", "9c+"}
BOULDER_KEEP = {
    "V14", "V15", "V16", "V17", "V18", "V19",
    "8B+", "8C", "8C+", "9A", "9A+", "9B",
}


def http_get(path: str) -> bytes:
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def discover_climber_ids() -> dict[int, str]:
    """Returns {climber_id: name} for climbers with at least one qualifying
    ascent in any of the discovery lists."""
    found: dict[int, str] = {}
    for path in DISCOVERY_LISTS:
        sys.stderr.write(f"Discovering climbers via {path} ...\n")
        soup = BeautifulSoup(http_get(path), "html.parser")
        for a in soup.select('table.table tbody a[href^="/climber/"]'):
            m = re.match(r"^/climber/(\d+)", a["href"])
            if not m:
                continue
            cid = int(m.group(1))
            if cid not in found:
                found[cid] = a.get_text(strip=True)
        time.sleep(0.5)
    sys.stderr.write(f"  found {len(found)} climbers\n")
    return found


def fetch_climber_ascents(climber_id: int) -> list[dict]:
    """Return the list of ascents from /api/v1/climber/{id}/ascents."""
    raw = http_get(f"/api/v1/climber/{climber_id}/ascents")
    data = json.loads(raw)
    return data.get("ascents", []) or []


def normalize_ascent(a: dict) -> dict | None:
    """Project a raw ascent record into our send schema. Returns None if
    the ascent should be dropped (project, unsuccessful, wrong type, etc.)."""
    if not a.get("successful"):
        return None
    if a.get("project"):
        return None
    if a.get("deleted_on"):
        return None
    climb_type = a.get("climb_type")
    if climb_type == "Sport route":
        discipline = "sport"
    elif climb_type == "Boulder problem":
        discipline = "boulder"
    else:
        return None
    style = STYLE_MAP.get(a.get("ascent_style"))
    if not style:
        return None
    grade = (a.get("climb_grade") or "").strip()
    if not grade:
        return None
    if discipline == "sport" and grade not in SPORT_KEEP:
        return None
    if discipline == "boulder" and grade not in BOULDER_KEEP:
        return None
    # ascent_dt_end is ISO yyyy-mm-dd, the latest possible date
    year = None
    end = a.get("ascent_dt_end")
    if end:
        m = re.match(r"^(\d{4})", end)
        if m:
            year = int(m.group(1))
    return {
        "discipline": discipline,
        "route": a.get("climb_name") or "?",
        "grade": grade,
        "year":  year,
        "style": style,
        "fa":    bool(a.get("fa", False)),
        "climbing_history_climb_id": a.get("climb_id"),
    }


def main() -> None:
    climber_ids = discover_climber_ids()

    climbers: list[dict] = []
    sys.stderr.write("\nFetching ascents per climber via API ...\n")
    for i, (cid, name) in enumerate(sorted(climber_ids.items()), 1):
        try:
            ascents = fetch_climber_ascents(cid)
        except Exception as e:
            sys.stderr.write(f"  [{i}/{len(climber_ids)}] {name} ({cid}): {e}\n")
            time.sleep(1.0)
            continue
        sends: list[dict] = []
        for a in ascents:
            s = normalize_ascent(a)
            if s:
                sends.append(s)
        # Sort newest-first / hardest-first for stable diffs.
        sends.sort(
            key=lambda s: (s.get("year") or 0, s.get("grade") or ""),
            reverse=True,
        )
        if sends:
            climbers.append({
                "name": name,
                "climbing_history_id": cid,
                "sends": sends,
            })
        if i % 10 == 0:
            sys.stderr.write(f"  [{i}/{len(climber_ids)}] {name}: {len(sends)} sends\n")
        time.sleep(0.4)

    climbers.sort(key=lambda c: c["name"].lower())

    config_path = REPO_ROOT / "config.yaml"
    cfg = {}
    if config_path.exists():
        with open(config_path) as f:
            cfg = (yaml.safe_load(f) or {}).get("config", {})

    out = {
        "_source": "climbing-history.org (per-climber ascents API)",
        "_discovery_lists": DISCOVERY_LISTS,
        "config": cfg,
        "climbers": climbers,
    }

    with open(YAML_PATH, "w") as f:
        yaml.safe_dump(out, f, sort_keys=False, allow_unicode=True, width=200)

    total_sends = sum(len(c["sends"]) for c in climbers)
    sys.stderr.write(
        f"\nWrote {YAML_PATH}\n"
        f"  climbers: {len(climbers)}\n"
        f"  sends:    {total_sends}\n"
    )


if __name__ == "__main__":
    main()
