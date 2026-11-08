"""Written analysis pieces: one Markdown-like file per article in content/analysis/.

    ---
    headline: When will 2028 presidential candidates announce?
    dek: One-sentence summary, also the meta description.
    published: 2026-11-08
    updated: 2026-11-15        (optional; datePublished never moves)
    og: dem-primary-2028       (optional race id for the share image)
    keywords: words for the site search
    ---
    A paragraph, with [a link](/2028/candidates/) and **bold**.

    ## A heading

    - a list item

    | A table | header |
    |---|---|
    | cell | cell |

Text is escaped; only links and bold become HTML. A file whose `published` date is after the build date
stays unpublished, so a piece can be written ahead and go live on its day.
"""
from __future__ import annotations

import re
from datetime import date
from html import escape
from pathlib import Path

from markupsafe import Markup

from . import config

CONTENT_DIR = config.ROOT / "content" / "analysis"
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
BOLD = re.compile(r"\*\*(.+?)\*\*")


def inline(text: str) -> Markup:
    def link(m: re.Match) -> str:
        label, url = m.group(1), m.group(2)
        if url.startswith("/"):
            return f'<a href="{url}">{label}</a>'
        if not url.startswith("https://"):
            raise ValueError(f"links must be site paths or https: {url}")
        return f'<a href="{url}" rel="nofollow noopener">{label}</a>'
    return Markup(BOLD.sub(r"<b>\1</b>", LINK.sub(link, escape(text, quote=False))))


def parse(path: Path) -> dict:
    text = path.read_text()
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    if not m:
        raise ValueError(f"{path.name}: missing front matter")
    meta = dict(line.split(":", 1) for line in m.group(1).splitlines() if line.strip())
    meta = {k.strip(): v.strip() for k, v in meta.items()}
    for key in ("headline", "dek", "published"):
        if not meta.get(key):
            raise ValueError(f"{path.name}: front matter needs {key}")
    published = date.fromisoformat(meta["published"])
    body: list[dict] = []
    for chunk in re.split(r"\n\s*\n", m.group(2).strip()):
        lines = [ln.rstrip() for ln in chunk.strip().splitlines()]
        if lines[0].startswith("## "):
            body.append(dict(h=lines[0][3:].strip()))
            lines = lines[1:]
            if not lines:
                continue
        if all(ln.startswith("- ") for ln in lines):
            body.append(dict(bullets=[inline(ln[2:]) for ln in lines]))
        elif all(ln.startswith("|") for ln in lines):
            cells = [[c.strip() for c in ln.strip("|").split("|")] for ln in lines if not re.fullmatch(r"\|[\s:|-]+\|", ln)]
            body.append(dict(table=dict(head=cells[0], rows=[[inline(c) for c in r] for r in cells[1:]], text=True)))
        else:
            body.append(dict(p=inline(" ".join(lines))))
    slug = path.stem
    return dict(slug=slug, path=f"/analysis/{slug}/", headline=meta["headline"], dek=meta["dek"], published=published,
                modified=date.fromisoformat(meta["updated"]) if meta.get("updated") else published,
                og=meta.get("og"), keywords=meta.get("keywords", ""), body=body)


def load(as_of: date) -> list[dict]:
    """Every written article published on or before `as_of`."""
    if not CONTENT_DIR.exists():
        return []
    out = []
    for path in sorted(CONTENT_DIR.glob("*.md")):
        a = parse(path)
        if a["published"] <= as_of:
            a["modified"] = min(max(a["modified"], a["published"]), as_of)
            out.append(a)
    return out
