# Climber Tier Chart

A power ranking of the world's hardest outdoor climbers, across **sport**, **bouldering**, and **overall**, with an **All-Time / Current** toggle. Static site, hosted on GitHub Pages, rebuilt monthly by a GitHub Action — no server, no local cron, no computer-on requirement.

## How it ranks

Each leaderboard sorts by the same four-tier criteria, in priority order:

1. **Hardest single send** (highest grade ever climbed)
2. **# of hard sends** (V15+ for boulder, 9a+ for sport)
3. **Hardest flash / onsight**
4. **# of hard flashes / onsights**

Ties are broken alphabetically. The threshold for a "hard send" is configurable in `climbers.yaml`.

For the **Overall** leaderboard, sport and boulder grades are projected onto a unified difficulty index using consensus equivalences (V15 ≈ 9a, V16 ≈ 9a+/9b, V17 ≈ 9b/9b+, V18 ≈ 9b+/9c).

## Repo layout

```
climbers.yaml              # source of truth — edit this
data.json                  # generated; checked in for fast page loads
index.html                 # the site (single file, vanilla JS)
scripts/build.py           # YAML → data.json
scripts/augment.py         # (stub) optional climbing-history.org scraper
.github/workflows/update.yml  # monthly cron
```

## Adding or editing climbers

The whole site is driven by `climbers.yaml`. To log a new send for someone already in the list, find their block and append to `sends:`:

```yaml
- name: Will Bosi
  country: GBR
  gender: M
  sends:
    - { discipline: boulder, route: "Realm of Tor'ment", grade: V17, font_grade: 9A, year: 2025, location: "Raven Tor, UK", fa: true, style: redpoint }
    # add new send here ...
```

To add a new climber, copy any existing block and fill in the fields. Only sends at or above the elite threshold (V15 / 9a+) need to be listed — lower-graded sends are great climbing achievements but won't move someone up a tier list of the world's hardest climbers.

Push to `main`, the `update.yml` workflow runs, regenerates `data.json`, and redeploys Pages. The site is live a couple of minutes later.

## Send schema

Every entry in `sends:` should have:

| Field | Required | Notes |
|---|---|---|
| `discipline` | yes | `boulder` or `sport` |
| `route` | yes | Route / problem name |
| `grade` | yes | `V15`–`V18` for boulder, `9a+`–`9c+` for sport |
| `font_grade` | boulder only | `8C`, `8C+`, `9A`, `9A+` |
| `year` | yes | Used for the Current vs. All-Time split |
| `location` | yes | `"Crag, Country"` |
| `fa` | optional | `true` if first ascent (default `false`) |
| `style` | optional | `redpoint` (default), `flash`, or `onsight` (sport only) |

## Local development

```bash
pip install pyyaml
python scripts/build.py            # regenerates data.json
python -m http.server 8000         # then open http://localhost:8000
```

## Deploying on GitHub

1. Push this repo to GitHub.
2. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
3. Done. The first push triggers `update.yml`, which builds and deploys the site. From then on it rebuilds on every push to `climbers.yaml` and on the **1st of every month** (`cron: "0 6 1 * *"`).

To kick off a manual rebuild: **Actions → Rebuild leaderboard → Run workflow**.

## How "Current" works

`Current` shows climbers ranked using only sends from the last 3 years (configurable via `config.current_years` in `climbers.yaml`). A climber appears in `Current` only if they have at least one qualifying send in that window.

## Future: auto-discovering new sends

`scripts/augment.py` is a stub for an optional [climbing-history.org](https://climbing-history.org) scraper. The intended flow:

1. The monthly Action fetches the hard-ascents lists from climbing-history.org.
2. New sends not yet in `climbers.yaml` are written to a `proposals.yaml` file.
3. A separate Action opens a draft PR with the proposed additions for human review.

This keeps the curation human-in-the-loop while surfacing new ascents automatically. The scraper is left as a follow-up because it requires inspecting the page layout to write a parser — easy to add once you've got the repo running.

## Credits & data sources

The seed dataset was compiled manually from public climbing news (Gripped, PlanetMountain, UKClimbing, climbing-history.org, Wikipedia's *List of grade milestones in rock climbing*). Errors are mine — open an issue or PR.
