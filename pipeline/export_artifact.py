"""Export dist/ as a self-contained bundle with relative links.

The production site uses root-absolute URLs (/approval/trump/). Static previews
hosted under a sub-path (an Artifact, a file share, a ZIP opened locally) need
relative links that point at index.html files explicitly.

    python -m pipeline.build && python -m pipeline.export_artifact
    -> dist-artifact/
"""
from __future__ import annotations

import os
import re
import shutil
import sys

from . import config

OUT = config.ROOT / "dist-artifact"
SKIP = {"CNAME", "ads.txt", "robots.txt", "sitemap.xml", ".nojekyll"}
ATTR = re.compile(r'(\s(?:href|src))="(/(?!/)[^"]*)"')


def rel_target(target: str, page_dir: str) -> str:
    frag = ""
    if "#" in target:
        target, frag = target.split("#", 1)
        frag = "#" + frag
    path = target.lstrip("/")
    if path == "" or path.endswith("/"):
        path += "index.html"
    rel = os.path.relpath(path, page_dir or ".")
    return rel + frag


def export() -> list[str]:
    src = config.DIST_DIR
    if OUT.exists():
        shutil.rmtree(OUT)
    files: list[str] = []
    for f in sorted(src.rglob("*")):
        if f.is_dir() or f.name in SKIP:
            continue
        rel = f.relative_to(src).as_posix()
        dest = OUT / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if f.suffix != ".html":
            shutil.copy(f, dest)
            files.append(rel)
            continue
        page_dir = os.path.dirname(rel)
        html = f.read_text(encoding="utf-8")
        html = ATTR.sub(lambda m: f'{m.group(1)}="{rel_target(m.group(2), page_dir)}"', html)
        root = os.path.relpath(".", page_dir or ".")
        root = "" if root == "." else root + "/"
        html = html.replace('<script src="', f'<script>window.SITE_ROOT="{root or "./"}";</script>\n<script src="', 1)
        if rel == "index.html":
            # the artifact host supplies the document skeleton for the main page
            html = re.sub(r"<!doctype html>\s*", "", html, flags=re.I)
            html = re.sub(r"</?html[^>]*>\s*|</?head>\s*|</?body>\s*", "", html)
            html = re.sub(r"<title>.*?</title>", "<title>ElectionsUSA</title>", html, count=1, flags=re.S)
        dest.write_text(html, encoding="utf-8")
        files.append(rel)
    print(f"exported {len(files)} files -> {OUT}")
    return files


if __name__ == "__main__":
    export()
    sys.exit(0)
