#!/usr/bin/env python3
"""
Build data.json from climbers.yaml + config.yaml.

Scoring (per discipline):
  redpoint_score = sum( top_N hardest qualifying sends, weighted by grade points )
  flash_score    = sum( top_M hardest qualifying flashes, weighted by grade points )
  total_score    = redpoint_score + flash_multiplier * flash_score

Overall leaderboard adds sport_score + boulder_score per climber.

Run from repo root:
  python scripts/build.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
CLIMBERS_PATH = REPO_ROOT / "climbers.yaml"
CONFIG_PATH = REPO_ROOT / "config.yaml"
JSON_PATH = REPO_ROOT / "data.json"


# ---------------------------------------------------------------------
# Grade ordering — for hardest_send / hardest_flash display, and for
# applying the qualifying threshold. Higher index = harder.
# ---------------------------------------------------------------------
SPORT_ORDER = ["7a", "7a+", "7b", "7b+", "7c", "7c+",
               "8a", "8a+", "8b", "8b+", "8c", "8c+",
               "9a", "9a+", "9b", "9b+", "9c", "9c+"]
BOULDER_ORDER = ["V8", "V9", "V10", "V11", "V12", "V13", "V14", "V15",
                 "V16", "V17", "V18", "V19"]
FONT_ORDER    = ["7C", "7C+", "8A", "8A+", "8B", "8B+",
                 "8C", "8C+", "9A", "9A+", "9B"]

# Boulder grade aliases (Font ↔ V).
FONT_TO_V = {
    "7C": "V9", "7C+": "V10", "8A": "V11", "8A+": "V12",
    "8B": "V13", "8B+": "V14", "8C": "V15", "8C+": "V16",
    "9A": "V17", "9A+": "V18", "9B": "V19",
}


def normalize_grade(grade: str, discipline: str) -> str:
    g = grade.strip()
    if discipline == "boulder" and g in FONT_TO_V:
        return FONT_TO_V[g]
    return g


def grade_rank(grade: str, discipline: str) -> int:
    """Numeric ordering. Higher = harder. -1 if unknown."""
    g = normalize_grade(grade, discipline)
    order = BOULDER_ORDER if discipline == "boulder" else SPORT_ORDER
    return order.index(g) if g in order else -1


def is_flash_style(send: dict) -> bool:
    return send.get("style") in ("flash", "onsight")


# ---------------------------------------------------------------------
def load_inputs():
    with open(CLIMBERS_PATH) as f:
        climbers_raw = yaml.safe_load(f)
    with open(CONFIG_PATH) as f:
        cfg_raw = yaml.safe_load(f)
    return climbers_raw, cfg_raw["config"]


def grade_points(grade: str, discipline: str, cfg: dict) -> float:
    table = cfg["sport_points"] if discipline == "sport" else cfg["boulder_points"]
    g = normalize_grade(grade, discipline)
    if g in table:
        return float(table[g])
    # Boulder: try Font alias as a fallback.
    if discipline == "boulder" and grade in table:
        return float(table[grade])
    return 0.0


def meets_threshold(send: dict, cfg: dict) -> tuple[bool, bool]:
    """Return (qualifies_as_redpoint, qualifies_as_flash) for this send."""
    discipline = send["discipline"]
    grade = send["grade"]
    rank = grade_rank(grade, discipline)
    if rank < 0:
        return False, False

    rp_threshold_grade = cfg["thresholds"][f"{discipline}_redpoint"]
    fl_threshold_grade = cfg["thresholds"][f"{discipline}_flash"]
    rp_threshold = grade_rank(rp_threshold_grade, discipline)
    fl_threshold = grade_rank(fl_threshold_grade, discipline)

    qualifies_rp = rank >= rp_threshold
    qualifies_fl = rank >= fl_threshold and is_flash_style(send)
    return qualifies_rp, qualifies_fl


def score_climber_in_discipline(
    sends: list[dict], discipline: str, cfg: dict
) -> dict:
    """Per-discipline score: top-N sends + flash_multiplier * top-M flashes.

    `scoring_sends` is the deduped list of sends that actually contribute
    to the score — top-N redpoints and top-M flashes (a flash that's also
    a top-N redpoint appears once).
    """
    rp_pts: list[tuple[float, dict]] = []
    fl_pts: list[tuple[float, dict]] = []

    for s in sends:
        if s["discipline"] != discipline:
            continue
        qrp, qfl = meets_threshold(s, cfg)
        pts = grade_points(s["grade"], discipline, cfg)
        if qrp:
            rp_pts.append((pts, s))
        if qfl:
            fl_pts.append((pts, s))

    rp_pts.sort(key=lambda x: x[0], reverse=True)
    fl_pts.sort(key=lambda x: x[0], reverse=True)

    top_sends   = rp_pts[: int(cfg["top_n_sends"])]
    top_flashes = fl_pts[: int(cfg["top_n_flashes"])]

    redpoint_score = sum(p for p, _ in top_sends)
    flash_score    = sum(p for p, _ in top_flashes)
    total_score    = redpoint_score + float(cfg["flash_multiplier"]) * flash_score

    hardest_send  = top_sends[0][1] if top_sends else None
    hardest_flash = top_flashes[0][1] if top_flashes else None

    scoring_sends = _dedupe_scoring([top_sends, top_flashes])

    return {
        "score":          round(total_score, 2),
        "redpoint_score": round(redpoint_score, 2),
        "flash_score":    round(flash_score, 2),
        "scoring_send_count":  len(top_sends),
        "scoring_flash_count": len(top_flashes),
        "total_qualifying_sends":   len(rp_pts),
        "total_qualifying_flashes": len(fl_pts),
        "hardest_send":  _summarize(hardest_send),
        "hardest_flash": _summarize(hardest_flash),
        "scoring_sends": scoring_sends,
    }


def _dedupe_scoring(buckets: list[list[tuple[float, dict]]]) -> list[dict]:
    """Flatten (points, send) bucket lists into one list of sends, deduped
    by object identity, sorted hardest-first."""
    seen: set[int] = set()
    rows: list[tuple[int, dict]] = []  # (grade_rank, send)
    for bucket in buckets:
        for _, s in bucket:
            sid = id(s)
            if sid in seen:
                continue
            seen.add(sid)
            rows.append(s)
    rows.sort(
        key=lambda s: (
            -grade_rank(s["grade"], s["discipline"]),
            -(s.get("year") or 0),
        ),
    )
    return rows


def _summarize(s: dict | None) -> dict | None:
    if not s:
        return None
    return {
        "route":      s.get("route", ""),
        "grade":      s.get("grade", ""),
        "year":       s.get("year"),
        "fa":         bool(s.get("fa", False)),
        "style":      s.get("style", "redpoint"),
        "discipline": s["discipline"],
    }


def filter_sends_by_year(sends: list[dict], year_cutoff: int | None) -> list[dict]:
    if year_cutoff is None:
        return sends
    return [s for s in sends if (s.get("year") or 0) >= year_cutoff]


def score_climber_overall(sends: list[dict], cfg: dict) -> dict:
    """Overall scoring: sends pooled across disciplines (top-N), flashes split.

    score = sum(top-10 hardest sends across sport+boulder)
          + flash_multiplier * (sum(top-5 sport flashes) + sum(top-5 boulder flashes))
    """
    rp_pool: list[tuple[float, dict]] = []      # all qualifying sends, mixed
    fl_sport: list[tuple[float, dict]] = []
    fl_boulder: list[tuple[float, dict]] = []

    for s in sends:
        qrp, qfl = meets_threshold(s, cfg)
        pts = grade_points(s["grade"], s["discipline"], cfg)
        if qrp:
            rp_pool.append((pts, s))
        if qfl:
            (fl_sport if s["discipline"] == "sport" else fl_boulder).append((pts, s))

    rp_pool.sort(key=lambda x: x[0], reverse=True)
    fl_sport.sort(key=lambda x: x[0], reverse=True)
    fl_boulder.sort(key=lambda x: x[0], reverse=True)

    n_sends = int(cfg["top_n_sends"])
    n_flashes = int(cfg["top_n_flashes"])
    top_sends = rp_pool[:n_sends]
    top_fl_sport = fl_sport[:n_flashes]
    top_fl_boulder = fl_boulder[:n_flashes]

    redpoint_score = sum(p for p, _ in top_sends)
    flash_score = (
        sum(p for p, _ in top_fl_sport) + sum(p for p, _ in top_fl_boulder)
    )
    total_score = redpoint_score + float(cfg["flash_multiplier"]) * flash_score

    hardest_send  = top_sends[0][1] if top_sends else None
    flash_candidates = [
        top_fl_sport[0][1] if top_fl_sport else None,
        top_fl_boulder[0][1] if top_fl_boulder else None,
    ]
    flash_candidates = [f for f in flash_candidates if f]
    hardest_flash = max(
        flash_candidates,
        key=lambda s: grade_rank(s["grade"], s["discipline"]),
        default=None,
    )

    scoring_sends = _dedupe_scoring([top_sends, top_fl_sport, top_fl_boulder])

    return {
        "score":          round(total_score, 2),
        "redpoint_score": round(redpoint_score, 2),
        "flash_score":    round(flash_score, 2),
        "scoring_send_count":  len(top_sends),
        "scoring_flash_count": len(top_fl_sport) + len(top_fl_boulder),
        "total_qualifying_sends":   len(rp_pool),
        "total_qualifying_flashes": len(fl_sport) + len(fl_boulder),
        "hardest_send":  _summarize(hardest_send),
        "hardest_flash": _summarize(hardest_flash),
        "scoring_sends": scoring_sends,
    }


def build_one_leaderboard(
    climbers: list[dict],
    *,
    discipline: str | None,    # None = overall
    year_cutoff: int | None,
    cfg: dict,
) -> list[dict]:
    rows: list[dict] = []
    for c in climbers:
        sends = filter_sends_by_year(c.get("sends") or [], year_cutoff)
        if not sends:
            continue

        if discipline in ("sport", "boulder"):
            stats = score_climber_in_discipline(sends, discipline, cfg)
        else:
            stats = score_climber_overall(sends, cfg)

        if stats["score"] <= 0:
            continue
        rows.append({
            "name":  c["name"],
            "climbing_history_id": c.get("climbing_history_id"),
            **stats,
        })

    rows.sort(
        key=lambda r: (
            -r["score"],
            -(grade_rank(r["hardest_send"]["grade"], r["hardest_send"]["discipline"])
              if r.get("hardest_send") else -1),
            r["name"].lower(),
        )
    )
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
    return rows


def main() -> None:
    climbers_raw, cfg = load_inputs()
    climbers = climbers_raw.get("climbers", []) or []

    today = dt.date.today()
    current_years = int(cfg.get("current_years", 3))
    current_cutoff = today.year - current_years
    leaderboard_size = int(cfg.get("leaderboard_size", 30))

    leaderboards = {}
    for board_id, discipline in (
        ("sport", "sport"),
        ("boulder", "boulder"),
        ("overall", None),
    ):
        leaderboards[board_id] = {
            "all_time": build_one_leaderboard(
                climbers, discipline=discipline, year_cutoff=None, cfg=cfg,
            )[:leaderboard_size],
            "current": build_one_leaderboard(
                climbers, discipline=discipline, year_cutoff=current_cutoff, cfg=cfg,
            )[:leaderboard_size],
        }

    out = {
        "generated_at": today.isoformat(),
        "source": climbers_raw.get("_source", ""),
        "current_window": {
            "years": current_years,
            "from_year": current_cutoff,
        },
        "thresholds":      cfg["thresholds"],
        "top_n_sends":     cfg["top_n_sends"],
        "top_n_flashes":   cfg["top_n_flashes"],
        "flash_multiplier": cfg["flash_multiplier"],
        "leaderboard_size": leaderboard_size,
        "totals": {
            "climbers": len(climbers),
            "sends": sum(len(c.get("sends") or []) for c in climbers),
        },
        "leaderboards": leaderboards,
    }

    with open(JSON_PATH, "w") as f:
        json.dump(out, f, indent=2, sort_keys=False, ensure_ascii=False)

    print(f"Wrote {JSON_PATH}")
    print(f"  Climbers: {out['totals']['climbers']}")
    print(f"  Sends:    {out['totals']['sends']}")
    print(f"  Current window: {current_cutoff}–{today.year}")


if __name__ == "__main__":
    main()
