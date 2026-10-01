"""Свежие новости РБК, пересказанные Claude в стиле вечернего шоу."""

import html
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import anthropic
import httpx

log = logging.getLogger(__name__)

RSS_URL = "https://rssexport.rbc.ru/rbcnews/news/30/full.rss"
NEWS_COUNT = 5
DEFAULT_MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """\
Ты — автор монологов для вечернего комедийного шоу в духе «Вечернего Урганта». \
Каждое утро ты пересказываешь главные мировые новости для дружеского чата.

Стиль: лёгкая ирония, остроумные сравнения, абсурдные наблюдения. \
Немного чёрного юмора допустимо, но основа — добрая интеллигентная шутка. \
Не издевайся над жертвами трагедий, не используй мат и оскорбления по национальности, \
полу, религии. Факт новости должен остаться узнаваемым и точным — шутка идёт поверх факта, \
а не вместо него. Не выдумывай детали, которых нет в заголовке и анонсе.

Каждый пересказ — 1–2 коротких предложения на русском языке, без эмодзи в начале."""

USER_PROMPT = """\
Ниже свежая лента РБК. Выбери {count} самых значимых новостей, \
отдавая приоритет мировым и международным событиям (политика, экономика, наука, технологии), \
а не региональным происшествиям. Для каждой укажи номер из ленты и напиши смешной пересказ.

{feed}"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "joke": {"type": "string"},
                },
                "required": ["index", "joke"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


@dataclass
class NewsItem:
    title: str
    link: str
    category: str
    summary: str


def _clean(text: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def parse_rss(xml_text: str) -> list[NewsItem]:
    root = ET.fromstring(xml_text)
    items = []
    for node in root.iter("item"):
        title = _clean(node.findtext("title"))
        if not title:
            continue
        items.append(
            NewsItem(
                title=title,
                link=(node.findtext("link") or "").strip(),
                category=_clean(node.findtext("category")),
                summary=_clean(node.findtext("description"))[:300],
            )
        )
    return items


async def fetch_rbc() -> list[NewsItem]:
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        r = await client.get(RSS_URL)
        r.raise_for_status()
    return parse_rss(r.text)


def _feed_text(items: list[NewsItem]) -> str:
    lines = []
    for i, it in enumerate(items):
        line = f"[{i}] ({it.category or 'без рубрики'}) {it.title}"
        if it.summary:
            line += f" — {it.summary}"
        lines.append(line)
    return "\n".join(lines)


def _link(text: str, url: str) -> str:
    if not url:
        return html.escape(text)
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(text)}</a>'


def format_plain(items: list[NewsItem]) -> str:
    return "\n".join(f"{n}. {_link(it.title, it.link)}" for n, it in enumerate(items[:NEWS_COUNT], 1))


def format_jokes(items: list[NewsItem], picks: list[dict]) -> str:
    lines = []
    for pick in picks:
        idx = pick.get("index")
        joke = (pick.get("joke") or "").strip()
        if not isinstance(idx, int) or not 0 <= idx < len(items) or not joke:
            continue
        lines.append(f"{len(lines) + 1}. {html.escape(joke)} {_link('(РБК)', items[idx].link)}")
        if len(lines) == NEWS_COUNT:
            break
    return "\n".join(lines)


async def _comedy(items: list[NewsItem]) -> str | None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        log.info("ANTHROPIC_API_KEY не задан — новости без шуток")
        return None
    client = anthropic.AsyncAnthropic(timeout=120)
    try:
        response = await client.beta.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL),
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": USER_PROMPT.format(count=NEWS_COUNT, feed=_feed_text(items)),
                }
            ],
            output_config={
                "effort": "low",
                "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
            },
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.APIConnectionError:
        log.exception("Claude API недоступен")
        return None
    except anthropic.RateLimitError:
        log.exception("Claude API: превышен лимит запросов")
        return None
    except anthropic.APIStatusError:
        log.exception("Claude API вернул ошибку")
        return None

    if response.stop_reason != "end_turn":
        log.warning("Claude не закончил ответ: stop_reason=%s", response.stop_reason)
        return None
    text = "".join(b.text for b in response.content if b.type == "text")
    try:
        picks = json.loads(text)["items"]
    except (ValueError, KeyError, TypeError):
        log.exception("Не удалось разобрать ответ Claude: %r", text[:500])
        return None
    return format_jokes(items, picks) or None


async def get_news() -> str:
    try:
        items = await fetch_rbc()
    except Exception:
        log.exception("Лента РБК недоступна")
        return "Лента РБК сегодня не отвечает — видимо, новости ещё спят."
    if not items:
        return "В ленте РБК пусто — редкий день, когда в мире ничего не случилось."
    return await _comedy(items) or format_plain(items)
