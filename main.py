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
             "ok": 0, "sent": 0, "dup": 0, "money": 0, "old": 0}

    items = sources.fetch_everything()
    stats["total"] = len(items)
    if not items:
        print("\nНичего не собралось. Проверь интернет или список каналов.")
        return stats

    state = storage.load()
    print(f"\n[ПАМЯТЬ] Уже отправлено раньше: {len(state['ids'])} вакансий")

    # --- разбор ---
    candidates = []
    # Отпечатки уже отобранного в этом прогоне. Раньше от повторов внутри
    # одного запуска спасала пометка в памяти, но она делалась до отправки
    # и хоронила всё сверх лимита. Теперь память пишется после отправки,
    # а за дублями внутри прогона следит этот набор: одну и ту же вакансию
    # публикуют сразу в нескольких каналах.
    seen_now = set()
    for post in items:
        # Протухшее не разбираем вовсе: за полторы недели место занято,
        # а отклик на такую вакансию — потраченное время.
        age = notifier.age_in_days(post.get("date"))
        if age is not None and age > config.MAX_AGE_DAYS:
            stats["old"] += 1
            continue

        # Пост может оказаться дайджестом из десятка вакансий. Тогда берём
        # из него все подходящие и шлём по отдельности, а не простынёй.
        found = analyzer.extract_all(post["text"],
                                     is_order=post.get("is_order", False))

        for n, (analysis, text) in enumerate(found):
            item = post
            if text != post["text"]:
                item = dict(post, text=text, id=f"{post['id']}#{n}")

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

            mark = storage.fingerprint(item["text"])
            if mark in seen_now:
                stats["dup"] += 1
                continue
            seen_now.add(mark)

            # Запоминаем не здесь, а только после успешной отправки.
            # Иначе всё найденное сверх MAX_PER_RUN помечалось отправленным,
            # хотя в бот не уходило, — и пропадало навсегда.
            candidates.append((item, analysis))

    # Порядок отправки. Профильное — всегда первым: за один запуск уходит
    # не больше MAX_PER_RUN сообщений, и без этого лимит съедали бы
    # многочисленные вакансии SMM-щиков и копирайтеров, а веб-дизайн
    # оставался бы в хвосте очереди до следующего запуска.
    priority = {"design": 0, "frontend": 0, "vibe": 0, "project": 0, "remote": 1}
    order = {"ok": 0, "suspicious": 1, "scam": 2}
    candidates.sort(key=lambda p: (priority.get(p[1]["category"], 1),
                                   order[p[1]["verdict"]],
                                   -p[1]["trust"]))

    print(f"\n{'='*60}")
    print(f"Собрано постов:        {stats['total']}")
    print(f"Старше {config.MAX_AGE_DAYS} дней:       {stats['old']}")
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
              f"{config.MAX_PER_RUN} (лимит из config.py).")
        print(f"    Остальные {len(candidates) - config.MAX_PER_RUN} "
              f"не забыты — придут следующими запусками.\n")

    for i, (item, analysis) in enumerate(to_send, 1):
        icon = notifier.VERDICT_STYLE[analysis["verdict"]][0]
        title = item["text"].split("\n")[0][:70]
        print(f"{i:>3}. {icon} [{item['source']}] {title}")

        if dry:
            continue

        # Запоминаем только то, что реально дошло. Если телеграм ответил
        # ошибкой — вакансия останется новой и уйдёт следующим запуском.
        if notifier.send(notifier.build_message(item, analysis)):
            stats["sent"] += 1
            storage.remember(state, item)
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
