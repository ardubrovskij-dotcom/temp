import asyncio
from types import SimpleNamespace

from chatbot import oneshot


def _msg(chat_id, user_id, username, is_bot=False):
    user = SimpleNamespace(id=user_id, username=username, first_name=username, is_bot=is_bot)
    chat = SimpleNamespace(id=chat_id, title="Чат", full_name=None, type="supergroup")
    return SimpleNamespace(chat=chat, from_user=user, new_chat_members=(), left_chat_member=None)


class FakeBot:
    def __init__(self, messages):
        self.queue = [SimpleNamespace(update_id=i, message=m) for i, m in enumerate(messages, 100)]
        self.offsets = []
        self.sent = []

    async def get_updates(self, offset=None, **kwargs):
        self.offsets.append(offset)
        return tuple(u for u in self.queue if offset is None or u.update_id >= offset)

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text))


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
