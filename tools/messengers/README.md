# WhatsApp, Telegram и MAX во всех проектах

Переносимая копия клиентов из `credit-biznes/sync`, версия 1.0.0.
Происхождение и контрольные суммы исходников — `SOURCE.json`.
Одинаковые команды доступны из корня каждого проекта.

## Начало работы для ИИ

1. Запустить `python3 tools/messengers/config.py`: проверяет наличие параметров,
   не выводит ключи и не подключается к аккаунтам.
2. Читать только диалоги, относящиеся к задаче. Сначала список чатов, затем
   конкретный чат по ID. Для свежей переписки использовать живое подключение.
3. Передавать пользователю короткий результат. Не объявлять соединение рабочим
   по наличию настроек: проверять реальным запросом.
4. Если доступы уже настроены в credit-biznes, использовать их через общий
   файл, не просить заново ключи и не копировать их в другой репозиторий.

## Один раз: зависимости и доступ

```bash
bash tools/messengers/setup.sh
```

Команды ниже используют созданное окружение. Для моста достаточно Python 3
из системы; Telethon и vkmax нужны только для прямых соединений, Pillow —
для поворота фото. Python 3.14 на Маке в этой поставке не проверялся.

Порядок чтения доступов: переменные окружения имеют приоритет над JSON.
Если задан `MESSENGERS_ACCESS_FILE`, читается только указанный JSON; иначе
ищется первый непустой файл из списка:

- `~/.config/messengers/access.json`;
- `avito/access.json` текущего проекта;
- `../credit-biznes/avito/access.json`;
- `~/credit-biznes/avito/access.json`.

Пример: указать **путь к уже существующему файлу**, без копирования содержимого:

```bash
export MESSENGERS_ACCESS_FILE="$HOME/credit-biznes/avito/access.json"
python3 tools/messengers/config.py
```

Файл доступов должен иметь права `600`. Если он ещё не распакован, выполнить
существующий процесс `avito/access.py` в credit-biznes. Пароли и коды не
передавать в аргументах команд и не выводить в чат. Здесь новый вход не запускается.
Настройки окружения задаются для каждой машины/облачной среды; коммит кода
сам по себе не переносит авторизацию и не открывает сеть.

Параметры: `WAHA_URL`, `WAHA_KEY`, опционально `WAHA_SESSION` (default);
`TG_API_ID`, `TG_API_HASH`, **`TG_SESSION_CLOUD`**; `MAX_TOKEN`, `MAX_DEVICE`.
`TG_SESSION` принадлежит мосту на Маке — использовать её из облака запрещено:
одновременный доступ с разных IP может аннулировать сессию. Прямые подключения
из нескольких облачных сред также требуют отдельных Telegram-сессий.
Для параллельной работы проектов использовать один существующий мост.

## Читать WhatsApp

```bash
tools/messengers/.venv/bin/python tools/messengers/wa.py статус
tools/messengers/.venv/bin/python tools/messengers/wa.py чаты 30
tools/messengers/.venv/bin/python tools/messengers/wa.py чат "имя или ID"
tools/messengers/.venv/bin/python tools/messengers/wa.py поиск "слово"
```

WhatsApp работает через существующий WAHA/HTTPS-мост на Маке или VPS.
В проектах не требуется поднимать новые контейнеры и туннели.

## Telegram и MAX напрямую

```bash
tools/messengers/.venv/bin/python tools/messengers/tg_ws.py чаты 30
tools/messengers/.venv/bin/python tools/messengers/tg_ws.py чат "имя или ID" 100
tools/messengers/.venv/bin/python tools/messengers/tg_ws.py поиск "слово" 30
tools/messengers/.venv/bin/python tools/messengers/max_vk.py чаты
tools/messengers/.venv/bin/python tools/messengers/max_vk.py чат 123456 100
```

Telegram использует Telethon поверх WebSocket, MAX — vkmax с браузерным
Origin. Это пользовательские сессии, не Bot API; доступ к аккаунтам остаётся
внешней настройкой. Протокол MAX может изменяться независимо от кода.

Если прямой доступ недоступен, Telegram и MAX читаются через тот же мост:

```bash
python3 tools/messengers/live.py статус
python3 tools/messengers/live.py тг чаты 30
python3 tools/messengers/live.py тг чат "имя или ID"
python3 tools/messengers/live.py тг поиск "слово"
python3 tools/messengers/live.py макс чаты
python3 tools/messengers/live.py макс чат "имя или ID"
```

## Вложения

```bash
tools/messengers/.venv/bin/python tools/messengers/tg_ws.py файлы 123456 ".messengers/Файлы/сделка" 50
tools/messengers/.venv/bin/python tools/messengers/tg_files.py "чат" --дата 26.10.2026 --папка ".messengers/Файлы/сделка"
tools/messengers/.venv/bin/python tools/messengers/wa_files.py "чат" --папка ".messengers/Файлы/сделка"
tools/messengers/.venv/bin/python tools/messengers/max_files.py "чат или ID" --папка ".messengers/Файлы/сделка"
```

`tg_files.py` и `wa_files.py` используют мост; `max_files.py` по числовому ID
работает напрямую, по имени — через мост. Фото и документы скачиваются;
голосовые Telegram расшифровываются текстом, видео только перечисляются.
Транскрибация может требовать Telegram Premium.

## Результаты и отправка

Выгрузки `wa.py выгрузить` и `live.py выгрузить` сохраняются локально в
`.messengers/Переписка/`, исключённой из Git. Выгрузка — ограниченный снимок,
не полная история и не источник свежих сообщений. При скачивании вложений
указывать `.messengers/Файлы/...` или разрешённое внешнее хранилище.
Не переносить все чаты и клиентские досье между проектами.

Ответы готовить черновиками. Отправка согласованных сообщений остаётся в
основном проекте: `credit-biznes/Переписка/_исходящие.json`, подтверждение
владельца `"ok": true`, затем существующий `sync/outbox.py`. Эти клиенты
не отправляют сообщения и не меняют настройки аккаунтов.

## Если соединение не работает

- Отсутствуют параметры: проверить общий файл/окружение и существующий процесс
  доступа в credit-biznes; не создавать новые аккаунты и не повторять вход без нужды.
- HTTP 401: мост достижим, проверить ключ. 404/502: проверить существующий
  мост и туннель; диагностика сервера находится в `credit-biznes/sync/Мост.md`.
- Сетевой запрет: проверить разрешения среды. Для моста нужен его HTTPS-хост,
  для Telegram — `<dc>.web.telegram.org`, для MAX — `ws-api.oneme.ru` и хосты
  вложений. Блокировку не обходить отключением прокси или TLS-проверки.
- Недействительная сессия: обновить авторизацию существующим процессом в
  credit-biznes; MAX — через QR, не повторять SMS-вход с капчей.

Локальные проверки: `python3 -m unittest discover -s tools/messengers -p 'test_*.py'`.
Они не требуют аккаунтов и не подтверждают доступ к живым сервисам.
