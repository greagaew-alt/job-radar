# -*- coding: utf-8 -*-
"""
ОТПРАВКА В ТЕЛЕГРАМ-БОТ

Собирает сообщение и шлёт его тебе в личку. Вакансия приходит с вердиктом:
что это за работа, сколько платят и стоит ли вообще связываться.
"""

import html as html_mod
import os
import time
from datetime import datetime, timedelta, timezone

import requests

import config

API = "https://api.telegram.org/bot{token}/sendMessage"
TG_LIMIT = 4096          # жёсткий лимит длины сообщения в телеграме

VERDICT_STYLE = {
    "ok":         ("✅", "НОРМ"),
    "suspicious": ("⚠️", "СОМНИТЕЛЬНАЯ"),
    "scam":       ("⛔", "НЕ НОРМ"),
}

CATEGORY_NAME = {
    "design":   "Веб-дизайн",
    "frontend": "Вёрстка / фронтенд",
    "project":  "Проектная работа",
    "remote":   "Удалёнка (не по профилю)",
}


def _esc(s):
    """Экранирует символы, которые телеграм примет за разметку."""
    return html_mod.escape(s, quote=False)


MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def format_when(iso_date):
    """
    Превращает «2026-07-27T15:01:12+00:00» в «сегодня в 18:01».

    Свежесть решает: вакансия часовой давности и трёхдневная — разные
    шансы на отклик, и это должно быть видно сразу, без вычислений в уме.
    Время переводится в твой часовой пояс из config.TIMEZONE_OFFSET —
    на GitHub сервер живёт по UTC, и без пересчёта время было бы чужим.
    """
    if not iso_date:
        return None

    try:
        raw = iso_date.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    tz = timezone(timedelta(hours=config.TIMEZONE_OFFSET))
    dt = dt.astimezone(tz)
    now = datetime.now(tz)

    days = (now.date() - dt.date()).days
    clock = dt.strftime("%H:%M")

    if days == 0:
        minutes = int((now - dt).total_seconds() // 60)
        if minutes < 2:
            return "только что"
        if minutes < 60:
            return f"{minutes} мин назад"
        hours = minutes // 60
        if hours < 5:
            word = "час" if hours == 1 else ("часа" if hours < 5 else "часов")
            return f"{hours} {word} назад · {clock}"
        return f"сегодня в {clock}"
    if days == 1:
        return f"вчера в {clock}"
    if days < 7:
        return f"{days} дн назад · {dt.day} {MONTHS[dt.month - 1]}"
    return f"{dt.day} {MONTHS[dt.month - 1]}, {clock}"


def _format_salary(item, analysis):
    """Строка с деньгами — из hh берём точные данные, из телеграма разбираем текст."""
    sal = item.get("hh_salary")
    if sal:
        lo, hi = sal.get("from"), sal.get("to")
        cur = {"RUR": "₽", "USD": "$", "EUR": "€"}.get(sal.get("currency"), "")
        if lo and hi:
            return f"{lo:,} – {hi:,} {cur}".replace(",", " ")
        if lo:
            return f"от {lo:,} {cur}".replace(",", " ")
        if hi:
            return f"до {hi:,} {cur}".replace(",", " ")

    lo, hi, raw = analysis["salary"]
    if lo is None:
        return None
    if hi and hi != lo:
        return f"{lo:,} – {hi:,} ₽".replace(",", " ")
    return f"от {lo:,} ₽".replace(",", " ")


def build_message(item, analysis):
    """Собирает готовый текст сообщения."""
    icon, label = VERDICT_STYLE[analysis["verdict"]]
    category = CATEGORY_NAME.get(analysis["category"], "Работа")

    head = f"{icon} <b>{label}</b> · {category}"
    if analysis["is_project"] and analysis["category"] != "project":
        head += " · разовый заказ"

    lines = [head]

    money = _format_salary(item, analysis)
    when = format_when(item.get("date"))

    money_line = f"💰 <b>{_esc(money)}</b>" if money else "💰 зП не указана"
    if when:
        money_line += f"   🕒 {_esc(when)}"
    lines.append(money_line)

    lines.append("")

    # --- тело вакансии ---
    body = item["text"].strip()
    # оставляем место под шапку, подвал и разбор
    reserve = 900 + sum(len(w) for w in analysis["why"]) + \
        sum(len(w) for w in analysis.get("green_why", []))
    room = TG_LIMIT - reserve
    if len(body) > room:
        body = body[:room].rsplit("\n", 1)[0].rstrip() + "\n…"
    lines.append(_esc(body))
    lines.append("")

    # --- разбор: почему такой вердикт ---
    if analysis["verdict"] != "ok" and analysis["why"]:
        lines.append("⚠️ <b>Что настораживает:</b>")
        for reason in analysis["why"][:5]:
            lines.append(f"• {_esc(reason)}")
        lines.append("")
    elif analysis["verdict"] == "ok" and analysis.get("green_why"):
        good = ", ".join(analysis["green_why"][:3])
        lines.append(f"👍 <i>{_esc(good)}</i>")
        lines.append("")

    # --- подвал ---
    src = _esc(item["source"])
    if item.get("url"):
        lines.append(f'🔗 <a href="{item["url"]}">Открыть</a>  ·  {src}')
    else:
        lines.append(f"🔗 {src}")

    msg = "\n".join(lines)
    return msg[:TG_LIMIT]


def send(text, token=None, chat_id=None):
    """Отправляет одно сообщение. Возвращает True, если ушло."""
    token = token or os.environ.get("TG_BOT_TOKEN", "").strip()
    chat_id = chat_id or os.environ.get("TG_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError(
            "Нет TG_BOT_TOKEN или TG_CHAT_ID. Локально — положи их в файл .env, "
            "на GitHub — в Settings → Secrets and variables → Actions.")

    try:
        r = requests.post(API.format(token=token), timeout=25, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        })
        if r.status_code == 429:
            wait = r.json().get("parameters", {}).get("retry_after", 5)
            print(f"    [~] Телеграм просит подождать {wait} сек")
            time.sleep(wait + 1)
            r = requests.post(API.format(token=token), timeout=25, json={
                "chat_id": chat_id, "text": text,
                "parse_mode": "HTML", "disable_web_page_preview": True})
        if not r.ok:
            print(f"    [!] Телеграм вернул ошибку {r.status_code}: {r.text[:200]}")
            return False
        return True
    except Exception as e:
        print(f"    [!] Не отправилось: {type(e).__name__}: {e}")
        return False


def find_chat_ids(token=None):
    """
    Ищет чаты, из которых боту писали. Возвращает {id: имя}.

    Бот не знает твой chat_id, пока ты сам ему не напишешь — телеграм
    сообщает его только вместе с входящим сообщением.
    """
    token = token or os.environ.get("TG_BOT_TOKEN", "").strip()
    if not token:
        return {}

    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20)
        data = r.json()
    except Exception as e:
        print(f"  Не получилось связаться с телеграмом: {e}")
        return {}

    if not data.get("ok"):
        print(f"  Телеграм ответил: {data.get('description')}")
        print("  Скорее всего токен неверный — перепроверь у @BotFather.")
        return {}

    chats = {}
    for upd in data.get("result", []):
        msg = upd.get("message") or upd.get("channel_post") or {}
        chat = msg.get("chat") or {}
        if chat.get("id"):
            name = chat.get("username") or chat.get("first_name") or chat.get("title", "")
            chats[chat["id"]] = name
    return chats


def show_chat_id(token=None):
    """Печатает найденные chat_id — для запуска из терминала."""
    token = token or os.environ.get("TG_BOT_TOKEN", "").strip()
    if not token:
        print("Сначала пропиши TG_BOT_TOKEN в файле .env")
        return

    chats = find_chat_ids(token)
    if not chats:
        print("Бот пока не получил ни одного сообщения.\n"
              "Открой телеграм, найди своего бота, нажми «Запустить» (/start)\n"
              "и запусти эту команду ещё раз.")
        return

    print("Нашёл вот такие чаты:\n")
    for cid, name in chats.items():
        print(f"    TG_CHAT_ID={cid}      ({name})")
    print("\nСкопируй нужную строку в файл .env")


def send_summary(stats, token=None, chat_id=None):
    """Короткий итог запуска — чтобы понимать, что радар живой."""
    if not stats["sent"]:
        return
    text = (f"📊 <b>Итог</b>: отправлено {stats['sent']} "
            f"(норм {stats['ok']}, сомнительных {stats['suspicious']})\n"
            f"Просмотрено {stats['total']}, отсеяно {stats['filtered']}, "
            f"скам {stats['scam']}")
    send(text, token, chat_id)
