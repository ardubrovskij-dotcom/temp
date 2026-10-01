"""Мем дня: самый залайканный свежий мем с Reddit через meme-api.com."""

import logging
import os

import httpx

log = logging.getLogger(__name__)

API_URL = "https://meme-api.com/gimme/{subreddit}/{count}"
DEFAULT_SUBREDDIT = "memes"
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def pick_meme(memes: list[dict]) -> dict | None:
    """Выбирает картинку с наибольшим числом лайков, без 18+ и спойлеров."""
    ok = [
        m
        for m in memes
        if not m.get("nsfw")
        and not m.get("spoiler")
        and str(m.get("url", "")).lower().endswith(IMAGE_EXTS)
    ]
    return max(ok, key=lambda m: m.get("ups", 0), default=None)


async def get_meme() -> dict | None:
    subreddit = os.getenv("MEME_SUBREDDIT", DEFAULT_SUBREDDIT)
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            r = await client.get(API_URL.format(subreddit=subreddit, count=20))
            r.raise_for_status()
        return pick_meme(r.json().get("memes", []))
    except Exception:
        log.exception("Мем дня недоступен")
        return None
