# Vercel build command: sh vercel-build.sh  (output directory: dist)
set -e
PY=python3
for v in python3.13 python3.12 python3.11 python3; do if command -v $v >/dev/null 2>&1; then PY=$v; break; fi; done
$PY -m pip install --quiet --break-system-packages -r requirements.txt || $PY -m pip install --quiet -r requirements.txt
mkdir -p data/seed/fivethirtyeight
B=https://raw.githubusercontent.com/fivethirtyeight/data/master/pollster-ratings/2023
[ -f data/seed/fivethirtyeight/raw-polls-2023.csv ] || curl -fsSL -o data/seed/fivethirtyeight/raw-polls-2023.csv $B/raw-polls.csv
[ -f data/seed/fivethirtyeight/pollster-ratings-2023.csv ] || curl -fsSL -o data/seed/fivethirtyeight/pollster-ratings-2023.csv $B/pollster-ratings.csv
$PY -m pipeline.build
rm -f dist/CNAME dist/.nojekyll
