# -*- coding: utf-8 -*-
"""
ПАМЯТЬ ПАРСЕРА

Хранит, что уже было отправлено, чтобы одна и та же вакансия не пришла дважды.

Проверок две:
  1. По ID поста — от повторов при каждом запуске.
  2. По «отпечатку» текста — одну вакансию часто публикуют сразу в пяти
     каналах, и по ID это разные посты, а по смыслу одна и та же работа.
"""

import hashlib
import json
import os
import re
from datetime import datetime, timedelta

SEEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seen.json")

# Сколько дней помнить. Больше — файл пухнет, меньше — рискуем повторами.
KEEP_DAYS = 30


def fingerprint(text):
    """
    Отпечаток вакансии: убираем всё оформление и оставляем «мясо».
    Один и тот же текст с разными эмодзи и хештегами даст один отпечаток.
    """
    t = text.lower()
    t = re.sub(r"https?://\S+", "", t)          # ссылки
    t = re.sub(r"@\w+", "", t)                  # ники
    t = re.sub(r"#\w+", "", t)                  # хештеги
    t = re.sub(r"[^\w\s]", "", t, flags=re.U)   # знаки и эмодзи
    t = re.sub(r"\s+", " ", t).strip()
    return hashlib.md5(t[:300].encode("utf-8")).hexdigest()[:16]


def load():
    """Читает память с диска. Если файла нет — начинаем с чистого листа."""
    if not os.path.exists(SEEN_FILE):
        return {"ids": {}, "prints": {}}
    try:
        with open(SEEN_FILE, encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("ids", {})
        data.setdefault("prints", {})
        return data
    except Exception:
        print("[!] seen.json повреждён — начинаю с нуля")
        return {"ids": {}, "prints": {}}


def save(state):
    """Сохраняет память, попутно выбрасывая всё старше KEEP_DAYS."""
    cutoff = (datetime.utcnow() - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    for key in ("ids", "prints"):
        state[key] = {k: v for k, v in state[key].items() if v >= cutoff}
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)


def is_new(state, item):
    """Проверяет, видели ли мы это раньше."""
    if item["id"] in state["ids"]:
        return False
    if fingerprint(item["text"]) in state["prints"]:
        return False
    return True


def remember(state, item):
    """Запоминает отправленную вакансию."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    state["ids"][item["id"]] = today
    state["prints"][fingerprint(item["text"])] = today
