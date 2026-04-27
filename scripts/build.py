#!/usr/bin/env python3
"""
Build data.json from climbers.yaml.

Produces a JSON file consumed by index.html that contains:
  - Sport leaderboard (all-time + current)
  - Boulder leaderboard (all-time + current)
  - Overall leaderboard (all-time + current)

Ranking criteria (in order, applied per leaderboard):
  1. Highest single-send difficulty
  2. Number of "hard" sends (V15+/9a+)
  3. Highest single-flash difficulty (flash or onsight)
  4. Number of "hard" flashes

Run from repo root:
  python scripts/build.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write(
        "PyYAML is required. Install with: pip install pyyaml\n"
    )
    sys.exit(1)


REPO_ROOT = Path(__file__).resolve().parent.parent
YAML_PATH = REPO_ROOT / "climbers.yaml"
JSON_PATH = REPO_ROOT / "data.json"


# ---------------------------------------------------------------------
# Grade scales — unified numeric "difficulty index" so we can rank
# across disciplines for the Overall leaderboard.
#
# Anchor points (consensus equivalence used by 8a / climbing-history):
#   V15 / 8C     ~  9a
#   V16 / 8C+    ~  9a+ / 9b
#   V17 / 9A     ~  9b / 9b+
#   V18 / 9A+    ~  9b+ / 9c
# ---------------------------------------------------------------------
BOULDER_INDEX = {
    "V15": 15.0, "8C":   15.0,
    "V16": 16.0, "8C+":  16.0,
    "V17": 17.0, "9A":   17.0,
    "V18": 18.0, "9A+":  18.0,
}
SPORT_INDEX = {
    "9a":   15.0,
    "9a+":  16.0,
    "9b":   17.0,
    "9b+":  18.0,
    "9c":   19.0,
    "9c+":  20.0,
}

GRADE_DISPLAY_BOULDER = {15: "V15", 16: "V16", 17: "V17", 18: "V18"}
GRADE_DISPLAY_SPORT = {15: "9a", 16: "9a+", 17: "9b", 18: "9b+", 19: "9c", 20: "9c+"}


def grade_index(send: dict) -> float:
    """Return the unified difficulty index for a send."""
    g = str(send.get("grade", "")).strip()
    if send["discipline"] == "boulder":
        return BOULDER_INDEX.get(g, BOULDER_INDEX.get(send.get("font_grade", ""), 0.0))
    return SPORT_INDEX.get(g, 0.0)


def is_flash(send: dict) -> bool:
    return send.get("style") in ("flash", "onsight")


def grade_label(idx: float, discipline: str) -> str:
    """Pretty grade label from index, e.g. 17.0 boulder -> 'V17'."""
    if idx <= 0:
        return "—"
    i = int(round(idx))
    if discipline == "boulder":
        return GRADE_DISPLAY_BOULDER.get(i, f"V{i}")
    return GRADE_DISPLAY_SPORT.get(i, "?")


def hard_threshold(discipline: str, threshold_cfg: dict) -> float:
    """Convert threshold config (V15 / 9a+) to a numeric index."""
    if discipline == "boulder":
        return BOULDER_INDEX.get(threshold_cfg["boulder"], 15.0)
    return SPORT_INDEX.get(threshold_cfg["sport"], 16.0)


# ---------------------------------------------------------------------
# Per-climber stats for one (discipline-set, scope) combination.
# ---------------------------------------------------------------------
def compute_stats(
    climber: dict,
    *,
    disciplines: set[str],         # e.g. {"sport"} or {"sport","boulder"}
    year_cutoff: int | None,        # inclusive; None = all-time
    threshold_cfg: dict,
) -> dict | None:
    """Aggregate stats for a single climber and the requested filter.

    Returns None if the climber has zero qualifying sends in scope.
    """
    sends = []
    for s in climber.get("sends", []):
        if s["discipline"] not in disciplines:
            continue
        if year_cutoff is not None and int(s.get("year", 0)) < year_cutoff:
            continue
        sends.append(s)

    if not sends:
        return None

    # Compute the four ranking metrics.
    hardest_send = max(sends, key=grade_index)
    hardest_send_idx = grade_index(hardest_send)

    flashes = [s for s in sends if is_flash(s)]
    if flashes:
        hardest_flash = max(flashes, key=grade_index)
        hardest_flash_idx = grade_index(hardest_flash)
    else:
        hardest_flash = None
        hardest_flash_idx = 0.0

    # "Hard" = at or above threshold for the discipline.
    def is_hard(s: dict) -> bool:
        return grade_index(s) >= hard_threshold(s["discipline"], threshold_cfg)

    hard_sends = [s for s in sends if is_hard(s)]
    hard_flashes = [s for s in flashes if is_hard(s)]

    # Display strings for the table.
    def display(s: dict) -> str:
        if not s:
            return "—"
        grade = s.get("grade", "")
        return f"{s.get('route','?')} ({grade})"

    return {
        "name": climber["name"],
        "country": climber.get("country", ""),
        "gender": climber.get("gender", ""),
        # Sort keys
        "hardest_send_idx": round(hardest_send_idx, 3),
        "hard_send_count": len(hard_sends),
        "hardest_flash_idx": round(hardest_flash_idx, 3),
        "hard_flash_count": len(hard_flashes),
        # Display fields
        "hardest_send": {
            "route": hardest_send.get("route", ""),
            "grade": hardest_send.get("grade", ""),
            "year": hardest_send.get("year", ""),
            "fa": bool(hardest_send.get("fa", False)),
            "discipline": hardest_send["discipline"],
        },
        "hardest_flash": (
            {
                "route": hardest_flash.get("route", ""),
                "grade": hardest_flash.get("grade", ""),
                "year": hardest_flash.get("year", ""),
                "style": hardest_flash.get("style", ""),
                "discipline": hardest_flash["discipline"],
            }
            if hardest_flash
            else None
        ),
        # Full qualifying sends so the row can expand to show details.
        "sends": sends,
    }


def rank_leaderboard(rows: list[dict]) -> list[dict]:
    """Sort rows using the 4-tier criteria and assign ranks."""
    rows.sort(
        key=lambda r: (
            -r["hardest_send_idx"],
            -r["hard_send_count"],
            -r["hardest_flash_idx"],
            -r["hard_flash_count"],
            r["name"].lower(),  # final stable tiebreak
        )
    )
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
    return rows


def build_leaderboard(
    climbers: list[dict],
    *,
    disciplines: set[str],
    year_cutoff: int | None,
    threshold_cfg: dict,
    size: int,
) -> list[dict]:
    rows: list[dict] = []
    for c in climbers:
        stats = compute_stats(
            c,
            disciplines=disciplines,
            year_cutoff=year_cutoff,
            threshold_cfg=threshold_cfg,
        )
        if stats:
            rows.append(stats)
    rank_leaderboard(rows)
    return rows[:size]


def main() -> None:
    if not YAML_PATH.exists():
        sys.stderr.write(f"climbers.yaml not found at {YAML_PATH}\n")
        sys.exit(1)

    with open(YAML_PATH) as f:
        raw = yaml.safe_load(f)

    cfg = raw.get("config", {}) or {}
    threshold_cfg = cfg.get("hard_threshold", {}) or {}
    threshold_cfg.setdefault("boulder", "V15")
    threshold_cfg.setdefault("sport", "9a+")
    leaderboard_size = int(cfg.get("leaderboard_size", 30))
    current_years = int(cfg.get("current_years", 3))

    climbers = raw.get("climbers", []) or []

    # Validate: every send needs at least a discipline + grade + year.
    for c in climbers:
        for s in c.get("sends", []):
            if "discipline" not in s or "grade" not in s:
                sys.stderr.write(
                    f"Bad send for {c.get('name')}: {s}\n"
                )

    today = dt.date.today()
    # "last N years" = sends from (current_year - N) onward, inclusive.
    # In April 2026 with N=3 this gives 2023+, ~3 years of elapsed time.
    current_cutoff = today.year - current_years

    leaderboards = {}
    for board_id, disciplines in (
        ("sport", {"sport"}),
        ("boulder", {"boulder"}),
        ("overall", {"sport", "boulder"}),
    ):
        leaderboards[board_id] = {
            "all_time": build_leaderboard(
                climbers,
                disciplines=disciplines,
                year_cutoff=None,
                threshold_cfg=threshold_cfg,
                size=leaderboard_size,
            ),
            "current": build_leaderboard(
                climbers,
                disciplines=disciplines,
                year_cutoff=current_cutoff,
                threshold_cfg=threshold_cfg,
                size=leaderboard_size,
            ),
        }

    out = {
        "generated_at": today.isoformat(),
        "current_window": {
            "years": current_years,
            "from_year": current_cutoff,
        },
        "thresholds": {
            "boulder": threshold_cfg["boulder"],
            "sport": threshold_cfg["sport"],
        },
        "leaderboard_size": leaderboard_size,
        "totals": {
            "climbers": len(climbers),
            "sends": sum(len(c.get("sends", []) or []) for c in climbers),
        },
        "leaderboards": leaderboards,
    }

    with open(JSON_PATH, "w") as f:
        json.dump(out, f, indent=2, sort_keys=False)

    print(f"Wrote {JSON_PATH}")
    print(f"  Climbers: {out['totals']['climbers']}")
    print(f"  Sends:    {out['totals']['sends']}")
    print(f"  Current window: {current_cutoff}–{today.year}")


if __name__ == "__main__":
    main()
