# Builds the site into dist/. Run by the GitHub workflow before it deploys to Cloudflare Pages
# (and by Vercel through vercel-build.sh). PYTHON picks the interpreter; otherwise the newest python3.x on PATH.
set -e
PY=${PYTHON:-}
if [ -z "$PY" ]; then
  for v in python3.13 python3.12 python3.11 python3; do if command -v $v >/dev/null 2>&1; then PY=$v; break; fi; done
fi
$PY -m pip install --quiet --break-system-packages -r requirements.txt || $PY -m pip install --quiet -r requirements.txt
mkdir -p data/seed/fivethirtyeight
B=https://raw.githubusercontent.com/fivethirtyeight/data/master/pollster-ratings/2023
[ -f data/seed/fivethirtyeight/raw-polls-2023.csv ] || curl -fsSL -o data/seed/fivethirtyeight/raw-polls-2023.csv $B/raw-polls.csv
[ -f data/seed/fivethirtyeight/pollster-ratings-2023.csv ] || curl -fsSL -o data/seed/fivethirtyeight/pollster-ratings-2023.csv $B/pollster-ratings.csv
$PY -m pipeline.build
rm -f dist/CNAME dist/.nojekyll
