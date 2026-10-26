#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""live.py: переносимый клиент мессенджеров. См. README.md рядом."""
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wa  # адрес, ключ и разбор ошибок берём оттуда же, что у WhatsApp

BASE = wa.BASE
OUT = wa.OUT
INDEX = wa.INDEX
HELP = "Мост: статус | тг/макс чаты [N] | тг/макс чат <имя|ID> | тг/макс поиск <слово> | выгрузить"


def get(path):
    return wa.call("GET", path)


def chats(channel, limit=100):
    rows = get(f"/{channel}/chats?limit={limit}")
    if isinstance(rows, dict) and rows.get("error"):
        raise SystemExit(f"{channel}: {rows['error']}")
    for c in rows:
        c.setdefault("time", "")
        c.setdefault("last", "")
    return rows


def messages(channel, chat_id, limit=200):
    rows = get(f"/{channel}/messages?id={urllib.parse.quote(str(chat_id))}&limit={limit}")
    if isinstance(rows, dict) and rows.get("error"):
        raise SystemExit(f"{channel}: {rows['error']}")
    return rows


def find(channel, query):
    q = str(query).lower()
    if re_int(query):
        return str(query), str(query)
    hits = [c for c in chats(channel, 300) if q in str(c.get("name", "")).lower()]
    if not hits:
        raise SystemExit(f"Чат «{query}» не найден. Список: python3 tools/messengers/live.py "
                         f"{'тг' if channel == 'tg' else 'макс'} чаты")
    if len(hits) > 1:
        print("Подходит несколько, беру первый по свежести:")
        for h in hits[:6]:
            print(f"  {h['name']}  (id {h['id']})")
    return hits[0]["id"], hits[0]["name"]


def re_int(v):
    try:
        int(str(v))
        return True
    except ValueError:
        return False


def show_chats(rows, limit):
    for c in sorted(rows, key=lambda r: r.get("ts", 0), reverse=True)[:limit]:
        kind = "группа" if c.get("group") else "личный"
        who = "мы: " if c.get("fromMe") else ""
        unread = f" ●{c['unread']}" if c.get("unread") else ""
        print(f"{c.get('time', ''):16} | {str(c.get('name', ''))[:26]:26} | {kind:6} | "
              f"{str(c.get('id')):>15} | {who}{c.get('last', '')}{unread}")
    print(f"\nвсего: {len(rows)}")


def show_chat(channel, query, limit=200):
    cid, name = find(channel, query)
    msgs = messages(channel, cid, limit)
    print(f"# {name}   (id {cid})   сообщений: {len(msgs)}\n")
    for m in msgs:
        who = "мы" if m.get("out") else (m.get("sender") or name)
        att = "".join(f"\n[{a.get('kind')}] {a.get('name') or ''}"
                      for a in (m.get("attaches") or []))
        print(f"{m.get('time', '')} · {who}\n{(m.get('text') or '') + att or '[вложение]'}\n")


def search(channel, word):
    w = str(word).lower()
    found = 0
    for c in chats(channel, 200):
        try:
            msgs = messages(channel, c["id"], 200)
        except SystemExit:
            continue
        hits = [m for m in msgs if w in (m.get("text") or "").lower()]
        if not hits:
            continue
        found += 1
        print(f"\n=== {c['name']} (id {c['id']}) — совпадений {len(hits)}")
        for m in hits[-3:]:
            who = "мы" if m.get("out") else c["name"]
            print(f"  {m.get('time', '')} · {who}: {(m.get('text') or '')[:160]}")
    print(f"\nчатов со словом «{word}»: {found}")


def who_of(m, chat):
    """Кто написал — с зацепкой для связи.

    В личной переписке хватает имени. В группе автор сообщения — чужой
    человек, и чтобы ему потом написать, нужен @username или id: по одному
    отображаемому имени Telegram никого не найдёт. Пишем их прямо в строку
    автора, рядом с именем.
    """
    if m.get("out"):
        return "**мы**"
    name = m.get("sender") or chat.get("name") or "—"
    tail = []
    if m.get("sender_username"):
        tail.append("@" + str(m["sender_username"]))
    if m.get("sender_id"):
        tail.append(f"id:{m['sender_id']}")
    return f"{name} [{', '.join(tail)}]" if tail else str(name)

def dump(channel):
    """Складывает живые чаты в «Переписка/», рядом с WhatsApp и Авито."""
    import datetime as dt
    name = {"tg": "telegram", "max": "max"}[channel]
    folder = os.path.join(OUT, name)
    os.makedirs(folder, exist_ok=True)
    idx = json.load(open(INDEX, encoding="utf-8")) if os.path.exists(INDEX) else {"chats": {}}
    idx.setdefault("chats", {})
    n = 0
    for c in chats(channel, 300):
        try:
            msgs = messages(channel, c["id"], 300)
        except SystemExit:
            continue
        if not msgs:
            continue
        head = [
            "---", "type: chat", f"channel: {name}", f"chat_id: {c['id']}",
            f"title: {json.dumps(str(c.get('name', '')), ensure_ascii=False)}",
            f"synced: {dt.datetime.now().strftime('%d.%m.%Y %H:%M')}",
            "tags: [chat, переписка]", "---", "",
            f"# {c.get('name')}", "",
            f"Канал: **{name}**, id `{c['id']}`. Сообщений: {len(msgs)}.", "",
        ]
        body = [f"**{m.get('time', '')}** · {who_of(m, c)}\n"
                f"{m.get('text') or '_[вложение]_'}\n" for m in msgs]
        path = os.path.join(folder, f"{wa.safe(c.get('name'))} ({wa.safe(c['id'])}).md")
        open(path, "w", encoding="utf-8").write("\n".join(head + body))
        last = msgs[-1]
        idx["chats"][f"{name}:{c['id']}"] = {
            "channel": name, "id": c["id"], "title": str(c.get("name", "")),
            "messages": len(msgs), "last": last.get("time", ""),
            "last_text": (last.get("text") or "")[:120],
        }
        print(f"  {name}: {str(c.get('name'))[:30]} — {len(msgs)} сообщ.")
        n += 1
    idx["updated"] = dt.datetime.now().isoformat(timespec="seconds")
    json.dump(idx, open(INDEX, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n{name}: выгружено диалогов — {n}")


CHANNELS = {"тг": "tg", "tg": "tg", "telegram": "tg",
            "макс": "max", "max": "max", "мах": "max"}


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help", "помощь"):
        return print(HELP)
    if a[0] in ("статус", "status"):
        d = get("/bridge")
        print(f"Telegram: {d.get('telegram')}")
        print(f"MAX:      {d.get('max')}")
        print(f"Почта:    {d.get('mail')}")
        print(f"WhatsApp: {d.get('waha')} (проксируется мостом)")
        return
    if a[0] in ("почта", "mail"):
        cmd = a[1] if len(a) > 1 else "письма"
        acc = next((x for x in a[2:] if "@" in x), None)
        accq = f"&acc={urllib.parse.quote(acc)}" if acc else ""
        def _row(h):
            print(f"{h.get('box','')[:18]:18} | {h['uid']:>7} | {h['date'][:16]:16} "
                  f"| {h['from'][:24]:24} | {h['subject'][:42]}")
        if cmd in ("письма", "list"):
            rows = get(f"/mail/list?limit=30{accq}")
            if isinstance(rows, dict) and rows.get("error"):
                raise SystemExit("Почта: " + rows["error"])
            for h in rows:
                _row(h)
            print(f"\nвсего: {len(rows)}   письмо: python3 tools/messengers/live.py почта письмо <uid> <ящик>")
        elif cmd in ("письмо", "get"):
            h = get(f"/mail/get?uid={a[2]}{accq}")
            print(f"Ящик: {h.get('box')}\nОт: {h.get('from')}\nТема: {h.get('subject')}\n"
                  f"Дата: {h.get('date')}\n")
            print((h.get("body") or "")[:6000])
        elif cmd in ("поиск", "search"):
            words = urllib.parse.quote(" ".join(x for x in a[2:] if "@" not in x))
            rows = get(f"/mail/search?q={words}{accq}")
            if isinstance(rows, dict) and rows.get("error"):
                raise SystemExit("Почта: " + rows["error"])
            for h in rows:
                _row(h)
            print(f"\nнайдено: {len(rows)}")
        else:
            print("почта письма | письмо <uid> <ящик> | поиск <слово>")
        return
    if a[0] in ("выгрузить", "sync"):
        for ch in ([CHANNELS[a[1]]] if len(a) > 1 else ["tg", "max"]):
            dump(ch)
        return
    if a[0] not in CHANNELS:
        return print(HELP)
    ch = CHANNELS[a[0]]
    cmd = a[1] if len(a) > 1 else "чаты"
    if cmd in ("чаты", "chats"):
        rows = chats(ch, 300)
        # В Telegram групп и каналов кратно больше, чем людей, поэтому
        # по умолчанию показываем личные — рабочие диалоги.
        if "--все" not in a:
            rows = [c for c in rows if not c.get("group")]
        n = next((int(x) for x in a[2:] if x.isdigit()), 60)
        show_chats(rows, n)
    elif cmd in ("чат", "chat"):
        show_chat(ch, " ".join(a[2:]))
    elif cmd in ("поиск", "search"):
        search(ch, " ".join(a[2:]))
    else:
        print(HELP)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        pass
