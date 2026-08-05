# -*- coding: utf-8 -*-
"""
СЛУШАТЕЛЬ ЧАТОВ — ловит живых заказчиков там, где они реально пишут

В отличие от sources.py, который читает ПУБЛИЧНЫЕ каналы без входа
в аккаунт, этот файл работает иначе: твой бот сидит ОБЫЧНЫМ УЧАСТНИКОМ
в чатах предпринимателей (ты сам его туда добавляешь) и видит все
сообщения, которые там пишут — включая «нужен сайт», «посоветуйте
веб-студию».

Это безопасно и официально: боты для того и существуют, чтобы состоять
в группах. Твой личный аккаунт при этом никак не участвует, входа
никуда делать не нужно, риска бана нет — в отличие от Telethon
(автоматизация через личный акк), которую мы сознательно не используем.

Единственное условие — у бота должен быть выключен privacy mode,
иначе Telegram отдаёт ему только сообщения, начинающиеся с /команда.
Как включить — см. README, раздел «Ловля живых клиентов в чатах».
"""

import html
import os
import time

import requests

import analyzer
import config
import notifier
import storage

API = "https://api.telegram.org/bot{token}/{method}"

# Порядковый номер последнего обработанного апдейта — чтобы Telegram
# не присылал одни и те же сообщения повторно
OFFSET_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leads_offset.txt")


def _load_offset():
    if os.path.exists(OFFSET_FILE):
        try:
            return int(open(OFFSET_FILE).read().strip())
        except ValueError:
            return 0
    return 0


def _save_offset(value):
    with open(OFFSET_FILE, "w") as f:
        f.write(str(value))


def fetch_chat_messages(token):
    """
    Забирает новые сообщения из всех чатов, где сидит бот.
    getUpdates отдаёт всё, что накопилось с прошлого раза — раз в 30 минут
    этого достаточно, отдельный вебхук не нужен.
    """
    offset = _load_offset()
    try:
        r = requests.get(API.format(token=token, method="getUpdates"), params={
            "offset": offset + 1,
            "timeout": 0,
            "allowed_updates": '["message"]',
        }, timeout=25)
        data = r.json()
    except Exception as e:
        print(f"    [!] Не получилось связаться с телеграмом: {e}")
        return []

    if not data.get("ok"):
        print(f"    [!] Телеграм ответил: {data.get('description')}")
        return []

    updates = data.get("result", [])
    if not updates:
        return []

    _save_offset(updates[-1]["update_id"])

    items = []
    for upd in updates:
        msg = upd.get("message")
        if not msg or "text" not in msg:
            continue
        chat = msg.get("chat", {})
        # только группы и супергруппы — личку и каналы не трогаем
        if chat.get("type") not in ("group", "supergroup"):
            continue

        author = msg.get("from", {})
        name = author.get("username") or author.get("first_name", "аноним")
        chat_title = chat.get("title", "чат")

        items.append({
            "id": f"chat:{chat['id']}:{msg['message_id']}",
            "text": msg["text"],
            "url": (f"https://t.me/{chat['username']}/{msg['message_id']}"
                   if chat.get("username") else ""),
            "source": f"💬 {chat_title}",
            "source_title": chat_title,
            "date": msg.get("date"),
            "origin": "chat",
            "author": name,
        })

    return items


def run(dry=False):
    """Отдельный проход: ищет лидов в чатах, не трогает вакансии."""
    token = os.environ.get("TG_BOT_TOKEN", "").strip()
    if not token:
        print("Нет TG_BOT_TOKEN — пропускаю поиск в чатах.")
        return

    print("\n[ЧАТЫ] Проверяю сообщения из групп, где сидит бот...")
    items = fetch_chat_messages(token)
    print(f"[ЧАТЫ] Новых сообщений: {len(items)}")

    if not items:
        return

    state = storage.load()
    found = 0

    for item in items:
        if not storage.is_new(state, item):
            continue

        # В чате пишут короткими репликами без «Требования: / Обязанности:»,
        # поэтому проверка на «это вообще вакансия» здесь неуместна —
        # сразу разбираем как потенциальный лид
        analysis = analyzer.analyze(item["text"], is_order=True)
        if analysis["category"] != "lead" or not analysis["relevant"]:
            continue

        found += 1
        print(f"  💼 [{item['source']}] {item['author']}: {item['text'][:60]}")

        if not dry:
            msg = notifier.build_message(item, analysis)
            if notifier.send(msg):
                storage.remember(state, item)
            time.sleep(config.SEND_DELAY)

    if found:
        print(f"[ЧАТЫ] Найдено потенциальных клиентов: {found}")
    else:
        print("[ЧАТЫ] Ничего похожего на заказ не нашлось.")

    if not dry:
        storage.save(state)
