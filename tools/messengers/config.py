"""Shared credentials, project-local output. Never prints secret values."""
import importlib.util
import json
import os
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
STATE = BASE / '.messengers' / 'state'
KEYS = ('WAHA_URL', 'WAHA_KEY', 'WAHA_SESSION', 'TG_API_ID', 'TG_API_HASH',
        'TG_SESSION_CLOUD', 'MAX_TOKEN', 'MAX_DEVICE')


def load_access():
    """Environment wins; otherwise use existing local credential store."""
    explicit = os.environ.get('MESSENGERS_ACCESS_FILE')
    candidates = [Path(explicit).expanduser()] if explicit else [
        Path.home() / '.config' / 'messengers' / 'access.json',
        BASE / 'avito' / 'access.json',
        BASE.parent / 'credit-biznes' / 'avito' / 'access.json',
        Path.home() / 'credit-biznes' / 'avito' / 'access.json',
    ]
    data = {}
    for path in candidates:
        if not path.is_file():
            if explicit:
                raise SystemExit('MESSENGERS_ACCESS_FILE: файл недоступен.')
            continue
        try:
            with path.open(encoding='utf-8') as stream:
                content = json.load(stream)
            if not isinstance(content, dict):
                raise ValueError()
            for key in KEYS:
                if content.get(key):
                    data[key] = content[key]
        except (OSError, ValueError):
            raise SystemExit('Не удалось прочитать хранилище мессенджеров (ожидается JSON-объект).') from None
        if data or explicit:
            break
    for key in KEYS:
        if os.environ.get(key):
            data[key] = os.environ[key]
    return data


def doctor():
    data = load_access()
    groups = {'WhatsApp / мост': ('WAHA_URL', 'WAHA_KEY'),
              'Telegram напрямую': ('TG_API_ID', 'TG_API_HASH', 'TG_SESSION_CLOUD'),
              'MAX напрямую': ('MAX_TOKEN', 'MAX_DEVICE')}
    for title, keys in groups.items():
        missing = [key for key in keys if not data.get(key)]
        print(title + ': ' + ('нет ' + ', '.join(missing) if missing else 'доступы заданы'))
    for package in ('telethon', 'websockets', 'vkmax', 'PIL'):
        print(package + ': ' + ('установлен' if importlib.util.find_spec(package) else 'не установлен'))
    print('Это проверка конфигурации. Живое подключение проверяется отдельно.')


if __name__ == '__main__':
    doctor()
