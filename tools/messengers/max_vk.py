#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MAX: чаты | чат <ID> [N]. Подключение — tools/messengers/README.md."""
import asyncio
import json
import os
import sys

from config import BASE, STATE, load_access
BASE = str(BASE)
FEED = str(STATE)














def token():
    return load_access().get("MAX_TOKEN")

def device_id():
    return load_access().get("MAX_DEVICE")

async def hello_and_login(c, tok, dev):
    import uuid
    await c.invoke_method(opcode=6, payload={
        "userAgent": {
            "deviceType": "WEB", "locale": "ru_RU", "osVersion": "macOS",
            "deviceName": "messengers", "deviceLocale": "ru-RU",
            "appVersion": "25.6.8", "screen": "1470x956 2.0x",
            "timezone": "Europe/Moscow", "headerUserAgent": UA,
        },
        "deviceId": dev or str(uuid.uuid4()),
    })
    r = await c.invoke_method(opcode=19, payload={
        "interactive": True, "token": tok, "chatsSync": 0, "contactsSync": 0,
        "presenceSync": 0, "draftsSync": 0, "chatsCount": 40,
    })
    if "error" in ((r or {}).get("payload") or {}):
        raise RuntimeError(r["payload"]["error"])
    c._is_logged_in = True
    return r


# Сервер MAX отбивает «голое» подключение по вебсокету (HTTP 403): ему нужны
# заголовки настоящего браузера. Библиотека их не шлёт, поэтому подставляем
# сами и перебираем варианты — рабочий сохраняется в max_proto.json.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36")
CONNECTIONS = [
    {"host": "wss://ws-api.oneme.ru/websocket", "origin": "https://web.max.ru"},
    {"host": "wss://ws-api.oneme.ru/websocket", "origin": "https://web.oneme.ru"},
    {"host": "wss://ws-api.oneme.ru/websocket", "origin": "https://max.ru"},
    {"host": "wss://web.max.ru/websocket", "origin": "https://web.max.ru"},
]


async def open_socket(variant):
    """Подключение с заголовками браузера — иначе HTTP 403."""
    import websockets
    return await websockets.connect(
        variant["host"],
        origin=variant["origin"],
        additional_headers={
            "User-Agent": UA,
            "Accept-Language": "ru-RU,ru;q=0.9",
            "Cache-Control": "no-cache",
        },
        open_timeout=25,
    )


async def connect_client(variant=None):
    """MaxClient с нашим подключением вместо встроенного."""
    import asyncio as _a
    from vkmax.client import MaxClient
    saved = json.load(open(PROTO, encoding="utf-8")).get("connection") \
        if os.path.exists(PROTO) else None
    order = [variant] if variant else ([saved] if saved else []) + CONNECTIONS
    last = None
    for v in [x for x in order if x]:
        c = MaxClient()
        try:
            c._connection = await open_socket(v)
            c._recv_task = _a.create_task(c._recv_loop())
            return c, v
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:120]}"
    raise RuntimeError(f"MAX не пускает подключение ({last})")


async def _client():
    from vkmax.client import MaxClient
    t = token()
    if not t:
        raise RuntimeError("Нет MAX_TOKEN. Подключите хранилище по README.md.")
    c, _ = await connect_client()
    me = await hello_and_login(c, t, device_id())
    return c, me


def _fmt(ms):
    import datetime as _dt
    try:
        return _dt.datetime.fromtimestamp(int(ms) // 1000).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return ""


def _chats_from(payload):
    """Список чатов приезжает вместе с ответом на вход."""
    body = (payload or {}).get("payload") or payload or {}
    chats = body.get("chats") or []
    out = []
    for ch in chats:
        cid = ch.get("id")
        if cid is None:
            continue
        last = (ch.get("lastMessage") or {})
        group = ch.get("type") not in ("DIALOG", None)
        # У личного диалога своего названия нет — имя берём у собеседника
        # (id участника, не считая себя). Разрешаем его позже resolve_users.
        peer = None
        if not group:
            parts = ch.get("participants") or {}
            ids = [int(x) for x in parts.keys()] if isinstance(parts, dict) else list(parts or [])
            me_id = body.get("profile", {}).get("contact", {}).get("id") or \
                    body.get("profile", {}).get("id")
            peer = next((i for i in ids if i != me_id), ids[0] if ids else None)
        out.append({
            "id": cid,
            "name": str(ch.get("title") or ch.get("name") or (cid if group else "")),
            "peer": peer,
            "group": group,
            "ts": int(last.get("time", 0) or 0) // 1000,
            "time": _fmt(last.get("time", 0)),
            "last": (last.get("text") or "")[:100],
            "fromMe": False,
        })
    return out


def _name_of(contact):
    """Имя из ответа resolve_users, какой бы формы оно ни было."""
    if not isinstance(contact, dict):
        return None
    names = contact.get("names")
    if isinstance(names, list) and names:
        n = names[0]
        if isinstance(n, dict):
            full = " ".join(str(n.get(k, "")) for k in ("firstName", "lastName")).strip()
            return n.get("name") or full or None
    full = " ".join(str(contact.get(k, "")) for k in ("firstName", "lastName")).strip()
    return contact.get("name") or full or None


async def _resolve_names(c, ids):
    """id участников → имена через resolve_users (opcode 32)."""
    ids = [i for i in dict.fromkeys(ids) if i]
    if not ids:
        return {}
    names = {}
    try:
        r = await asyncio.wait_for(
            c.invoke_method(opcode=32, payload={"contactIds": ids}), timeout=30)
        body = (r or {}).get("payload") or {}
        for c_ in (body.get("contacts") or body.get("users") or []):
            cid = c_.get("id")
            nm = _name_of(c_)
            if cid and nm:
                names[int(cid)] = nm
    except Exception:
        pass
    return names


def chats():
    async def run():
        c, me = await _client()
        try:
            rows = _chats_from(me)
            peers = [r["peer"] for r in rows if not r["group"] and r.get("peer")]
            names = await _resolve_names(c, peers)
            for r in rows:
                if not r["group"] and r.get("peer") in names:
                    r["name"] = names[r["peer"]]
                elif not r["name"]:
                    r["name"] = str(r["peer"] or r["id"])
            return rows
        finally:
            try:
                c._recv_task.cancel()
                await c._connection.close()
            except Exception:
                pass
    return asyncio.run(run())


PROTO = os.path.join(FEED, "max_proto.json")


def proto():
    """Способ читать историю, подобранный sync/max_setup.py."""
    if os.path.exists(PROTO):
        return json.load(open(PROTO, encoding="utf-8")).get("history")
    return None


async def _fetch_history(c, chat_id, limit, me_id):
    """Опрос истории чата (opcode 49). Отсчёт — от времени в миллисекундах,
    идём назад (backward). Листаем страницами, пока набираем limit."""
    import time as _t
    got = {}
    frm = int(_t.time() * 1000) + 60000
    for _ in range(max(1, (limit // 100) + 1)):
        r = await asyncio.wait_for(c.invoke_method(opcode=49, payload={
            "chatId": int(chat_id), "from": frm, "forward": 0,
            "backward": min(100, limit), "getMessages": True,
        }), timeout=25)
        msgs = ((r or {}).get("payload") or {}).get("messages") or []
        if not msgs:
            break
        for m in msgs:
            mid = m.get("id") or m.get("time")
            got[mid] = m
        frm = min(int(m.get("time", frm) or frm) for m in msgs) - 1
        if len(got) >= limit:
            break
    msgs = sorted(got.values(), key=lambda m: int(m.get("time", 0) or 0))
    senders = [int(m["sender"]) for m in msgs if m.get("sender")]
    names = await _resolve_names(c, senders)
    if me_id:
        names.setdefault(int(me_id), "мы")
    out = []
    for m in msgs[-limit:]:
        sid = m.get("sender")
        out.append({
            "ts": int(m.get("time", 0) or 0) // 1000,
            "time": _fmt(m.get("time", 0)),
            "out": bool(me_id) and str(sid) == str(me_id),
            "sender": names.get(int(sid), str(sid)) if sid else "",
            "text": m.get("text"),
            "id": m.get("id"),
            "attaches": await _attaches(c, chat_id, m),
        })
    return out


async def _attaches(c, chat_id, m):
    """Вложения сообщения со ссылками на скачивание.

    Фото MAX отдаёт готовой ссылкой (baseUrl). Для документов ссылку надо
    запросить отдельно (opcode 88) — она временная, поэтому берём сразу.
    Видео только перечисляем: его не скачиваем (решение владельца от 26.08).

    У пересланных сообщений («переслано») своих attaches нет — вложения
    лежат в m["link"]["message"]["attaches"], у оригинала. Без этого
    пересланные фото/видео/документы выглядели как сообщения без вложений.
    """
    link = m.get("link") or {}
    original = link.get("message") or {}
    attaches = m.get("attaches") or original.get("attaches") or []
    # Для запроса ссылки на файл (opcode 88) нужны chatId и messageId
    # оригинала, а не пересланной копии — файл физически лежит там.
    file_chat_id = link.get("chatId", chat_id)
    file_msg_id = original.get("id", m.get("id"))
    out = []
    for a in attaches:
        kind = str(a.get("_type") or a.get("type") or "").upper()
        item = {"kind": kind.lower(), "name": a.get("name"), "size": a.get("size"), "url": None}
        if kind == "PHOTO":
            item["url"] = a.get("baseUrl") or a.get("url")
            item["name"] = item["name"] or f"{a.get('photoId') or m.get('id')}.jpg"
        elif kind == "FILE":
            try:
                r = await asyncio.wait_for(c.invoke_method(opcode=88, payload={
                    "fileId": a.get("fileId"), "chatId": int(file_chat_id),
                    "messageId": str(file_msg_id),
                }), timeout=20)
                item["url"] = ((r or {}).get("payload") or {}).get("url")
            except Exception as e:
                item["error"] = f"{type(e).__name__}"
        out.append(item)
    return out


def history(chat_id, limit=200):
    async def run():
        c, me = await _client()
        me_id = (((me or {}).get("payload") or {}).get("profile") or {}).get("contact", {}).get("id") \
            or (((me or {}).get("payload") or {}).get("profile") or {}).get("id")
        try:
            return await _fetch_history(c, chat_id, limit, me_id)
        finally:
            try:
                c._recv_task.cancel()
                await c._connection.close()
            except Exception:
                pass
    return asyncio.run(run())










if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    elif a[0] in ("вход", "login"):
        raise SystemExit("Вход MAX выполняется по QR в основном проекте; см. README.md.")
    elif a[0] in ("код", "code"):
        raise SystemExit("Вход MAX выполняется по QR в основном проекте; см. README.md.")
    elif a[0] in ("чат", "chat"):
        # чат <id> [N] — id из «чаты»
        for m in history(a[1], int(a[2]) if len(a) > 2 else 100):
            att = " ".join("[%s]" % (x.get("type") or "вложение") if isinstance(x, dict) else "[вложение]"
                           for x in (m.get("attaches") or []))
            print(f"{m['time']} · {'мы' if m['out'] else m['sender']}: {m.get('text') or ''} {att}".rstrip())
    elif a[0] in ("чаты", "chats"):
        for c in chats()[:30]:
            print(f"{str(c['id']):>18} | {c['name'][:30]:30} | {c['last']}")
    else:
        print(__doc__)
