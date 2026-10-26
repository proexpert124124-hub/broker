#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wa_files.py: переносимый клиент мессенджеров. См. README.md рядом."""
import datetime as dt
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wa
from tg_files import раздел, чисто, повернуть

HELP = __doc__

ГОЛОС_ТИПЫ = ("ptt", "audio")
ВИДЕО_ТИПЫ = ("video",)


def тип(m):
    t = (m.get("_data") or {}).get("type") or m.get("type") or ""
    mime = ((m.get("media") or {}).get("mimetype") or "").lower()
    if t in ГОЛОС_ТИПЫ or mime.startswith("audio/"):
        return "голос"
    if t in ВИДЕО_ТИПЫ or mime.startswith("video/"):
        return "видео"
    return "файл"


def забрать(url):
    """Файл из WAHA. Адрес в ответе внутренний (localhost:3000) — подменяем
    на внешний, путь /api/files/… мост проксирует в WAHA."""
    base, key, _ = wa.settings()
    path = urllib.parse.urlsplit(url).path
    req = urllib.request.Request(base + path, headers={"X-Api-Key": key} if key else {})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "помощь"):
        print(HELP)
        return 0
    опции = {"--дата": None, "--с": None, "--папка": None, "--сколько": "200"}
    чат = []
    i = 0
    while i < len(argv):
        if argv[i] in опции:
            опции[argv[i]] = argv[i + 1]
            i += 2
        else:
            чат.append(argv[i])
            i += 1
    chat_id, имя_чата = wa.find_chat(" ".join(чат))
    rows = wa.call("GET", wa.api(f"/chats/{urllib.parse.quote(chat_id)}/messages"
                                 f"?limit={int(опции['--сколько'])}&downloadMedia=true"))
    с = dt.datetime.strptime(опции["--с"], "%d.%m.%Y") if опции["--с"] else None

    отобрано = []
    for m in rows or []:
        if not m.get("hasMedia"):
            continue
        когда = wa.when(m.get("timestamp"))
        if опции["--дата"] and not когда.startswith(опции["--дата"]):
            continue
        if с and dt.datetime.fromtimestamp(int(m.get("timestamp") or 0)) < с:
            continue
        m["_когда"] = когда
        отобрано.append(m)
    отобрано.sort(key=lambda m: m.get("timestamp") or 0)
    if not отобрано:
        print(f"Вложений не нашлось: {имя_чата}")
        return 0

    сюда = os.path.abspath(опции["--папка"] or os.path.join(wa.BASE, ".messengers", "Файлы", чисто(имя_чата)))
    файлы = [m for m in отобрано if тип(m) == "файл"]
    голоса = [m for m in отобрано if тип(m) == "голос"]
    видосы = [m for m in отобрано if тип(m) == "видео"]
    print(f"{имя_чата}: файлов {len(файлы)}, голосовых {len(голоса)}, "
          f"видео {len(видосы)} (не качаем) → {сюда}")

    счёт, сохранено, ошибок, повёрнуто = {}, 0, 0, 0
    for m in файлы:
        media = m.get("media") or {}
        if not media.get("url"):
            print(f"  ✗ {m['_когда']}: WAHA не скачал файл ({media.get('error') or 'нет ссылки'})")
            ошибок += 1
            continue
        try:
            data = забрать(media["url"])
        except (urllib.error.URLError, OSError) as e:
            print(f"  ✗ {m['_когда']}: {e}")
            ошибок += 1
            continue
        исходное = media.get("filename") or ""
        ext = os.path.splitext(исходное)[1].lower() \
            or mimetypes.guess_extension((media.get("mimetype") or "").split(";")[0]) or ".bin"
        if ext == ".jpe":
            ext = ".jpg"
        группа = раздел("x" + ext)
        счёт[группа] = счёт.get(группа, 0) + 1
        день = m["_когда"][:10].replace(".", "-")
        новое = f"{группа} {счёт[группа]:02d} ({день}){ext}"
        каталог = os.path.join(сюда, группа)
        os.makedirs(каталог, exist_ok=True)
        путь = os.path.join(каталог, новое)
        with open(путь, "wb") as fh:
            fh.write(data)
        сохранено += 1
        if группа == "Фото" and повернуть(путь):
            повёрнуто += 1
        подпись = (m.get("body") or "").replace("\n", " ")[:80]
        print(f"  ✓ {группа}/{новое}   ({исходное or media.get('mimetype')}, {len(data)} байт)"
              + (f" — «{подпись}»" if подпись else ""))

    for название, список in (("Голосовые — прослушать в WhatsApp", голоса),
                             ("Видео не скачано — забрать вручную", видосы)):
        if список:
            print(f"\n{название} ({len(список)}):")
            for m in список:
                кто = "мы" if m.get("fromMe") else имя_чата
                print(f"  · {m['_когда']} · {кто}")

    print(f"\nСохранено файлов: {сохранено}, развёрнуто по EXIF: {повёрнуто}, ошибок: {ошибок}")
    for группа, n in sorted(счёт.items()):
        print(f"  {группа}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
