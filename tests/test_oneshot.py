import asyncio
from types import SimpleNamespace

import pytest

from chatbot import oneshot


@pytest.fixture(autouse=True)
def no_meme(monkeypatch):
    async def fake_meme():
        return None

    monkeypatch.setattr(oneshot.meme, "get_meme", fake_meme)


def _msg(chat_id, user_id, username, is_bot=False, text="привет", message_id=1):
    user = SimpleNamespace(id=user_id, username=username, first_name=username, is_bot=is_bot)
    chat = SimpleNamespace(id=chat_id, title="Чат", full_name=None, type="supergroup")
    return SimpleNamespace(
        chat=chat, from_user=user, new_chat_members=(), left_chat_member=None,
        text=text, message_id=message_id,
    )


class FakeBot:
    def __init__(self, messages):
        self.queue = [SimpleNamespace(update_id=i, message=m) for i, m in enumerate(messages, 100)]
        self.offsets = []
        self.sent = []
        self.commands = None

    async def get_me(self):
        return SimpleNamespace(username="bashenka_dailynews_bot")

    async def set_my_commands(self, commands):
        self.commands = commands

    async def get_updates(self, offset=None, **kwargs):
        self.offsets.append(offset)
        return tuple(u for u in self.queue if offset is None or u.update_id >= offset)

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text))

    async def send_photo(self, chat_id, photo, **kwargs):
        self.sent.append((chat_id, photo))


def test_read_updates_confirms_last_offset():
    bot = FakeBot([_msg(-1, 1, "a"), _msg(-1, 2, "b")])
    msgs = asyncio.run(oneshot.read_updates(bot, confirm=True))
    assert len(msgs) == 2
    assert bot.offsets == [None, 102, 102]


def test_send_records_members_from_target_chat_only(tmp_path, monkeypatch):
    (tmp_path / "members.txt").write_text("@static\n", encoding="utf-8")
    monkeypatch.setattr(oneshot, "ROOT", tmp_path)

    async def fake_build(day, mentions):
        return [" ".join(mentions)]

    monkeypatch.setattr(oneshot.message, "build", fake_build)
    bot = FakeBot([_msg(-1, 1, "alice"), _msg(-2, 2, "stranger"), _msg(-1, 3, "robot", is_bot=True)])
    asyncio.run(oneshot.send(bot, -1, wait=False))
    assert bot.sent == [(-1, "@static @alice")]
    assert (tmp_path / "data" / "members.json").exists()


def test_send_without_mentions(tmp_path, monkeypatch):
    (tmp_path / "members.txt").write_text("@static\n", encoding="utf-8")
    monkeypatch.setattr(oneshot, "ROOT", tmp_path)

    async def fake_build(day, mentions):
        return [f"tags={len(mentions)}"]

    monkeypatch.setattr(oneshot.message, "build", fake_build)
    bot = FakeBot([_msg(-1, 1, "alice")])
    asyncio.run(oneshot.send(bot, -1, wait=False, mentions=False))
    assert bot.sent == [(-1, "tags=0")]


def test_send_attaches_meme(tmp_path, monkeypatch):
    monkeypatch.setattr(oneshot, "ROOT", tmp_path)

    async def fake_build(day, mentions):
        return ["сводка"]

    async def fake_meme():
        return {"url": "https://i.redd.it/x.jpg", "title": "t"}

    monkeypatch.setattr(oneshot.message, "build", fake_build)
    monkeypatch.setattr(oneshot.meme, "get_meme", fake_meme)
    bot = FakeBot([])
    asyncio.run(oneshot.send(bot, -1, wait=False))
    assert bot.sent == [(-1, "сводка"), (-1, "https://i.redd.it/x.jpg")]


def test_parse_command():
    bot = "bashenka_dailynews_bot"
    assert oneshot.parse_command("/news", bot) == "news"
    assert oneshot.parse_command("/MEME@Bashenka_DailyNews_Bot", bot) == "meme"
    assert oneshot.parse_command("/news@other_bot", bot) is None
    assert oneshot.parse_command("/start", bot) is None
    assert oneshot.parse_command("news", bot) is None
    assert oneshot.parse_command(None, bot) is None


def test_poll_answers_each_command_once(tmp_path, monkeypatch):
    monkeypatch.setattr(oneshot, "ROOT", tmp_path)
    answered = []

    async def fake_answer(bot, chat_id, command, reply_to):
        answered.append((chat_id, command, reply_to))

    monkeypatch.setattr(oneshot, "answer_command", fake_answer)
    bot = FakeBot([
        _msg(-1, 1, "a", text="/news", message_id=10),
        _msg(-1, 2, "b", text="/news", message_id=11),
        _msg(-1, 3, "c", text="/meme@bashenka_dailynews_bot", message_id=12),
        _msg(-2, 4, "x", text="/meme", message_id=13),
    ])
    asyncio.run(oneshot.poll(bot, -1))
    assert answered == [(-1, "news", 11), (-1, "meme", 12)]
    assert [c.command for c in bot.commands] == ["news", "meme"]
