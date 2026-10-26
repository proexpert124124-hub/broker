#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""max_files.py: переносимый клиент мессенджеров. См. README.md рядом."""
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live
import tg_files


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return
    chat, day, folder = a[0], None, None
    if "--дата" in a:
        day = a[a.index("--дата") + 1]
    if "--папка" in a:
        folder = a[a.index("--папка") + 1]
    if chat.lstrip("-").isdigit():
        # id чата из `max_vk.py чаты` — напрямую из облака, без моста
        import max_vk
        cid, name = chat, chat
        msgs = max_vk.history(cid, 200)
    else:
        cid, name = live.find("max", chat)
        msgs = live.messages("max", cid, 200)
    folder = folder or os.path.join(live.BASE, ".messengers", "Файлы", tg_files.чисто(name))
    if day:
        msgs = [m for m in msgs if str(m.get("time", "")).startswith(day)]
    if not any("attaches" in m for m in msgs):
        raise SystemExit("Мост не отдаёт вложения MAX — на Маке нужен свежий "
                         "sync/max_vk.py (git pull в папке базы).")
    got, videos, n = [], [], 0
    for m in msgs:
        for at in m.get("attaches") or []:
            if at.get("kind") == "video":
                videos.append(f"{m.get('time')} видео {at.get('name') or ''}")
                continue
            if not at.get("url"):
                print(f"⚠️  {m.get('time')} {at.get('kind')} {at.get('name') or ''}: "
                      f"ссылки нет {at.get('error') or ''}")
                continue
            n += 1
            req = urllib.request.Request(at["url"], headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=60).read()
            fname = tg_files.чисто(at.get("name")) or f"{n}.bin"
            if at.get("kind") == "photo" and not fname.lower().endswith((".jpg", ".jpeg", ".png")):
                fname += ".jpg"
            sub = tg_files.раздел(fname)
            os.makedirs(os.path.join(folder, sub), exist_ok=True)
            path = os.path.join(folder, sub, f"{n:02d} {fname}")
            open(path, "wb").write(data)
            tg_files.повернуть(path)
            got.append(path)
            print(f"✅ {path}  ({len(data) // 1024} КБ)")
    print(f"\nскачано: {len(got)}")
    for v in videos:
        print("🎬 не скачано:", v)


if __name__ == "__main__":
    main()
