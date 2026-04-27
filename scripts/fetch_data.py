#!/usr/bin/env python3
"""
Scrape climbing-history.org and write climbers.yaml.

Pulls all confirmed sends/onsights/flashes from canonical curated lists.
Each list page is a static HTML table — we parse rows and aggregate by climber.

Lists (all are ascent lists — sends only, not attempts):
  /list/5   sport redpoints, 9b+
  /list/13  sport redpoints by women, 9a+
  /list/14  boulder redpoints, 8C+
  /list/20  boulder flashes, 8B+
  /list/37  sport onsights, 8c+
  /list/42  sport onsights by women, 8b+
"""
from __future__ import annotations

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

# (path, discipline, default_style, columns)
# columns is the order of <td> after the rank column for each row.
LISTS = [
    ("/list/5/",  "sport",   "redpoint", ["climber", "climb", "grade", "fa", "date"]),
    ("/list/13/", "sport",   "redpoint", ["climber", "climb", "grade", "date"]),
    ("/list/14/", "boulder", "redpoint", ["climber", "climb", "grade", "date"]),
    ("/list/20/", "boulder", "flash",    ["date", "climber", "climb", "grade"]),
    ("/list/37/", "sport",   "onsight",  ["climber", "climb", "grade", "date"]),
    ("/list/42/", "sport",   "onsight",  ["climber", "climb", "grade", "date"]),
]


def fetch(path: str) -> str:
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse_year(date_text: str) -> int | None:
    m = re.search(r"\b(19|20)\d{2}\b", date_text)
    return int(m.group(0)) if m else None


def parse_rows(html: str, columns: list[str]) -> list[dict]:
    """Parse a list page's <tbody> into a list of cell dicts."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="table")
    if not table or not table.tbody:
        return []
    rows = []
    for tr in table.tbody.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        # First td is the rank.
        if len(tds) < len(columns) + 1:
            continue
        cells = tds[1:1 + len(columns)]
        row = {}
        for col_name, td in zip(columns, cells):
            if col_name == "climber":
                a = td.find("a", href=re.compile(r"^/climber/\d+"))
                if not a:
                    break
                m = re.match(r"^/climber/(\d+)", a["href"])
                row["climber_id"] = int(m.group(1))
                row["climber_name"] = a.get_text(strip=True)
            elif col_name == "climb":
                a = td.find("a", href=re.compile(r"^/climb/\d+"))
                if not a:
                    break
                m = re.match(r"^/climb/(\d+)", a["href"])
                row["climb_id"] = int(m.group(1))
                row["climb_name"] = a.get_text(strip=True)
            elif col_name == "grade":
                row["grade"] = td.get_text(strip=True)
            elif col_name == "fa":
                row["fa"] = "✓" in td.get_text()
            elif col_name == "date":
                row["date_text"] = td.get_text(strip=True)
                row["year"] = parse_year(row["date_text"])
        else:
            rows.append(row)
    return rows


def main() -> None:
    # climber_id -> {"name": str, "sends": [send_dict, ...]}
    climbers: dict[int, dict] = defaultdict(lambda: {"name": "", "sends": []})
    # Dedupe key: (climber_id, climb_id, style)
    seen: set[tuple[int, int, str]] = set()

    total_rows = 0
    for path, discipline, default_style, columns in LISTS:
        sys.stderr.write(f"Fetching {path} ...\n")
        html = fetch(path)
        rows = parse_rows(html, columns)
        sys.stderr.write(f"  parsed {len(rows)} rows\n")
        total_rows += len(rows)
        for r in rows:
            cid = r["climber_id"]
            climbers[cid]["name"] = r["climber_name"]
            key = (cid, r["climb_id"], default_style)
            if key in seen:
                continue
            seen.add(key)
            send = {
                "discipline": discipline,
                "route": r["climb_name"],
                "grade": r["grade"],
                "year": r.get("year"),
                "style": default_style,
                "fa": r.get("fa", False),
                "climbing_history_climb_id": r["climb_id"],
            }
            climbers[cid]["sends"].append(send)
        time.sleep(1.0)  # be polite

    # Convert to list, alphabetical by name for stable diffs.
    climber_list = []
    for cid, data in climbers.items():
        sends_sorted = sorted(
            data["sends"],
            key=lambda s: (s.get("year") or 0, s.get("grade") or ""),
            reverse=True,
        )
        climber_list.append({
            "name": data["name"],
            "climbing_history_id": cid,
            "sends": sends_sorted,
        })
    climber_list.sort(key=lambda c: c["name"].lower())

    # Read existing config from a separate file (or seed defaults).
    config_path = REPO_ROOT / "config.yaml"
    if config_path.exists():
        with open(config_path) as f:
            cfg = yaml.safe_load(f) or {}
    else:
        cfg = {}

    out = {
        "_source": "climbing-history.org",
        "_generated_lists": [p for p, *_ in LISTS],
        "config": cfg.get("config", {}),
        "climbers": climber_list,
    }

    with open(YAML_PATH, "w") as f:
        yaml.safe_dump(out, f, sort_keys=False, allow_unicode=True, width=200)

    sys.stderr.write(
        f"\nWrote {YAML_PATH}\n"
        f"  total rows scraped: {total_rows}\n"
        f"  unique climbers:    {len(climber_list)}\n"
        f"  unique sends:       {len(seen)}\n"
    )


if __name__ == "__main__":
    main()
