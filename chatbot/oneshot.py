"""Разовый запуск для GitHub Actions: python -m chatbot.oneshot <режим>

Режимы:
  send         собрать сводку и сразу отправить в чат;
  send --wait  то же, но если сейчас раньше 9:00 МСК — дождаться 9:00;
  find-chat    вывести ID чатов, где боту недавно писали (для настройки CHAT_ID).

Постоянно работающего процесса нет, поэтому участников бот узнаёт из
очереди getUpdates: Telegram хранит непрочитанные обновления 24 часа.
"""

import argparse
import asyncio
import logging
import os
from datetime import datetime, timedelta

from telegram import Bot

from . import message
from .main import MSK, ROOT, SEND_AT, load_env, send_texts
from .members import MemberStore

log = logging.getLogger("chatbot.oneshot")


async def read_updates(bot: Bot, confirm: bool) -> list:
    """Забирает все накопившиеся сообщения. confirm=True помечает их прочитанными."""
    messages = []
    offset = None
    while True:
        updates = await bot.get_updates(
            offset=offset, timeout=0, allowed_updates=["message"]
        )
        if not updates:
            break
        offset = updates[-1].update_id + 1
        messages.extend(u.message for u in updates if u.message)
    if confirm and offset is not None:
        await bot.get_updates(offset=offset, timeout=0, limit=1)
    return messages


async def find_chat(bot: Bot) -> None:
    chats = {}
    for msg in await read_updates(bot, confirm=False):
        chats[msg.chat.id] = msg.chat.title or msg.chat.full_name or msg.chat.type
    if not chats:
        print("Сообщений нет. Добавьте бота в чат, напишите там /chatid и запустите снова.")
    for chat_id, title in chats.items():
        print(f"CHAT_ID={chat_id}  ({title})")


async def wait_until_send_time() -> None:
    now = datetime.now(MSK)
    target = now.replace(hour=SEND_AT.hour, minute=SEND_AT.minute, second=0, microsecond=0)
    delay = (target - now).total_seconds()
    if 0 < delay <= timedelta(hours=2).total_seconds():
        log.info("Сводка готова, жду %s МСК (%.0f с)", SEND_AT.strftime("%H:%M"), delay)
        await asyncio.sleep(delay)


async def send(bot: Bot, chat_id: int, wait: bool) -> None:
    store = MemberStore(ROOT / "members.txt", ROOT / "data" / "members.json")
    for msg in await read_updates(bot, confirm=True):
        if msg.chat.id == chat_id:
            store.record(msg)
    texts = await message.build(datetime.now(MSK).date(), store.mentions())
    if wait:
        await wait_until_send_time()
    await send_texts(bot, chat_id, texts)
    log.info("Сводка отправлена")


async def run(args: argparse.Namespace) -> None:
    async with Bot(os.environ["TELEGRAM_BOT_TOKEN"]) as bot:
        if args.mode == "find-chat":
            await find_chat(bot)
        else:
            await send(bot, int(os.environ["CHAT_ID"]), args.wait)


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_env(ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["send", "find-chat"])
    parser.add_argument("--wait", action="store_true")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
