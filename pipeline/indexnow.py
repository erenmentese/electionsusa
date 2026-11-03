"""Tell Bing, Yandex and the other IndexNow engines which pages changed.

The deploy workflow builds the site, compares the new sitemap with the live one and posts every URL
whose lastmod moved (or that is new) to api.indexnow.org. The key file at the site root proves we
own the host. Google does not use IndexNow; it reads the sitemap.

    python -m pipeline.indexnow --sitemap dist/sitemap.xml            # submit changes
    python -m pipeline.indexnow --sitemap dist/sitemap.xml --dry-run  # list them only
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
import time

import requests

from . import config

ENDPOINT = "https://api.indexnow.org/indexnow"
MAX_URLS = 10_000  # the protocol's limit per request
log = logging.getLogger("indexnow")


def parse(sitemap: str) -> dict[str, str]:
    """loc -> lastmod ("" when absent)."""
    return dict(re.findall(r"<loc>([^<]+)</loc>(?:<lastmod>([^<]*)</lastmod>)?", sitemap))


def changed(new: str, old: str) -> list[str]:
    """URLs that are new or whose lastmod differs from the live sitemap."""
    before = parse(old)
    return [u for u, mod in parse(new).items() if u not in before or before[u] != mod]


def submit(urls: list[str], session: requests.Session | None = None) -> int:
    if not urls:
        return 0
    s = session or requests.Session()
    host = config.SITE["domain"]
    body = {"host": host, "key": config.INDEXNOW_KEY, "keyLocation": f"{config.SITE['url']}/{config.INDEXNOW_KEY}.txt",
            "urlList": urls[:MAX_URLS]}
    r = s.post(ENDPOINT, json=body, headers={"Content-Type": "application/json; charset=utf-8"}, timeout=30)
    log.info("IndexNow: %d URL(s) -> HTTP %s", len(body["urlList"]), r.status_code)
    return r.status_code


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sitemap", default=str(config.DIST_DIR / "sitemap.xml"))
    ap.add_argument("--wait", type=int, default=0, help="seconds to wait first, so the deploy is live")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    new = open(args.sitemap, encoding="utf-8").read()
    try:
        old = requests.get(f"{config.SITE['url']}/sitemap.xml", timeout=30).text
    except requests.RequestException as e:
        log.warning("could not read the live sitemap (%s); submitting every URL", e)
        old = ""
    urls = changed(new, old)
    log.info("%d changed URL(s)", len(urls))
    if args.dry_run:
        print("\n".join(urls))
        return 0
    if urls and args.wait:
        time.sleep(args.wait)
    status = submit(urls)
    return 0 if status in (0, 200, 202) else 1


if __name__ == "__main__":
    sys.exit(main())
