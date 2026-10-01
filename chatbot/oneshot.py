"""Разовый запуск для GitHub Actions: python -m chatbot.oneshot <режим>

Режимы:
  send         собрать сводку и сразу отправить в чат;
  send --wait  то же, но если сейчас раньше 9:00 МСК — дождаться 9:00;
  send --no-mentions  тестовая отправка без тэгов участников;
  poll         ответить на команды /news и /meme, пришедшие с прошлого запуска;
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

from . import meme, message
from .main import (
    BOT_COMMANDS,
    MSK,
    ROOT,
    SEND_AT,
    answer_command,
    load_env,
    send_meme,
    send_texts,
)
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


COMMANDS = {"news", "meme"}


def parse_command(text: str | None, bot_username: str) -> str | None:
    """'/news', '/meme@bot' → 'news' / 'meme'; всё остальное → None."""
    if not text or not text.startswith("/"):
        return None
    name, _, target = text.split()[0][1:].partition("@")
    if target and target.lower() != bot_username.lower():
        return None
    name = name.lower()
    return name if name in COMMANDS else None


async def process_updates(bot: Bot, chat_id: int, store: MemberStore) -> dict[str, int]:
    """Учитывает участников и возвращает команды: {команда: id последнего сообщения}."""
    me = await bot.get_me()
    commands = {}
    for msg in await read_updates(bot, confirm=True):
        if msg.chat.id != chat_id:
            continue
        store.record(msg)
        command = parse_command(msg.text, me.username)
        if command:
            commands[command] = msg.message_id
    return commands


async def answer_all(bot: Bot, chat_id: int, commands: dict[str, int]) -> None:
    for command, message_id in commands.items():
        try:
            await answer_command(bot, chat_id, command, message_id)
        except Exception:
            log.exception("Не удалось ответить на /%s", command)


def _store() -> MemberStore:
    return MemberStore(ROOT / "members.txt", ROOT / "data" / "members.json")


async def poll(bot: Bot, chat_id: int) -> None:
    await bot.set_my_commands(BOT_COMMANDS)
    commands = await process_updates(bot, chat_id, _store())
    await answer_all(bot, chat_id, commands)
    log.info("Команды обработаны: %s", ", ".join(commands) or "нет")


async def find_chat(bot: Bot) -> None:
    me = await bot.get_me()
    webhook = await bot.get_webhook_info()
    print(f"Токен принадлежит боту @{me.username}")
    print(f"Видит все сообщения в группах: {'да' if me.can_read_all_group_messages else 'нет'}")
    print(f"Вебхук: {'установлен' if webhook.url else 'нет'}, ждут обработки: {webhook.pending_update_count}")
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


async def send(bot: Bot, chat_id: int, wait: bool, mentions: bool = True) -> None:
    store = _store()
    commands = await process_updates(bot, chat_id, store)
    tags = store.mentions() if mentions else []
    texts, meme_item = await asyncio.gather(
        message.build(datetime.now(MSK).date(), tags), meme.get_meme()
    )
    if wait:
        await wait_until_send_time()
    await send_texts(bot, chat_id, texts)
    await send_meme(bot, chat_id, meme_item)
    await answer_all(bot, chat_id, commands)
    log.info("Сводка отправлена")


async def run(args: argparse.Namespace) -> None:
    async with Bot(os.environ["TELEGRAM_BOT_TOKEN"]) as bot:
        if args.mode == "find-chat":
            await find_chat(bot)
        elif args.mode == "poll":
            await poll(bot, int(os.environ["CHAT_ID"]))
        else:
            await send(bot, int(os.environ["CHAT_ID"]), args.wait, not args.no_mentions)


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_env(ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["send", "poll", "find-chat"])
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--no-mentions", action="store_true")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
