"""Minimal X (Twitter) API client for posting with OAuth 1.0a user context.

Credentials come from environment variables (GitHub Actions secrets):
  X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET

Posting uses POST /2/tweets. Images use the v1.1 media upload endpoint, which
works with OAuth 1.0a; X has announced a v2 replacement (OAuth 2.0 only), so a
failed upload falls back to a text-only post instead of losing the post.
"""
from __future__ import annotations

import logging
import os
import time

import requests
from requests_oauthlib import OAuth1

log = logging.getLogger(__name__)
POST_URL = "https://api.x.com/2/tweets"
UPLOAD_URL = "https://upload.x.com/1.1/media/upload.json"
ALT_URL = "https://upload.x.com/1.1/media/metadata/create.json"
ENV = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")


class XError(RuntimeError):
    pass


def credentials_present() -> bool:
    return all(os.environ.get(k) for k in ENV)


class XClient:
    def __init__(self, session: requests.Session | None = None):
        missing = [k for k in ENV if not os.environ.get(k)]
        if missing:
            raise XError(f"missing credentials: {', '.join(missing)}")
        self.auth = OAuth1(os.environ["X_API_KEY"], os.environ["X_API_SECRET"],
                           os.environ["X_ACCESS_TOKEN"], os.environ["X_ACCESS_TOKEN_SECRET"])
        self.s = session or requests.Session()

    def _check(self, r: requests.Response, what: str) -> dict:
        if r.status_code == 429:
            reset = r.headers.get("x-rate-limit-reset")
            raise XError(f"{what}: rate limited (resets at {reset})")
        if r.status_code >= 400:
            raise XError(f"{what}: HTTP {r.status_code} {r.text[:300]}")
        return r.json() if r.content else {}

    def upload_png(self, png: bytes, alt: str = "") -> str:
        r = self.s.post(UPLOAD_URL, auth=self.auth, files={"media": ("card.png", png, "image/png")},
                        data={"media_category": "tweet_image"}, timeout=60)
        media_id = str(self._check(r, "media upload")["media_id_string"])
        if alt:
            try:
                ra = self.s.post(ALT_URL, auth=self.auth, json={"media_id": media_id, "alt_text": {"text": alt[:1000]}}, timeout=30)
                self._check(ra, "alt text")
            except XError as e:  # alt text is best effort
                log.warning("%s", e)
        return media_id

    def post(self, text: str, media_ids: list[str] | None = None, reply_to: str | None = None) -> str:
        body: dict = {"text": text}
        if media_ids:
            body["media"] = {"media_ids": media_ids}
        if reply_to:
            body["reply"] = {"in_reply_to_tweet_id": reply_to}
        for attempt in range(3):
            r = self.s.post(POST_URL, auth=self.auth, json=body, timeout=30)
            if r.status_code >= 500 and attempt < 2:
                time.sleep(2 ** (attempt + 1))
                continue
            return str(self._check(r, "create post")["data"]["id"])
        raise XError("create post: server errors")

    def post_with_card(self, text: str, png: bytes | None, alt: str = "") -> str:
        media = []
        if png:
            try:
                media = [self.upload_png(png, alt)]
            except XError as e:
                log.warning("image upload failed, posting text only: %s", e)
        return self.post(text, media or None)
