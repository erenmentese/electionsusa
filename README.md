# ElectionsUSA — electionsusa.org

Open, transparent polling averages for the 2028 U.S. presidential election, the
2028 primaries, presidential approval and the generic ballot; a pollster
accuracy scorecard; and prediction-market odds next to the polls.

Static site (no server, no database). Python pipeline + Jinja2 templates →
plain HTML/SVG → GitHub Pages (or any static host). Free to run.

## Layout

```
pipeline/
  config.py          races, candidates, dates, site settings  ← edit this first
  schema.py          polls.csv / markets.csv schema + validation
  seed_data.py       hand-entered, sourced starting dataset (python -m pipeline.seed_data)
  fetch_wikipedia.py parse poll tables from Wikipedia compilation pages (MediaWiki API)
  fetch_markets.py   Polymarket + Kalshi public APIs
  run_pipeline.py    network step: fetch + merge into data/*.csv
  average.py         weighted polling average + no-look-ahead trend
  scorecard.py       pollster accuracy from FiveThirtyEight's open archive (+ 2026 cycle)
  charts.py          dependency-free SVG charts
  history.py         presidential results by state 1976-2024 (MIT Election Lab + Census apportionment)
  usmap.py           state map as inline SVG (us-atlas geometry), shaded by margin
  og_cards.py        1200x630 share images, rendered at build time
  build.py           render everything into dist/
site/templates/      Jinja2 pages        site/static/   CSS, JS, favicon
data/polls.csv       long format: one row per poll per candidate (see /data/ page)
data/markets.csv     market snapshots    data/results/2026.csv  (add after Nov 3, 2026)
data/seed/fivethirtyeight/   538 raw-polls + pollster-ratings (CC BY 4.0)
data/seed/medsl/     state presidential returns 1976-2024 (CC0)   data/seed/census/  House apportionment
data/seed/us-atlas/  state outlines, Albers USA (ISC)             each folder has a SOURCE.md
.github/workflows/   fetch every 6h → test → commit data (Vercel deploys) → health check; tests also run on PRs
                     an unhealthy run opens a "data-alert" issue (pipeline/check_data.py), closed once healthy
```

## Run locally

```bash
pip install -r requirements.txt
python -m pipeline.build            # -> dist/
python -m http.server -d dist 8000  # http://localhost:8000
python -m pytest -q tests
python -m pipeline.run_pipeline     # fetch live data (needs internet)
```

## Deploy (GitHub Pages, ~10 minutes)

1. Create a GitHub repo, push this folder to `main`.
2. Settings → Pages → Source: **GitHub Actions**.
3. Settings → Actions → General → Workflow permissions: **Read and write**.
4. Run the workflow once (Actions → "Update data and deploy" → Run workflow).
5. Point DNS for `electionsusa.org`: A records to GitHub Pages IPs
   (185.199.108.153 / .109 / .110 / .111) and a CNAME `www → <user>.github.io`.
   `dist/CNAME` is already generated. Enable "Enforce HTTPS" in Pages settings.

Alternative: Cloudflare Pages with build command `pip install -r requirements.txt && python -m pipeline.build`, output `dist`.

## Before launch checklist

- [ ] `pipeline/config.py` → `SITE`: author name (use a real, named editor; political content ranks poorly anonymously), contact email, `github_repo`, Twitter/Bluesky handle.
- [ ] Verify Polymarket slugs and Kalshi series tickers in `config.MARKETS` against the live sites.
- [ ] Run `python -m pipeline.run_pipeline` once and eyeball `data/polls.csv` — Wikipedia tables change layout; `tests/` covers the parser against a fixture, not the live page.
- [ ] After AdSense approval: set `SITE["adsense_client"]`, replace `dist/ads.txt` content (edit in `build.py`), and add a consent management platform for EEA/UK visitors.
- [ ] Generate `site/static/img/og.png` (1200×630) for social sharing.
- [ ] Review `/privacy/` for your jurisdiction.
- [ ] After Nov 3, 2026: add `data/results/2026.csv` (`race_id,candidate,pct,election_date`) and the 2026 pollster scorecard appears automatically.

## Data licence

Compiled data is published under CC BY 4.0. Poll numbers are facts attributed to
their pollster on every row. Historical accuracy data: FiveThirtyEight (CC BY 4.0).
Wikipedia compilation pages: CC BY-SA 4.0 (used to locate polls; row links point to the pollster's release when cited).

## X (Twitter) bot

Posts new polls, a Monday roundup and countdown milestones from the same data,
each with a 1600×900 share card in the site's style. Code: `pipeline/social_*.py`,
`pipeline/xclient.py`, `pipeline/run_bot.py`; settings: `config.BOT`.

```bash
python -m pipeline.run_bot                # dry run: prints posts, writes cards to out/bot/
python -m pipeline.run_bot --preview-all  # one example of every post type
python -m pipeline.run_bot --bootstrap    # mark all existing polls as already posted
```

What it posts

| Post | When | Example |
|---|---|---|
| New poll | A poll whose fieldwork ended in the last 10 days appears in the data | Results, pollster, dates, sample, and how it moved our average |
| Weekly roundup | Mondays (UTC) | Every average with its 7-day change |
| Countdown | Milestone days (700, 600 … 100 … 1) and the last days before the midterms | Big countdown card |

Limits: at most 2 posts per run and 6 per 24 hours; each item is posted once
(`data/bot_state.json`, committed by the workflow). The first live run marks all
existing polls as seen, so a new account doesn't get a backlog.

Setup

1. Create the X account. In its settings, turn on the **Automated** label
   (Settings → Your account → Account information → Automation) and name yourself as the managing account; X requires this for bots.
2. At console.x.com create a project and app, buy a small amount of pay-per-use credit,
   set app permissions to **Read and write**, then generate the API key/secret and
   the access token/secret **for the bot account** (log in as it, or use the 3-legged flow).
3. In the GitHub repo add secrets `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`,
   `X_ACCESS_TOKEN_SECRET`, and the variable `BOT_ENABLED=true`.
4. Run the workflow manually once and check the log.

Cost: X charges per post; posts containing a URL cost far more, so
`include_links` is off by default. Put the site in the profile bio and on the cards instead.
