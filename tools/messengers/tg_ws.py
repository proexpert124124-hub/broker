#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tg_ws.py: переносимый клиент мессенджеров. См. README.md рядом."""
import asyncio
import json
import os
import struct
import sys

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.network.connection.tcpobfuscated import (
    ConnectionTcpObfuscated, ObfuscatedIO)

from config import BASE, STATE, load_access
BASE = str(BASE)

DC_NAMES = {1: "pluto", 2: "venus", 3: "aurora", 4: "vesta", 5: "flora"}


class _WSReader:
    def __init__(self, ws):
        self.ws, self.buf = ws, bytearray()

    async def readexactly(self, n):
        while len(self.buf) < n:
            msg = await self.ws.recv()
            self.buf += msg if isinstance(msg, (bytes, bytearray)) else msg.encode()
        out = bytes(self.buf[:n])
        del self.buf[:n]
        return out


class _WSWriter:
    def __init__(self, ws):
        self.ws, self.buf = ws, bytearray()

    def write(self, data):
        self.buf += data

    async def drain(self):
        if self.buf:
            data, self.buf = bytes(self.buf), bytearray()
            await self.ws.send(data)

    def close(self):
        asyncio.ensure_future(self.ws.close())

    async def wait_closed(self):
        pass


class _ObfuscatedIOWithDC(ObfuscatedIO):
    """Как в Telegram Web: номер DC в байтах 60–61 заголовка."""
    def __init__(self, connection):
        self._reader = connection._reader
        self._writer = connection._writer
        codec = connection.packet_codec
        dc = connection._dc_id
        orig = ObfuscatedIO.init_header
        # Заголовок собираем заново с DC, шифр берём из стандартной функции.
        import os as _os
        from telethon.crypto import AESModeCTR
        kw = (b'PVrG', b'GET ', b'POST', b'\xee\xee\xee\xee')
        while True:
            r = _os.urandom(64)
            if r[0] != 0xef and r[:4] not in kw and r[4:8] != b'\0\0\0\0':
                break
        r = bytearray(r)
        rev = r[55:7:-1]
        enc = AESModeCTR(bytes(r[8:40]), bytes(r[40:56]))
        dec = AESModeCTR(bytes(rev[:32]), bytes(rev[32:48]))
        r[56:60] = codec.obfuscate_tag
        r[60:62] = struct.pack('<h', dc)
        r[56:64] = enc.encrypt(bytes(r))[56:64]
        self.header, self._encrypt, self._decrypt = r, enc, dec


class ConnectionWebSocket(ConnectionTcpObfuscated):
    obfuscated_io = _ObfuscatedIOWithDC

    async def _connect(self, timeout=None, ssl=None):
        from websockets.asyncio.client import connect
        name = DC_NAMES.get(self._dc_id, "venus")
        url = "wss://%s.web.telegram.org/apiws" % name
        ws = await asyncio.wait_for(
            connect(url, subprotocols=["binary"], max_size=None,
                    open_timeout=timeout or 15), timeout=(timeout or 15) + 5)
        self._ws = ws
        self._reader, self._writer = _WSReader(ws), _WSWriter(ws)
        self._codec = self.packet_codec(self)
        self._init_conn()
        await self._writer.drain()





def client(session=None):
    a = load_access()
    if session is None:
        session = a.get("TG_SESSION_CLOUD")
        if not session:
            raise SystemExit("Нет TG_SESSION_CLOUD. Подключите существующее хранилище по README.md; TG_SESSION не использовать.")
    return TelegramClient(StringSession(session), int(a.get("TG_API_ID") or 0),
                          a["TG_API_HASH"], connection=ConnectionWebSocket,
                          receive_updates=False)


def _who(m, me):
    if m.out:
        return "мы"
    s = m.sender
    return (getattr(s, "first_name", None) or getattr(s, "title", None) or "") + \
        (" " + s.last_name if getattr(s, "last_name", None) else "")


def _line(m, me):
    t = m.message or ""
    if m.media:
        t = (t + " " if t else "") + "[вложение]"
    return "%s · %s: %s" % (m.date.astimezone().strftime("%d.%m.%Y %H:%M"),
                            _who(m, me), t)


async def _find(c, q):
    if q.lstrip("-").isdigit():
        return await c.get_entity(int(q))
    ql = q.lower()
    async for d in c.iter_dialogs(limit=None):
        if ql in (d.name or "").lower():
            return d.entity
    return await c.get_entity(q)






async def main(argv):
    cmd = argv[0] if argv else "чаты"
    if cmd in ("вход", "код"):
        raise SystemExit("Вход выполняется в основном проекте; см. README.md.")
    if cmd in ("--help", "-h"):
        print("Telegram: чаты [N] | чат <имя|ID> [N] | поиск <слово> [N] | файлы <чат> <папка> [N]")
        return
    c = client()
    try:
        await c.connect()
        if not await c.is_user_authorized():
            raise SystemExit("Сессия Telegram недействительна; обновите её в основном проекте.")
        me = await c.get_me()
        if cmd == "чаты":
            n = int(argv[1]) if len(argv) > 1 else 30
            async for d in c.iter_dialogs(limit=n):
                last = (d.message.message or "[вложение]")[:70] if d.message else ""
                print("%-12s %-35s %s" % (d.id, (d.name or "")[:35], last.replace("\n", " ")))
        elif cmd == "чат":
            n = int(argv[2]) if len(argv) > 2 else 100
            e = await _find(c, argv[1])
            msgs = [m async for m in c.iter_messages(e, limit=n)]
            for m in reversed(msgs):
                print(_line(m, me))
        elif cmd == "файлы":
            # файлы <чат> <папка> [N] — фото и документы скачать, голосовые
            # расшифровать текстом, видео только перечислить (правило 26.08.2026)
            from telethon.tl.functions.messages import TranscribeAudioRequest
            e = await _find(c, argv[1])
            folder = os.path.join(BASE, argv[2])
            n = int(argv[3]) if len(argv) > 3 else 50
            videos = []
            msgs = [m async for m in c.iter_messages(e, limit=n) if m.media]
            for i, m in enumerate(reversed(msgs), 1):
                if m.voice:
                    try:
                        r = await c(TranscribeAudioRequest(peer=e, msg_id=m.id))
                        print("🎤 %s: %s" % (m.date.strftime("%d.%m %H:%M"), r.text))
                    except Exception as ex:
                        print("🎤 %s: не расшифровалось (%s)" % (m.date.strftime("%d.%m %H:%M"), ex))
                    continue
                if m.video or m.video_note:
                    videos.append(m.date.strftime("%d.%m %H:%M"))
                    continue
                sub = "Фото" if m.photo else ("Документы" if m.document else "Прочее")
                os.makedirs(os.path.join(folder, sub), exist_ok=True)
                name = m.file.name if m.file and m.file.name else "%02d%s" % (i, m.file.ext if m.file else "")
                path = await m.download_media(file=os.path.join(folder, sub, "%02d_%s" % (i, name)))
                print("📎", os.path.relpath(path, BASE))
            if videos:
                print("🎬 Видео не скачаны (забрать вручную):", ", ".join(videos))
        elif cmd == "поиск":
            n = int(argv[2]) if len(argv) > 2 else 30
            async for m in c.iter_messages(None, search=argv[1], limit=n):
                chat = await m.get_chat()
                name = getattr(chat, "title", None) or getattr(chat, "first_name", "")
                print("[%s] %s" % (name, _line(m, me)))
        else:
            print(__doc__)

    finally:
        await c.disconnect()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
