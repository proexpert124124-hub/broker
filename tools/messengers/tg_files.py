#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tg_files.py: переносимый клиент мессенджеров. См. README.md рядом."""
import base64
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live
import wa

HELP = __doc__

# Что чем является. Документы и фото лежат отдельно: инвестор смотрит
# фото, а юрист — выписки, смешивать их в одной куче неудобно.
РАЗДЕЛЫ = [
    ("Документы", (".pdf", ".doc", ".docx", ".rtf", ".xls", ".xlsx", ".zip", ".rar")),
    ("Фото", (".jpg", ".jpeg", ".png", ".heic", ".webp")),
]

# Голосовые не качаем — их расшифровывает Telegram.
# Видео не качаем вовсе: тяжёлые, и что из них нужно — решает владелец,
# скрипт только перечисляет их, чтобы было видно, что забрать руками.
ГОЛОС = (".ogg", ".oga", ".mp3", ".m4a", ".wav")
ВИДЕО = (".mp4", ".mov", ".avi", ".mkv", ".webm")


def голосовое(m):
    info = m.get("media") or {}
    имя = (info.get("name") or "").lower()
    mime = (info.get("mime") or "").lower()
    return (mime.startswith("audio/") or имя.endswith(ГОЛОС)
            or info.get("kind") in ("MessageMediaDocument.voice", "voice"))


def видео(m):
    info = m.get("media") or {}
    имя = (info.get("name") or "").lower()
    mime = (info.get("mime") or "").lower()
    return mime.startswith("video/") or имя.endswith(ВИДЕО)


def раздел(имя):
    ext = os.path.splitext(имя)[1].lower()
    for название, exts in РАЗДЕЛЫ:
        if ext in exts:
            return название
    return "Прочее"


def чисто(s):
    """Имя файла без слэшей и служебных символов."""
    s = re.sub(r"[\\/:*?\"<>|]+", " ", str(s or "")).strip()
    return re.sub(r"\s+", " ", s)


def повернуть(путь):
    """Разворачивает фото по EXIF. Без Pillow — просто пропускает."""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return False
    try:
        with Image.open(путь) as im:
            fixed = ImageOps.exif_transpose(im)
            if fixed is not im:
                fixed.save(путь, quality=95)
                return True
    except Exception:
        pass
    return False


def расшифровать(chat_id, msg_id):
    r = live.get(f"/tg/transcribe?id={urllib.parse.quote(str(chat_id))}&msg={msg_id}")
    if isinstance(r, dict) and r.get("error"):
        return None, r["error"]
    if r.get("pending"):
        return None, "Telegram ещё расшифровывает, попробовать позже"
    return (r.get("text") or "").strip(), None


def скачать(chat_id, msg_id):
    r = live.get(f"/tg/media?id={urllib.parse.quote(str(chat_id))}&msg={msg_id}")
    if isinstance(r, dict) and r.get("error"):
        raise RuntimeError(r["error"])
    return r


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "помощь"):
        print(HELP)
        return 0

    чат = argv[0]
    дата = None
    папка = None
    i = 1
    while i < len(argv):
        if argv[i] == "--дата":
            дата = argv[i + 1]
            i += 2
        elif argv[i] == "--папка":
            папка = argv[i + 1]
            i += 2
        else:
            i += 1

    chat_id, имя_чата = live.find("tg", чат)
    msgs = live.messages("tg", chat_id, 200)

    if "media" not in (msgs[0] if msgs else {}):
        raise SystemExit(
            "Мост не отдаёт вложения — на Маке стоит старая версия sync/bridge.py.\n"
            "Проверить версию основного моста по tools/messengers/README.md."
        )

    сюда = папка or os.path.join(wa.BASE if hasattr(wa, "BASE") else ".",
                                 ".messengers", "Файлы", чисто(имя_чата))
    сюда = os.path.abspath(сюда)

    отобрано = [m for m in msgs if m.get("media")
                and (not дата or str(m.get("time", "")).startswith(дата))]
    if not отобрано:
        print(f"Вложений не нашлось: {имя_чата}" + (f", дата {дата}" if дата else ""))
        return 0

    голоса = [m for m in отобрано if голосовое(m)]
    видосы = [m for m in отобрано if видео(m) and not голосовое(m)]
    файлы = [m for m in отобрано
             if not голосовое(m) and not видео(m)]
    print(f"{имя_чата}: файлов {len(файлы)}, голосовых {len(голоса)}, "
          f"видео {len(видосы)} (не качаем) → {сюда}")
    счёт = {}
    сохранено, ошибок, повёрнуто = 0, 0, 0

    for m in файлы:
        try:
            f = скачать(chat_id, m["id"])
        except Exception as e:
            print(f"  ✗ сообщение {m['id']}: {e}")
            ошибок += 1
            continue
        if f.get("error"):
            print(f"  ✗ сообщение {m['id']}: {f['error']}")
            ошибок += 1
            continue

        исходное = f.get("name") or f"{m['id']}.bin"
        группа = раздел(исходное)
        счёт[группа] = счёт.get(группа, 0) + 1
        ext = os.path.splitext(исходное)[1].lower() or ".bin"
        день = str(m.get("time", ""))[:10].replace(".", "-")
        # Имя: раздел, порядковый номер и дата — файлы сортируются
        # по порядку присылки, а не по случайному имени из Telegram
        новое = f"{группа} {счёт[группа]:02d} ({день}){ext}"

        каталог = os.path.join(сюда, группа)
        os.makedirs(каталог, exist_ok=True)
        путь = os.path.join(каталог, новое)
        with open(путь, "wb") as fh:
            fh.write(base64.b64decode(f["base64"]))
        сохранено += 1
        if группа == "Фото" and повернуть(путь):
            повёрнуто += 1
        print(f"  ✓ {группа}/{новое}   ({исходное}, {f.get('size', 0)} байт)")

    if голоса:
        # Расшифровку печатаем, а не кладём файлом: голосовое нужно понять
        # и учесть в карточке, в папку сделки оно не идёт — там только
        # то, что показывают инвестору.
        print(f"\nГолосовые ({len(голоса)}) — расшифровка, в папку не сохраняется:")
        for m in голоса:
            текст, беда = расшифровать(chat_id, m["id"])
            кто = "мы" if m.get("out") else (m.get("sender") or имя_чата)
            print(f"\n  {m.get('time', '')} · {кто}")
            print(f"  {текст}" if текст else f"  [не расшифровано: {беда}]")
        print()

    if видосы:
        print(f"\nВидео не скачано — забрать из Telegram вручную ({len(видосы)}):")
        for m in видосы:
            имя = ((m.get("media") or {}).get("name")) or "без имени"
            print(f"  · {m.get('time', '')} — {имя}")

    print(f"\nСохранено файлов: {сохранено}, развёрнуто по EXIF: {повёрнуто}, ошибок: {ошибок}")
    for группа, n in sorted(счёт.items()):
        print(f"  {группа}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
