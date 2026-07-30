# -*- coding: utf-8 -*-
"""
ИСТОЧНИКИ ВАКАНСИЙ

Telegram — через веб-превью канала (t.me/s/имя). Это обычная HTML-страница
с последними постами, открытая для всех. Аккаунт не нужен, риска бана нет.
Минус один: закрытые каналы и чаты так не читаются.

hh.ru — через официальное API. Оно требует токен приложения; если токена
нет, источник просто выключается и остаётся один телеграм.
"""

import html
import os
import re
import time

import requests

import config

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# Разбор HTML телеграма
POST_RE = re.compile(
    r'<div class="tgme_widget_message(?:\s[^"]*)?"[^>]*data-post="([^"]+)"(.*?)'
    r'(?=<div class="tgme_widget_message(?:\s[^"]*)?"[^>]*data-post=|\Z)', re.S)
TEXT_RE = re.compile(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', re.S)
TIME_RE = re.compile(r'<time datetime="([^"]+)"')
TITLE_RE = re.compile(r'<meta property="og:title" content="([^"]*)"')


def _strip_tags(raw):
    """HTML телеграм-поста → чистый текст с сохранением переносов строк."""
    s = re.sub(r'<br\s*/?>', '\n', raw)
    s = re.sub(r'</p>\s*<p[^>]*>', '\n\n', s)
    s = re.sub(r'<[^>]+>', '', s)
    s = html.unescape(s)
    s = re.sub(r'\n{3,}', '\n\n', s)
    return s.strip()


def fetch_telegram(channel, session, limit=None):
    """Забирает последние посты одного канала. Возвращает список вакансий."""
    limit = limit or config.POSTS_PER_CHANNEL
    url = f"https://t.me/s/{channel}"
    try:
        r = session.get(url, timeout=20, headers={"User-Agent": UA})
        r.raise_for_status()
    except Exception as e:
        print(f"    [!] @{channel}: {type(e).__name__} — пропускаю")
        return []

    page = r.text
    title_m = TITLE_RE.search(page)
    channel_title = html.unescape(title_m.group(1)) if title_m else channel

    items = []
    for post_id, block in POST_RE.findall(page):
        text_m = TEXT_RE.search(block)
        if not text_m:
            continue
        text = _strip_tags(text_m.group(1))
        if len(text) < 60:          # слишком короткое — не вакансия
            continue
        time_m = TIME_RE.search(block)
        items.append({
            "id": f"tg:{post_id}",
            "text": text,
            "url": f"https://t.me/{post_id}",
            "source": f"@{channel}",
            "source_title": channel_title,
            # полное время публикации, вида 2026-07-27T15:01:12+00:00
            "date": time_m.group(1) if time_m else "",
            "origin": "telegram",
        })

    return items[-limit:]


def fetch_all_telegram():
    """Обходит все каналы из конфига."""
    session = requests.Session()
    all_items = []
    print(f"\n[ТЕЛЕГРАМ] Каналов в списке: {len(config.CHANNELS)}")
    for ch in config.CHANNELS:
        items = fetch_telegram(ch, session)
        if items:
            print(f"    @{ch}: {len(items)} постов")
        all_items.extend(items)
        time.sleep(0.2)          # вежливая пауза, чтобы не долбить сервер
    print(f"[ТЕЛЕГРАМ] Всего собрано постов: {len(all_items)}")
    return all_items


# ─────────────────────────────────────────────────────────────────────
#  hh.ru
# ─────────────────────────────────────────────────────────────────────

def fetch_hh():
    """
    Тянет вакансии с hh.ru. Нужен токен приложения в переменной HH_TOKEN.
    Без токена возвращает пустой список — не роняя весь парсер.
    """
    if not config.HH_ENABLED:
        return []

    token = os.environ.get("HH_TOKEN", "").strip()
    if not token:
        print("\n[HH.RU] Токена нет — источник выключен (работает только телеграм).")
        return []

    session = requests.Session()
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "JobRadar/1.0 (personal use)",
    }

    items, seen_ids = [], set()
    print(f"\n[HH.RU] Запросов: {len(config.HH_QUERIES)}")
    for query in config.HH_QUERIES:
        params = {
            "text": query,
            "schedule": "remote",
            "period": config.HH_PERIOD_DAYS,
            "per_page": 50,
            "order_by": "publication_time",
        }
        if config.SKIP_SENIOR:
            params["experience"] = ["noExperience", "between1And3"]

        try:
            r = session.get("https://api.hh.ru/vacancies", params=params,
                            headers=headers, timeout=20)
            if r.status_code == 403:
                print("    [!] hh отдаёт 403 — токен недействителен или не выдан.")
                print("        Смотри README, раздел «Подключить hh.ru».")
                return []
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"    [!] «{query}»: {type(e).__name__} — пропускаю")
            continue

        found = 0
        for v in data.get("items", []):
            if v["id"] in seen_ids:
                continue
            seen_ids.add(v["id"])

            # Собираем текст, чтобы анализатор работал так же, как с телеграмом
            parts = [v["name"], v["employer"]["name"] if v.get("employer") else ""]
            snip = v.get("snippet") or {}
            parts += [snip.get("requirement") or "", snip.get("responsibility") or ""]
            sal = v.get("salary")
            if sal:
                lo, hi = sal.get("from"), sal.get("to")
                cur = sal.get("currency", "RUR").replace("RUR", "руб")
                if lo and hi:
                    parts.append(f"Зарплата: от {lo} до {hi} {cur}")
                elif lo:
                    parts.append(f"Зарплата: от {lo} {cur}")
                elif hi:
                    parts.append(f"Зарплата: до {hi} {cur}")
            exp = (v.get("experience") or {}).get("name")
            if exp:
                parts.append(f"Опыт: {exp}")

            text = "\n".join(p for p in parts if p)
            text = re.sub(r"</?highlighttext>", "", text)

            items.append({
                "id": f"hh:{v['id']}",
                "text": text,
                "url": v.get("alternate_url", ""),
                "source": "hh.ru",
                "source_title": (v.get("employer") or {}).get("name", "hh.ru"),
                "date": v.get("published_at") or "",
                "origin": "hh",
                "hh_salary": sal,
            })
            found += 1

        print(f"    «{query}»: {found} новых (всего найдено {data.get('found', 0)})")
        time.sleep(0.3)

    print(f"[HH.RU] Всего собрано: {len(items)}")
    return items


def fetch_everything():
    """Собирает всё со всех источников."""
    return fetch_all_telegram() + fetch_hh()
