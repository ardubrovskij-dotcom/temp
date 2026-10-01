"""Список участников для упоминаний.

Telegram Bot API не отдаёт список всех участников группы, поэтому список
складывается из двух источников:
  1. members.txt — юзернеймы, которых тэгаем всегда;
  2. data/members.json — те, кого бот увидел в чате сам (написали сообщение,
     вступили в чат). Ушедшие из чата удаляются.
"""

import html
import json
import logging
import threading
from pathlib import Path

log = logging.getLogger(__name__)


def load_static(path: Path) -> list[str]:
    if not path.exists():
        return []
    names = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip().lstrip("@")
        if line:
            names.append(line)
    return names


class MemberStore:
    def __init__(self, static_path: Path, data_path: Path):
        self.static = load_static(static_path)
        self.data_path = data_path
        self._lock = threading.Lock()
        self._seen: dict[str, dict] = {}
        if data_path.exists():
            try:
                self._seen = json.loads(data_path.read_text(encoding="utf-8"))
            except ValueError:
                log.exception("Повреждён %s — начинаю с пустого списка", data_path)

    def _save(self) -> None:
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.data_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._seen, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.data_path)

    def remember(self, user_id: int, username: str | None, first_name: str) -> None:
        entry = {"username": username or "", "name": first_name or ""}
        key = str(user_id)
        with self._lock:
            if self._seen.get(key) == entry:
                return
            self._seen[key] = entry
            self._save()

    def forget(self, user_id: int) -> None:
        with self._lock:
            if self._seen.pop(str(user_id), None) is not None:
                self._save()

    def mentions(self) -> list[str]:
        """HTML-упоминания без дублей (юзернеймы сравниваются без учёта регистра)."""
        result = [f"@{u}" for u in self.static]
        used = {u.lower() for u in self.static}
        with self._lock:
            seen = list(self._seen.items())
        for user_id, info in seen:
            username = info.get("username", "")
            if username:
                if username.lower() in used:
                    continue
                used.add(username.lower())
                result.append(f"@{username}")
            else:
                name = html.escape(info.get("name") or "участник")
                result.append(f'<a href="tg://user?id={user_id}">{name}</a>')
        return result
