import asyncio
import json
from datetime import date, timedelta
from types import SimpleNamespace

from chatbot import days, meme, message, news, weather
from chatbot.members import MemberStore

RSS = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
<item><title>Заголовок &amp; один</title><link>https://www.rbc.ru/a</link>
<category>Политика</category><description><![CDATA[<p>Анонс первой</p>]]></description></item>
<item><title>Второй</title><link>https://www.rbc.ru/b</link><category>Экономика</category></item>
<item><title>  </title><link>https://www.rbc.ru/empty</link></item>
</channel></rss>"""


def test_greeting_matches_real_calendar():
    monday = date(2026, 9, 28)
    expected = [
        "Сегодня понедельник — поздравляю всех с Дрочельником!",
        "Сегодня вторник — поздравляю всех с Фуррником!",
        "Сегодня среда — поздравляю всех с Квадрой!",
        "Сегодня четверг — поздравляю всех с Хоббихорсингом!",
        "Сегодня пятница — поздравляю всех с Нефорятницей!",
        "Сегодня суббота — поздравляю всех с Гномботой!",
        "Сегодня воскресенье — поздравляю всех с Цуцикеньем!",
    ]
    for i, text in enumerate(expected):
        assert days.greeting(monday + timedelta(days=i)) == text


def test_parse_rss():
    items = news.parse_rss(RSS)
    assert [i.title for i in items] == ["Заголовок & один", "Второй"]
    assert items[0].summary == "Анонс первой"
    assert items[1].category == "Экономика"


def test_format_jokes_skips_bad_indexes_and_escapes():
    items = news.parse_rss(RSS)
    picks = [{"index": 9, "joke": "нет"}, {"index": 1, "joke": "a < b"}, {"index": 0, "joke": ""}]
    assert news.format_jokes(items, picks) == (
        '1. <a href="https://www.rbc.ru/b">Второй</a>\n😏 <i>a &lt; b</i>'
    )


def test_comedy_uses_claude_output(monkeypatch):
    items = news.parse_rss(RSS)
    payload = {"items": [{"index": 0, "joke": "Шутка"}]}
    captured = {}

    class FakeMessages:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                stop_reason="end_turn",
                content=[SimpleNamespace(type="text", text=json.dumps(payload))],
            )

    class FakeClient:
        def __init__(self, **kwargs):
            self.beta = SimpleNamespace(messages=FakeMessages())

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(news.anthropic, "AsyncAnthropic", FakeClient)
    result = asyncio.run(news._comedy(items))
    assert result == '1. <a href="https://www.rbc.ru/a">Заголовок &amp; один</a>\n😏 <i>Шутка</i>'
    assert captured["model"] == "claude-opus-5-5"
    assert "[1] (Экономика) Второй" in captured["messages"][0]["content"]


def test_comedy_refusal_falls_back(monkeypatch):
    class FakeMessages:
        async def create(self, **kwargs):
            return SimpleNamespace(stop_reason="refusal", content=[])

    class FakeClient:
        def __init__(self, **kwargs):
            self.beta = SimpleNamespace(messages=FakeMessages())

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(news.anthropic, "AsyncAnthropic", FakeClient)
    assert asyncio.run(news._comedy(news.parse_rss(RSS))) is None


def test_format_city():
    daily = {
        "weather_code": [61],
        "temperature_2m_min": [-1.4],
        "temperature_2m_max": [5.6],
        "precipitation_probability_max": [70],
        "wind_speed_10m_max": [18.0],
    }
    assert weather.format_city("Москва", daily) == (
        "🌧 <b>Москва</b>: -1…+6°C, небольшой дождь, осадки 70%, ветер до 5 м/с"
    )


def test_members_dedupe_and_forget(tmp_path):
    static = tmp_path / "members.txt"
    static.write_text("# comment\n@Alice\nbob  # note\n", encoding="utf-8")
    store = MemberStore(static, tmp_path / "data" / "members.json")
    store.remember(1, "alice", "Алиса")
    store.remember(2, None, "Без <ника>")
    store.remember(3, "carol", "Кэрол")
    assert store.mentions() == [
        "@Alice",
        "@bob",
        '<a href="tg://user?id=2">Без &lt;ника&gt;</a>',
        "@carol",
    ]
    store.forget(3)
    reloaded = MemberStore(static, tmp_path / "data" / "members.json")
    assert "@carol" not in reloaded.mentions()


def test_compose_splits_long_mentions():
    mentions = [f"@user_{i:04d}" for i in range(600)]
    msgs = message.compose(date(2026, 9, 30), "новости", "погода", mentions)
    assert msgs[0].startswith("<b>Сегодня среда — поздравляю всех с Квадрой!</b>")
    assert all(len(m) <= message.TG_LIMIT for m in msgs)
    assert " ".join(msgs[1:]).split() == mentions


def test_compose_single_message():
    msgs = message.compose(date(2026, 9, 30), "н", "п", ["@a", "@b"])
    assert len(msgs) == 1 and msgs[0].endswith("@a @b")


def test_comedy_cli_parses_structured_output(monkeypatch, tmp_path):
    items = news.parse_rss(RSS)
    fake = tmp_path / "claude"
    out = json.dumps({"is_error": False, "result": "", "structured_output": {"items": [{"index": 1, "joke": "Ха"}]}})
    fake.write_text(f"#!/bin/sh\necho '{out}'\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test")
    result = asyncio.run(news._comedy(items))
    assert result == '1. <a href="https://www.rbc.ru/b">Второй</a>\n😏 <i>Ха</i>'


def test_pick_meme_skips_nsfw_and_video():
    memes = [
        {"url": "https://i.redd.it/a.jpg", "ups": 900, "nsfw": True},
        {"url": "https://v.redd.it/b.mp4", "ups": 800},
        {"url": "https://i.redd.it/c.gif", "ups": 700},
        {"url": "https://i.redd.it/d.png", "ups": 500, "spoiler": False},
        {"url": "https://i.redd.it/e.jpg", "ups": 100},
    ]
    assert meme.pick_meme(memes)["url"] == "https://i.redd.it/d.png"
    assert meme.pick_meme([]) is None
