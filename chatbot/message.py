"""Сборка утреннего сообщения."""

import asyncio
import html
from datetime import date

from . import days, news, weather

TG_LIMIT = 4096
SEPARATOR = "\n--------------\n"


def compose(
    day: date, news_text: str, wish: str, weather_text: str, mentions: list[str]
) -> list[str]:
    """Возвращает список сообщений: сводку и (если не влезают) упоминания отдельно."""
    sections = [
        f"<b>{html.escape(days.greeting(day))}</b>",
        f"📰 <b>Новости мира</b>\n\n{news_text}",
        f"💌 <b>Пожелание на день</b>\n{wish}",
        f"🌦 <b>Погода на сегодня</b>\n{weather_text}",
    ]
    main = SEPARATOR.join(sections)
    if not mentions:
        return [main]
    tags = " ".join(mentions)
    combined = f"{main}{SEPARATOR}{tags}"
    if len(combined) <= TG_LIMIT:
        return [combined]
    messages = [main]
    chunk = ""
    for m in mentions:
        candidate = f"{chunk} {m}".strip()
        if len(candidate) > TG_LIMIT:
            messages.append(chunk)
            candidate = m
        chunk = candidate
    messages.append(chunk)
    return messages


async def build(day: date, mentions: list[str]) -> list[str]:
    (news_text, wish), weather_text = await asyncio.gather(
        news.get_digest(), weather.get_weather()
    )
    return compose(day, news_text, wish, weather_text, mentions)
