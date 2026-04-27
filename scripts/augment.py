#!/usr/bin/env python3
"""
augment.py — STUB

Intent: monthly job fetches the hard-ascents lists from climbing-history.org
(and optionally 8a.nu) and surfaces any sends not already in climbers.yaml
as PR-ready proposals.

This is left as a follow-up because writing a robust parser for those pages
is best done after eyeballing the actual HTML / JSON they expose. Once you
have the repo up, drop in a parser here and call it from update.yml.

Suggested behavior (when implemented):
  1. GET each of:
       https://climbing-history.org/list/<id>/hard-sport-climbing-ascents
       https://climbing-history.org/list/<id>/hard-bouldering-ascents
  2. Parse rows into the same `send` schema used in climbers.yaml.
  3. Diff against the YAML — drop anything already present.
  4. Write any new sends to `proposals.yaml`.
  5. (separate Action) open a draft PR with the diff for human review.

Run from repo root:
  python scripts/augment.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROPOSALS = REPO_ROOT / "proposals.yaml"


def main() -> None:
    print("augment.py is a stub — see the docstring for the planned design.")
    print("Nothing was written.")


if __name__ == "__main__":
    main()
