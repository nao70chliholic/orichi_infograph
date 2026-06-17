import os
import io
import importlib
import tempfile
import unittest
from unittest import mock

SAMPLE_MESSAGE = """◆FiNANCiE開運オロチトークン現在情報（2026年06月16日 06:00時点）
・オープン516日目
・メンバー数 22,725人（前日比 -9人）
・トークン価格 11.9909円（前日比 -0.0037円）
・トークン在庫 50,018枚（前日比 +8枚）
#CNPオロチ #開運オロチ..."""


import requests

class FakeResponse:
    def __init__(self, ok=True, status_code=200, data=None, content=b""):
        self.ok = ok
        self.status_code = status_code
        self._data = data
        self.content = content

    def json(self):
        return self._data

    @property
    def text(self):
        # Provide a text representation for debug printing
        if self.content:
            try:
                return self.content.decode('utf-8', errors='replace')
            except Exception:
                return str(self.content)
        return str(self._data)

    def raise_for_status(self):
        if not self.ok or (self.status_code and self.status_code >= 400):
            raise requests.HTTPError(f"{self.status_code} Error")


class DummyWebhook:
    def __init__(self, url=None):
        self.url = url
        self.files = []

    def add_file(self, file=None, filename=None):
        # Accept either bytes or file-like; capture for inspection if needed
        if hasattr(file, 'read'):
            data = file.read()
            try:
                file.seek(0)
            except Exception:
                pass
        else:
            data = file
        self.files.append((filename, data))

    def execute(self):
        # Simulate a successful webhook post
        return FakeResponse(ok=True, status_code=204)


class CliPostDryRunTest(unittest.TestCase):
    def setUp(self):
        # Ensure a clean import state
        if 'bot.cli_post_infograph' in importlib.sys.modules:
            importlib.reload(importlib.import_module('bot.cli_post_infograph'))

    def test_dry_run_writes_png_with_mocked_requests(self):
        # Prepare environment variables
        env = os.environ.copy()
        env['DISCORD_BOT_TOKEN'] = 'dummy'
        env['DISCORD_CHANNEL_ID'] = '123'
        env['DISCORD_WEBHOOK_URL'] = 'https://discord.com/api/webhooks/139/abc'

        # Patch requests.get to handle both webhook info resolution and messages fetch
        def fake_requests_get(url, *args, **kwargs):
            # webhook info URL pattern contains '/api/webhooks/'
            if '/api/webhooks/' in url and 'messages' not in url:
                return FakeResponse(ok=True, status_code=200, data={'channel_id': '123'})
            # messages API URL
            if '/messages' in url:
                # Return a list of message dicts as the Discord API would
                messages = [
                    {'content': SAMPLE_MESSAGE}
                ]
                return FakeResponse(ok=True, status_code=200, data=messages)
            return FakeResponse(ok=False, status_code=404, data={})

        # Patch discord_webhook.DiscordWebhook to avoid real network calls
        with mock.patch.dict(os.environ, env), \
             mock.patch('requests.get', side_effect=fake_requests_get), \
             mock.patch('discord_webhook.DiscordWebhook', DummyWebhook):

            # Import the module after env and mocks are in place
            module = importlib.import_module('bot.cli_post_infograph')
            importlib.reload(module)

            tmpfile = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            tmpfile.close()

            # Run main in dry-run mode; this should write the PNG to tmpfile.name
            try:
                module.main(dry_run=True, output_path=tmpfile.name)
            except SystemExit as e:
                # The script uses sys.exit(0) on success; ensure it exited cleanly
                self.assertEqual(e.code, 0)

            # Verify file exists and starts with PNG header
            with open(tmpfile.name, 'rb') as f:
                data = f.read()
            self.assertTrue(data.startswith(b'\x89PNG'))

            # Cleanup
            os.unlink(tmpfile.name)


if __name__ == '__main__':
    unittest.main()
