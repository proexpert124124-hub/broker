"""Offline contract tests: shared access and HTTP reads without account mutation."""
import asyncio
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import config
import live
import wa


class AccessTests(unittest.TestCase):
    def test_shared_file_env_priority_and_no_unrelated_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'access.json'
            path.write_text(json.dumps({'WAHA_URL': 'https://example.invalid',
                                        'WAHA_KEY': 'file-secret', 'TG_SESSION': 'mac-only',
                                        'UNRELATED_PASSWORD': 'not-for-this-client'}))
            with patch.dict(os.environ, {'MESSENGERS_ACCESS_FILE': str(path),
                                         'WAHA_KEY': 'env-secret'}, clear=True):
                data = config.load_access()
                self.assertEqual(data['WAHA_KEY'], 'env-secret')
                self.assertNotIn('TG_SESSION', data)
                self.assertNotIn('UNRELATED_PASSWORD', data)
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    config.doctor()
                self.assertNotIn('env-secret', output.getvalue())
                self.assertNotIn('file-secret', output.getvalue())

    def test_explicit_missing_file_does_not_fall_back(self):
        with patch.dict(os.environ, {'MESSENGERS_ACCESS_FILE': '/nonexistent/messengers.json'}, clear=True):
            with self.assertRaisesRegex(SystemExit, 'файл недоступен'):
                config.load_access()

    def test_bad_json_does_not_echo_its_content(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'access.json'
            path.write_text('invalid-secret-json')
            with patch.dict(os.environ, {'MESSENGERS_ACCESS_FILE': str(path)}, clear=True):
                with self.assertRaises(SystemExit) as error:
                    config.load_access()
                self.assertNotIn('invalid-secret-json', str(error.exception))

    def test_sibling_project_reuses_store_without_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / 'other-project'
            base.mkdir()
            store = Path(directory) / 'credit-biznes' / 'avito' / 'access.json'
            store.parent.mkdir(parents=True)
            store.write_text('{"MAX_TOKEN":"shared-max-token"}')
            with patch.object(config, 'BASE', base), patch('config.Path.home', return_value=Path(directory)/'home'), patch.dict(os.environ, {}, clear=True):
                self.assertEqual(config.load_access()['MAX_TOKEN'], 'shared-max-token')
                self.assertEqual(list(base.iterdir()), [])


class ReadTests(unittest.TestCase):
    def test_bridge_read_has_auth_and_encoded_chat_id(self):
        reply = MagicMock()
        reply.__enter__.return_value.read.return_value = b'[{"id":123,"text":"hello"}]'
        with patch.object(wa, 'settings', return_value=('https://example.invalid','test-key','default')), patch('urllib.request.urlopen', return_value=reply) as request:
            self.assertEqual(live.messages('tg','-123 45',10)[0]['text'], 'hello')
            sent = request.call_args.args[0]
            self.assertEqual(sent.get_method(), 'GET')
            self.assertEqual(sent.get_header('X-api-key'), 'test-key')
            self.assertIn('id=-123%2045&limit=10', sent.full_url)

    def test_writes_rejected_before_network(self):
        with patch('urllib.request.urlopen') as request:
            with self.assertRaises(SystemExit):
                wa.call('POST', '/api/sendText', {'text':'must not send'})
            request.assert_not_called()

    def test_telegram_never_uses_mac_session(self):
        try:
            import tg_ws
        except ImportError:
            self.skipTest('optional Telegram dependencies not installed')
        with patch.object(tg_ws, 'load_access', return_value={'TG_API_ID':'1','TG_API_HASH':'hash','TG_SESSION':'mac-session'}), patch.object(tg_ws, 'TelegramClient') as client:
            with self.assertRaisesRegex(SystemExit, 'TG_SESSION_CLOUD'):
                tg_ws.client()
            client.assert_not_called()

    def test_max_uses_shared_token_without_local_token_file(self):
        import max_vk
        with patch.object(max_vk, 'load_access', return_value={'MAX_TOKEN':'test-token','MAX_DEVICE':'device'}):
            self.assertEqual(max_vk.token(), 'test-token')
            self.assertEqual(max_vk.device_id(), 'device')


if __name__ == '__main__':
    unittest.main()
