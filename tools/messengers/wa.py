#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wa.py: переносимый клиент мессенджеров. См. README.md рядом."""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from config import BASE, STATE, load_access
BASE = str(BASE)


OUT = os.path.join(BASE, ".messengers", "Переписка")
WA_DIR = os.path.join(OUT, "whatsapp")
INDEX = os.path.join(OUT, "_индекс.json")
MSGS_PER_CHAT = 300

HELP = "WhatsApp: статус | чаты [N] | чат <имя|id> | поиск <слово> | выгрузить"


# ── доступы ────────────────────────────────────────────────────────────────





def settings():
    d = load_access()
    url = os.environ.get("WAHA_URL") or d.get("WAHA_URL")
    key = os.environ.get("WAHA_KEY") or d.get("WAHA_KEY")
    session = os.environ.get("WAHA_SESSION") or d.get("WAHA_SESSION") or "default"
    if not url:
        raise SystemExit(
            "Адрес WhatsApp-сервиса не задан.\n"
            "См. tools/messengers/README.md: WAHA_URL, WAHA_KEY."
        )
    return url.rstrip("/"), key, session




# ── запросы ────────────────────────────────────────────────────────────────

def call(method, path, body=None, quiet=False):
    if method != "GET":
        raise SystemExit("Клиент поддерживает только чтение.")
    url, key, _ = settings()
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "application/json"}
    if key:
        headers["X-Api-Key"] = key
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url + path, data=data, headers=headers, method=method)
    # Бесплатный туннель иногда роняет соединение на ровном месте — пробуем ещё раз,
    # чтобы из-за одного обрыва не падала вся команда.
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError:
            break
        except Exception:
            if attempt == 2:
                break
            time.sleep(2)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")[:400]
        if "ERR_NGROK_3200" in text or "is offline" in text:
            raise SystemExit(
                f"Адрес {url} есть, но за ним ничего не отвечает — туннель не запущен.\n"
                "На Маке в Терминале:  ngrok http 3000 --url=" + url.split("//")[-1] + "\n"
                "и это окно оставить открытым. Проверить, что сам сервис жив: docker start waha"
            )
        if quiet:
            return {"_error": e.code, "_text": text}
        raise SystemExit(f"{method} {path} → HTTP {e.code}: {text}")
    except urllib.error.URLError as e:
        raise SystemExit(
            f"Сервис WhatsApp недоступен по адресу {url} ({e.reason}).\n"
            "Проверьте на Маке, что контейнер и туннель запущены — tools/messengers/README.md."
        )
    return json.loads(raw) if raw.strip() else {}


def api(path):
    """Путь внутри сессии: /api/<сессия>/…"""
    _, _, s = settings()
    return f"/api/{urllib.parse.quote(s)}{path}"


# ── вспомогательное ────────────────────────────────────────────────────────

def jid(number):
    """Телефон или id чата → id в формате WhatsApp."""
    n = str(number).strip()
    if "@" in n:
        return n
    digits = re.sub(r"[^0-9]", "", n)
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    return digits + "@c.us"


def when(ts):
    import datetime as dt
    try:
        d = dt.datetime.fromtimestamp(int(ts))
    except (TypeError, ValueError, OSError):
        return ""
    return d.strftime("%d.%m.%Y %H:%M")


def safe(name):
    return re.sub(r'[/\\:*?"<>|]', "-", str(name)).strip()[:80] or "без имени"


def chat_list(limit=200):
    rows = call("GET", api(f"/chats/overview?limit={limit}&offset=0"), quiet=True)
    if isinstance(rows, dict) and rows.get("_error"):
        rows = call("GET", api(f"/chats?limit={limit}&sortBy=conversationTimestamp&sortOrder=desc"))
    out = []
    for c in rows or []:
        last = c.get("lastMessage") or {}
        cid = c.get("id") if isinstance(c.get("id"), str) else (c.get("id") or {}).get("_serialized", "")
        out.append({
            "id": cid,
            "name": c.get("name") or (c.get("contact") or {}).get("name") or str(cid).split("@")[0],
            "group": str(cid).endswith("@g.us"),
            "ts": last.get("timestamp") or c.get("timestamp") or 0,
            "last": (last.get("body") or "").replace("\n", " ")[:70],
            "fromMe": bool(last.get("fromMe")),
        })
    out.sort(key=lambda r: r["ts"] or 0, reverse=True)
    return out


def find_chat(query):
    """По номеру, части номера или имени — один чат."""
    if re.fullmatch(r"[0-9+\-() ]{6,}", str(query)) or "@" in str(query):
        return jid(query), str(query)
    q = str(query).lower()
    hits = [c for c in chat_list() if q in c["name"].lower() or q in c["id"]]
    if not hits:
        raise SystemExit(f"Чат «{query}» не найден. Список: python3 tools/messengers/wa.py чаты")
    if len(hits) > 1:
        print("Подходит несколько, беру первый по свежести:")
        for h in hits[:6]:
            print(f"  {h['name']}  ({h['id']})")
    return hits[0]["id"], hits[0]["name"]


def messages(chat_id, limit=MSGS_PER_CHAT):
    rows = call("GET", api(f"/chats/{urllib.parse.quote(chat_id)}/messages"
                           f"?limit={limit}&downloadMedia=false"))
    msgs = []
    for m in rows or []:
        msgs.append({
            "ts": m.get("timestamp") or 0,
            "time": when(m.get("timestamp")),
            "out": bool(m.get("fromMe")),
            "sender": m.get("notifyName") or m.get("_data", {}).get("notifyName") or None,
            "text": m.get("body") or None,
            "type": m.get("type") or "",
        })
    msgs.sort(key=lambda x: x["ts"] or 0)
    return msgs


# ── команды ────────────────────────────────────────────────────────────────

def cmd_status():
    url, _, s = settings()
    d = call("GET", f"/api/sessions/{urllib.parse.quote(s)}", quiet=True)
    if d.get("_error") == 404:
        print(f"Сессия «{s}» на сервисе ещё не создана.")
        print("Создать и войти:  python3 tools/messengers/wa.py вход")
        return
    status = d.get("status", "?")
    me = d.get("me") or {}
    human = {
        "WORKING": "✅ подключено, чаты читаются",
        "SCAN_QR_R": "⏳ ждёт привязки телефона — python3 tools/messengers/wa.py вход",
        "STARTING": "⏳ запускается, повторите через полминуты",
        "STOPPED": "⏸ остановлена — python3 tools/messengers/wa.py вход",
        "FAILED": "❌ упала, нужен перезапуск контейнера на Маке",
    }.get(status, status)
    print(f"Сервис: {url}")
    print(f"Сессия: {s} — {human}")
    if me:
        print(f"Номер:  {me.get('id', '').split('@')[0]}  {me.get('pushName', '')}")
    if status == "WORKING":
        print(f"Диалогов видно: {len(chat_list())}")




def cmd_chats(limit=60):
    rows = chat_list(max(limit, 60))[:limit]
    if not rows:
        print("Диалогов не видно. Проверьте: python3 tools/messengers/wa.py статус")
        return
    for c in rows:
        kind = "группа" if c["group"] else "личный"
        who = "мы: " if c["fromMe"] else ""
        print(f"{when(c['ts']):16} | {c['name'][:26]:26} | {kind:6} | "
              f"{c['id'].split('@')[0]:>14} | {who}{c['last']}")
    print(f"\nвсего: {len(rows)}   переписка целиком: python3 tools/messengers/wa.py чат <имя или номер>")


def cmd_chat(query):
    cid, name = find_chat(query)
    msgs = messages(cid)
    print(f"# {name}   ({cid})   сообщений: {len(msgs)}\n")
    for m in msgs:
        who = "мы" if m["out"] else (m["sender"] or name)
        text = m["text"] or f"[{m['type'] or 'вложение'}]"
        print(f"{m['time']} · {who}\n{text}\n")


def cmd_search(word):
    w = str(word).lower()
    found = 0
    for c in chat_list():
        try:
            msgs = messages(c["id"], 200)
        except SystemExit:
            continue
        hits = [m for m in msgs if w in (m["text"] or "").lower()]
        if not hits:
            continue
        found += 1
        print(f"\n=== {c['name']} ({c['id'].split('@')[0]}) — совпадений {len(hits)}")
        for m in hits[-3:]:
            print(f"  {m['time']} · {'мы' if m['out'] else c['name']}: {(m['text'] or '')[:160]}")
    print(f"\nчатов со словом «{word}»: {found}")


def write_chat_file(chat, msgs, idx):
    os.makedirs(WA_DIR, exist_ok=True)
    import datetime as dt
    head = [
        "---", "type: chat", "channel: whatsapp", f"chat_id: {chat['id']}",
        f"title: {json.dumps(chat['name'], ensure_ascii=False)}",
        f"phone: {chat['id'].split('@')[0] if not chat['group'] else ''}",
        f"synced: {dt.datetime.now().strftime('%d.%m.%Y %H:%M')}",
        "tags: [chat, переписка]", "---", "",
        f"# {chat['name']}", "",
        f"Канал: **whatsapp**, id `{chat['id']}`. Сообщений: {len(msgs)}.", "",
    ]
    body = []
    for m in msgs:
        who = "**мы**" if m["out"] else (m["sender"] or chat["name"])
        body.append(f"**{m['time']}** · {who}\n{m['text'] or '_[вложение]_'}\n")
    path = os.path.join(WA_DIR, f"{safe(chat['name'])} ({safe(chat['id'].split('@')[0])}).md")
    open(path, "w", encoding="utf-8").write("\n".join(head + body))
    last = msgs[-1]
    idx["chats"][f"whatsapp:{chat['id']}"] = {
        "channel": "whatsapp", "id": chat["id"], "title": chat["name"],
        "messages": len(msgs), "last": last["time"],
        "last_text": (last["text"] or "")[:120],
    }


def cmd_sync(limit=200):
    import datetime as dt
    idx = {"chats": {}, "updated": None}
    if os.path.exists(INDEX):
        idx = json.load(open(INDEX, encoding="utf-8"))
    idx.setdefault("chats", {})
    n = 0
    for c in chat_list(limit):
        try:
            msgs = messages(c["id"])
        except SystemExit as e:
            print(f"  пропуск {c['name']}: {e}")
            continue
        if not msgs:
            continue
        write_chat_file(c, msgs[-MSGS_PER_CHAT:], idx)
        print(f"  whatsapp: {c['name'][:30]} — {len(msgs)} сообщ.")
        n += 1
    idx["updated"] = dt.datetime.now().isoformat(timespec="seconds")
    os.makedirs(OUT, exist_ok=True)
    json.dump(idx, open(INDEX, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nWhatsApp: выгружено диалогов — {n} → Переписка/whatsapp/")
    print("Выгрузка локальная; выбирайте только относящиеся к проекту материалы.")




def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help", "помощь"):
        print(HELP)
        return
    c = a[0].lower()
    if c in ("статус", "status"):
        cmd_status()
    elif c in ("чаты", "chats"):
        cmd_chats(int(a[1]) if len(a) > 1 else 60)
    elif c in ("чат", "chat"):
        cmd_chat(" ".join(a[1:]))
    elif c in ("поиск", "search"):
        cmd_search(" ".join(a[1:]))
    elif c in ("выгрузить", "sync"):
        cmd_sync()
    elif c in ("отправить", "send"):
        raise SystemExit("Отправка — только после согласования через очередь основного проекта.")
    else:
        print(HELP)


if __name__ == "__main__":
    main()
