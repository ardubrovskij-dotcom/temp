# Утренний бот для чата

Каждый день ровно в **9:00 МСК** бот пишет в чат одно сообщение:

1. День недели по реальному календарю и его название в чате:
   «Сегодня среда — поздравляю всех с Квадрой!»
2. 5 свежих новостей из ленты РБК, пересказанных Claude в стиле вечернего шоу (со ссылками).
3. Погоду на сегодня: Москва, Санкт-Петербург, Сочи, Волгоград (Open-Meteo).
4. Упоминания всех участников.

| День | Название в чате |
|---|---|
| Понедельник | Дрочельник |
| Вторник | Фуррник |
| Среда | Квадра |
| Четверг | Хоббихорсинг |
| Пятница | Нефорятница |
| Суббота | Гномбота |
| Воскресенье | Цуцикенье |

## Как бот узнаёт участников

Telegram не даёт ботам получить список всех участников группы. Поэтому:

- `members.txt` — юзернеймы, которых бот тэгает всегда (правится вручную);
- `data/members.json` — бот сам запоминает каждого, кто пишет в чат или вступает в него, и забывает тех, кто вышел.
  Людей без юзернейма бот упоминает ссылкой на имя.

Чтобы бот видел все сообщения, в @BotFather отключите privacy mode:
`/mybots → бот → Bot Settings → Group Privacy → Turn off`. После этого удалите бота из чата и добавьте снова.

## Установка

### 1. Создать бота
1. Напишите [@BotFather](https://t.me/BotFather) → `/newbot` → придумайте имя и юзернейм → скопируйте токен.
2. Отключите Group Privacy (см. выше).
3. Ключ для новостей: [platform.claude.com](https://platform.claude.com) → API Keys. Без ключа бот присылает обычные заголовки РБК без шуток.

### 2. Поставить на VPS (Ubuntu/Debian, Python ≥ 3.11)
```bash
sudo useradd -r -m -d /opt/chatbot chatbot
sudo -u chatbot git clone <URL репозитория> /opt/chatbot
cd /opt/chatbot
sudo -u chatbot python3 -m venv .venv
sudo -u chatbot .venv/bin/pip install -r requirements.txt
sudo -u chatbot cp .env.example .env
sudo -u chatbot nano .env          # TELEGRAM_BOT_TOKEN и ANTHROPIC_API_KEY
```

### 3. Узнать ID чата
```bash
sudo -u chatbot .venv/bin/python -m chatbot.main
```
Добавьте бота в чат, напишите `/chatid`, впишите ID в `.env` (`CHAT_ID=-100…`) и остановите бота (Ctrl+C).

### 4. Запустить как сервис
```bash
sudo cp deploy/chatbot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now chatbot
journalctl -u chatbot -f           # логи
```

## Команды
- `/today` — прислать сводку прямо сейчас (для проверки)
- `/chatid` — показать ID чата
- `/members` — сколько человек в списке упоминаний

## Как это работает
- В 8:57 МСК бот заранее собирает новости и погоду, в 9:00:00 отправляет готовое сообщение. Если заготовки нет, собирает её на месте.
- Новости: [RSS РБК](https://rssexport.rbc.ru/rbcnews/news/30/full.rss) → Claude (`claude-opus-5-5`, можно поменять в `ANTHROPIC_MODEL`) выбирает 5 самых значимых мировых новостей и пересказывает их с юмором. Если Claude недоступен или отказал, бот присылает обычные заголовки.
- Погода: [Open-Meteo](https://open-meteo.com), без ключа.
- Если сообщение длиннее лимита Telegram (4096 символов), упоминания уходят отдельным сообщением.

## Тесты
```bash
pip install pytest && python -m pytest -q
```
