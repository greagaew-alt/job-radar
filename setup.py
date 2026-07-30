# -*- coding: utf-8 -*-
"""
ПОШАГОВАЯ НАСТРОЙКА РАДАРА

Запускается двойным кликом по NASTROIT.bat.
Спрашивает токен бота, находит chat_id, проверяет связь.
"""

import os
import sys

# Консоль на русской Windows может работать в разных кодировках, и эмодзи
# в неё не влезают. errors="replace" превращает такие символы в «?»,
# вместо того чтобы ронять скрипт посреди настройки.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(HERE, ".env")


def line(char="─", width=60):
    print(char * width)


def title(text):
    print()
    line("═")
    print(f"  {text}")
    line("═")
    print()


def save_env(token, chat_id="", hh=""):
    with open(ENV, "w", encoding="utf-8") as f:
        f.write(f"TG_BOT_TOKEN={token}\n")
        f.write(f"TG_CHAT_ID={chat_id}\n")
        f.write(f"HH_TOKEN={hh}\n")


def read_env():
    """Читает уже сохранённые значения, чтобы не спрашивать их заново."""
    data = {}
    if os.path.exists(ENV):
        with open(ENV, encoding="utf-8") as f:
            for ln in f:
                if "=" in ln and not ln.strip().startswith("#"):
                    k, _, v = ln.partition("=")
                    data[k.strip()] = v.strip()
    return data


def main():
    title("НАСТРОЙКА РАДАРА ВАКАНСИЙ")

    saved = read_env()
    token = saved.get("TG_BOT_TOKEN", "")

    # ── Шаг 1: токен ──────────────────────────────────────────
    print("  ШАГ 1 из 3. Токен бота")
    line()
    print()

    if token:
        print(f"  Токен уже сохранён: {token[:12]}...{token[-4:]}")
        again = input("  Ввести другой? (нажми Enter чтобы оставить, или напиши да): ")
        if again.strip().lower() not in ("да", "y", "yes", "д"):
            print()
        else:
            token = ""

    if not token:
        print("  Открой телеграм, найди @BotFather и отправь ему:  /newbot")
        print("  Он попросит имя, потом логин (должен кончаться на bot).")
        print("  В ответ пришлёт длинную строку — это и есть токен.")
        print()
        print("  Выглядит примерно так:")
        print("  1234567890:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw")
        print()
        token = input("  Вставь сюда токен и нажми Enter: ").strip()

        if not token:
            print("\n  Пусто. Запусти файл заново.")
            return 1
        if ":" not in token or len(token) < 20:
            print("\n  Это не похоже на токен — в нём должно быть двоеточие")
            print("  и он длинный. Скопируй ещё раз из чата с @BotFather.")
            return 1

        save_env(token)
        print("\n  Токен сохранён.")

    os.environ["TG_BOT_TOKEN"] = token

    # ── Шаг 2: chat_id ────────────────────────────────────────
    print()
    print("  ШАГ 2 из 3. Разреши боту писать тебе")
    line()
    print()
    print("  Телеграм запрещает боту писать первым, пока ты сам с ним")
    print("  не заговоришь. Поэтому:")
    print()
    print("    1. Найди своего бота в поиске телеграма")
    print("    2. Нажми кнопку «Запустить» внизу экрана")
    print()
    input("  Сделал? Нажми Enter...")
    print()

    import notifier
    chat_id = ""

    for attempt in range(3):
        ids = notifier.find_chat_ids(token)
        if ids:
            if len(ids) == 1:
                chat_id = str(list(ids)[0])
                name = ids[list(ids)[0]]
                print(f"  Нашёл тебя: {name}  (id {chat_id})")
            else:
                print("  Нашлось несколько чатов:\n")
                for cid, name in ids.items():
                    print(f"      {cid}   {name}")
                print()
                chat_id = input("  Впиши нужный номер: ").strip()
            break

        print("  Бот пока не получил от тебя сообщений.")
        if attempt < 2:
            print("  Проверь, что нажал «Запустить» в чате с ботом.")
            input("  Нажми Enter чтобы проверить ещё раз...")
            print()

    if not chat_id:
        print("\n  Не получилось. Возможные причины:")
        print("    • ты не нажал «Запустить» в чате с ботом")
        print("    • токен от другого бота")
        print("  Запусти настройку заново.")
        return 1

    save_env(token, chat_id)
    os.environ["TG_CHAT_ID"] = chat_id

    # ── Шаг 3: проверка ───────────────────────────────────────
    print()
    print("  ШАГ 3 из 3. Проверка связи")
    line()
    print()

    ok = notifier.send("🛠 <b>Проверка связи</b>\n\n"
                       "Если ты это видишь — радар настроен верно.")
    if ok:
        print("  Сообщение отправлено. Загляни в телеграм.")
        print()
        line("═")
        print("  ВСЁ ГОТОВО")
        line("═")
        print()
        print("  Теперь запускай ZAPUSTIT.bat — и вакансии придут в бота.")
        print()
        print("  Чтобы радар работал сам, без твоего компьютера, —")
        print("  смотри README.md, шаги 3 и 4 про GitHub.")
    else:
        print("  Не отправилось. Ошибка выше подскажет причину.")
        return 1

    print()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n  Отменено.")
        sys.exit(1)
