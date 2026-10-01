"""Прогноз погоды на сегодня через Open-Meteo (бесплатно, без ключа)."""

import asyncio
import logging

import httpx

log = logging.getLogger(__name__)

API_URL = "https://api.open-meteo.com/v1/forecast"

CITIES = [
    ("Москва", 55.7558, 37.6173),
    ("Санкт-Петербург", 59.9386, 30.3141),
    ("Сочи", 43.6028, 39.7342),
    ("Волгоград", 48.7080, 44.5133),
]

# Коды погоды WMO: https://open-meteo.com/en/docs
WMO = {
    0: ("☀️", "ясно"),
    1: ("🌤", "преимущественно ясно"),
    2: ("⛅️", "переменная облачность"),
    3: ("☁️", "пасмурно"),
    45: ("🌫", "туман"),
    48: ("🌫", "изморозь"),
    51: ("🌦", "лёгкая морось"),
    53: ("🌦", "морось"),
    55: ("🌧", "сильная морось"),
    56: ("🌧", "ледяная морось"),
    57: ("🌧", "сильная ледяная морось"),
    61: ("🌧", "небольшой дождь"),
    63: ("🌧", "дождь"),
    65: ("🌧", "сильный дождь"),
    66: ("🌧", "ледяной дождь"),
    67: ("🌧", "сильный ледяной дождь"),
    71: ("🌨", "небольшой снег"),
    73: ("🌨", "снег"),
    75: ("❄️", "сильный снег"),
    77: ("🌨", "снежная крупа"),
    80: ("🌦", "небольшой ливень"),
    81: ("🌧", "ливень"),
    82: ("⛈", "сильный ливень"),
    85: ("🌨", "снегопад"),
    86: ("❄️", "сильный снегопад"),
    95: ("⛈", "гроза"),
    96: ("⛈", "гроза с градом"),
    99: ("⛈", "сильная гроза с градом"),
}


def _signed(t: float) -> str:
    v = round(t)
    return f"+{v}" if v > 0 else str(v)


def format_city(name: str, daily: dict) -> str:
    code = daily["weather_code"][0]
    emoji, text = WMO.get(code, ("🌡", "без описания"))
    t_min = _signed(daily["temperature_2m_min"][0])
    t_max = _signed(daily["temperature_2m_max"][0])
    rain = daily["precipitation_probability_max"][0]
    wind = round(daily["wind_speed_10m_max"][0] / 3.6)  # км/ч → м/с
    parts = [f"{emoji} <b>{name}</b>: {t_min}…{t_max}°C, {text}"]
    if rain is not None:
        parts.append(f"осадки {rain}%")
    parts.append(f"ветер до {wind} м/с")
    return ", ".join(parts)


async def _fetch_city(client: httpx.AsyncClient, name: str, lat: float, lon: float) -> str:
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
        "precipitation_probability_max,wind_speed_10m_max",
        "timezone": "Europe/Moscow",
        "forecast_days": 1,
    }
    try:
        r = await client.get(API_URL, params=params)
        r.raise_for_status()
        return format_city(name, r.json()["daily"])
    except Exception:
        log.exception("Погода для %s недоступна", name)
        return f"🌡 <b>{name}</b>: прогноз недоступен"


async def get_weather() -> str:
    async with httpx.AsyncClient(timeout=15) as client:
        lines = await asyncio.gather(*(_fetch_city(client, *c) for c in CITIES))
    return "\n".join(lines)
