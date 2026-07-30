# -*- coding: utf-8 -*-
"""
ПАРСЕР УДАЛЁННЫХ ВАКАНСИЙ → ТЕЛЕГРАМ-БОТ

Запуск:
    python main.py            обычный прогон: собрать, отфильтровать, отправить
    python main.py --dry      прогон без отправки (посмотреть, что нашлось)
    python main.py --chatid   узнать свой chat_id для файла .env
    python main.py --test     отправить одно тестовое сообщение в бот
    python main.py --reset    забыть всё отправленное и начать заново
"""

import os
import sys
import time

import analyzer
import config
import notifier
import sources
import storage


def load_env():
    """Читает токены из файла .env, если он есть (для локального запуска)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def run(dry=False):
    stats = {"total": 0, "filtered": 0, "scam": 0, "suspicious": 0,
             "ok": 0, "sent": 0, "dup": 0, "money": 0}

    items = sources.fetch_everything()
    stats["total"] = len(items)
    if not items:
        print("\nНичего не собралось. Проверь интернет или список каналов.")
        return stats

    state = storage.load()
    print(f"\n[ПАМЯТЬ] Уже отправлено раньше: {len(state['ids'])} вакансий")

    # --- разбор ---
    candidates = []
    for item in items:
        analysis = analyzer.analyze(item["text"], is_order=item.get("is_order", False))

        if not analysis["relevant"]:
            stats["filtered"] += 1
            continue

        # Порог зависит от типа: разовый заказ, обычная удалёнка или
        # работа по профилю — у каждого свой, см. salary_ok()
        if not analyzer.salary_ok(analysis["salary"],
                                  is_project=analysis["is_project"] or
                                  item.get("is_order", False),
                                  category=analysis["category"]):
            stats["money"] += 1
            continue

        verdict = analysis["verdict"]
        if verdict == "scam":
            stats["scam"] += 1
            if not config.SEND_SCAM:
                continue
        elif verdict == "suspicious":
            stats["suspicious"] += 1
            if not config.SEND_SUSPICIOUS:
                continue
        else:
            stats["ok"] += 1

        if not storage.is_new(state, item):
            stats["dup"] += 1
            continue

        candidates.append((item, analysis))
        storage.remember(state, item)     # помечаем сразу, чтобы не задвоить

    # Сначала нормальные, потом сомнительные; внутри — те, где больше доверия
    order = {"ok": 0, "suspicious": 1, "scam": 2}
    candidates.sort(key=lambda p: (order[p[1]["verdict"]], -p[1]["trust"]))

    print(f"\n{'='*60}")
    print(f"Собрано постов:        {stats['total']}")
    print(f"Не по профилю:         {stats['filtered']}")
    print(f"Не прошли по деньгам:  {stats['money']}")
    print(f"Уже присылали раньше:  {stats['dup']}")
    print(f"Скам (отброшен):       {stats['scam']}")
    print(f"К отправке:            {len(candidates)}")
    print(f"{'='*60}\n")

    if not candidates:
        print("Новых подходящих вакансий нет.")
        if not dry:
            storage.save(state)
        return stats

    # --- отправка ---
    to_send = candidates[:config.MAX_PER_RUN]
    if len(candidates) > config.MAX_PER_RUN:
        print(f"[!] Нашлось {len(candidates)}, отправлю первые "
              f"{config.MAX_PER_RUN} (лимит из config.py)\n")

    for i, (item, analysis) in enumerate(to_send, 1):
        icon = notifier.VERDICT_STYLE[analysis["verdict"]][0]
        title = item["text"].split("\n")[0][:70]
        print(f"{i:>3}. {icon} [{item['source']}] {title}")

        if dry:
            continue

        if notifier.send(notifier.build_message(item, analysis)):
            stats["sent"] += 1
        time.sleep(config.SEND_DELAY)

    if dry:
        print("\n(прогон без отправки — в бот ничего не ушло, память не тронута)")
        return stats

    storage.save(state)
    print(f"\nОтправлено: {stats['sent']} из {len(to_send)}")
    return stats


def main():
    load_env()
    args = sys.argv[1:]

    if "--reset" in args:
        if os.path.exists(storage.SEEN_FILE):
            os.remove(storage.SEEN_FILE)
            print("Память очищена — следующий запуск пришлёт всё заново.")
        else:
            print("Память и так пустая.")
        return

    if "--chatid" in args:
        notifier.show_chat_id()
        return

    if "--test" in args:
        ok = notifier.send(
            "🛠 <b>Проверка связи</b>\n\nЕсли ты это видишь — бот настроен верно.")
        print("Тестовое сообщение ушло." if ok else "Не получилось, смотри ошибку выше.")
        return

    run(dry="--dry" in args)


if __name__ == "__main__":
    main()
