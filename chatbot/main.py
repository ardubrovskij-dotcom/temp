"""Точка входа: python -m chatbot.main"""

import asyncio
import logging
import os
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import Bot, BotCommand, LinkPreviewOptions, ReplyParameters, Update
from telegram.constants import ParseMode
from telegram.error import NetworkError, RetryAfter
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from . import meme, message, news
from .members import MemberStore

MSK = ZoneInfo("Europe/Moscow")
SEND_AT = time(9, 0, tzinfo=MSK)
# Новости и погоду собираем заранее, чтобы сообщение ушло ровно в 9:00.
PREPARE_AT = time(8, 57, tzinfo=MSK)

ROOT = Path(__file__).resolve().parent.parent

BOT_COMMANDS = [
    BotCommand("news", "Свежие новости с шутками"),
    BotCommand("meme", "Случайный мем"),
]

log = logging.getLogger("chatbot")


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


async def send_texts(bot: Bot, chat_id: int, texts: list[str]) -> None:
    for text in texts:
        for attempt in range(3):
            try:
                await bot.send_message(
                    chat_id,
                    text,
                    parse_mode=ParseMode.HTML,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )
                break
            except RetryAfter as e:
                await asyncio.sleep(float(e.retry_after))
            except NetworkError:
                if attempt == 2:
                    raise
                log.warning("Сеть недоступна, повтор через 5 с")
                await asyncio.sleep(5)


async def send_meme(
    bot: Bot,
    chat_id: int,
    item: dict | None,
    caption: str = "🖼 Мем дня",
    reply_to: int | None = None,
) -> bool:
    if not item:
        return False
    nsfw = bool(item.get("nsfw") or item.get("spoiler"))
    try:
        await bot.send_photo(
            chat_id,
            item["url"],
            caption=caption + (" (18+)" if nsfw else ""),
            has_spoiler=nsfw,
            reply_parameters=_reply(reply_to),
        )
        return True
    except Exception:
        log.exception("Не удалось отправить мем %s", item.get("url"))
        return False


def _reply(message_id: int | None) -> ReplyParameters | None:
    if message_id is None:
        return None
    return ReplyParameters(message_id=message_id, allow_sending_without_reply=True)


async def answer_command(bot: Bot, chat_id: int, command: str, reply_to: int | None) -> None:
    """Ответ на /news и /meme."""
    if command == "news":
        news_text, _ = await news.get_digest()
        await bot.send_message(
            chat_id,
            f"📰 <b>Новости мира</b>\n\n{news_text}",
            parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
            reply_parameters=_reply(reply_to),
        )
    elif command == "meme":
        item = await meme.get_meme(random_pick=True)
        if not await send_meme(bot, chat_id, item, caption="🖼 Мем", reply_to=reply_to):
            await bot.send_message(
                chat_id, "Мемы закончились. Попробуйте посмеяться над собой.",
                reply_parameters=_reply(reply_to),
            )


async def _build_today(context: ContextTypes.DEFAULT_TYPE) -> list[str]:
    store: MemberStore = context.bot_data["store"]
    return await message.build(datetime.now(MSK).date(), store.mentions())


async def prepare_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    today = datetime.now(MSK).date()
    context.bot_data["prepared"] = (today, await _build_today(context))
    log.info("Утреннее сообщение подготовлено")


async def send_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    today = datetime.now(MSK).date()
    prepared = context.bot_data.pop("prepared", None)
    if prepared and prepared[0] == today:
        texts = prepared[1]
    else:
        log.warning("Заготовки нет — собираю сообщение сейчас")
        texts = await _build_today(context)
    chat_id = context.bot_data["chat_id"]
    if chat_id is None:
        log.warning("CHAT_ID не задан — некуда отправлять")
        return
    await send_texts(context.bot, chat_id, texts)
    await send_meme(context.bot, chat_id, await meme.get_meme())
    log.info("Утреннее сообщение отправлено")


async def cmd_chatid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(f"ID этого чата: {update.effective_chat.id}")


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text("Собираю сводку…")
    await send_texts(context.bot, update.effective_chat.id, await _build_today(context))
    await send_meme(context.bot, update.effective_chat.id, await meme.get_meme())


async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    await answer_command(context.bot, msg.chat_id, "news", msg.message_id)


async def cmd_meme(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    await answer_command(context.bot, msg.chat_id, "meme", msg.message_id)


async def cmd_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store: MemberStore = context.bot_data["store"]
    await update.effective_message.reply_text(
        f"В списке упоминаний: {len(store.mentions())} чел."
    )


async def track(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Запоминает пишущих и вступивших, забывает ушедших."""
    msg = update.effective_message
    if msg is None or update.effective_chat.id != context.bot_data["chat_id"]:
        return
    context.bot_data["store"].record(msg)


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_env(ROOT / ".env")

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = int(os.environ["CHAT_ID"]) if os.getenv("CHAT_ID") else None

    async def post_init(application: Application) -> None:
        await application.bot.set_my_commands(BOT_COMMANDS)

    app = Application.builder().token(token).post_init(post_init).build()
    app.bot_data["chat_id"] = chat_id
    app.bot_data["store"] = MemberStore(ROOT / "members.txt", ROOT / "data" / "members.json")

    app.add_handler(CommandHandler("chatid", cmd_chatid))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("members", cmd_members))
    app.add_handler(CommandHandler("news", cmd_news))
    app.add_handler(CommandHandler("meme", cmd_meme))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS, track), group=1)

    if chat_id is None:
        log.warning("CHAT_ID не задан: добавьте бота в чат, напишите /chatid и пропишите ID в .env")
    app.job_queue.run_daily(prepare_job, PREPARE_AT, name="prepare")
    app.job_queue.run_daily(send_job, SEND_AT, name="send")

    log.info("Бот запущен, чат %s, отправка в %s МСК", chat_id, SEND_AT.strftime("%H:%M"))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
