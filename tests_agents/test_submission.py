"""Offline first-run and browser-boundary regression checks; no live accounts."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, AsyncMock

import httpx

from agents.model import codex_executable, ModelError
from agents.bridge import create_app
from agents.native import NativeBridge, cloud_check_passed, delivery_check_passed, native_app
from agents.native_enroll import load_base
from agents.native_setup import BootstrapError


class PortableEnrollment(unittest.TestCase):
    def test_missing_base_enrollment_initializes_the_consistent_sibling_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            native = Path(temporary) / 'native'
            base = Path(temporary) / 'switch'
            def provision(directory):
                self.assertEqual(base, directory)
                directory.mkdir()
                (directory / 'config.json').write_text(json.dumps({'agents': {'fixture': 'scoped'}}))
                (directory / 'provisioning.json').write_text(json.dumps({'owners': {'fixture': 'operator'}}))
            with patch('agents.native_enroll.setup', side_effect=provision) as setup:
                config, state = load_base(native)
            setup.assert_called_once_with(base)
            self.assertEqual('scoped', config['agents']['fixture'])
            self.assertEqual('operator', state['owners']['fixture'])

    def test_incomplete_existing_enrollment_is_preserved_and_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            (base / 'config.json').write_text('{}')
            with patch('agents.native_enroll.setup') as setup:
                with self.assertRaises(BootstrapError):
                    load_base(base / 'native', base)
            setup.assert_not_called()
            self.assertEqual('{}', (base / 'config.json').read_text())

    def test_codex_uses_explicit_override_or_path_without_machine_fallback(self):
        with patch.dict(os.environ, {'CODEX_BIN': '/operator/bin/codex'}), patch('agents.model.shutil.which', return_value='/operator/bin/codex') as find:
            self.assertEqual('/operator/bin/codex', codex_executable())
            find.assert_called_once_with('/operator/bin/codex')
        with patch.dict(os.environ, {}, clear=True), patch('agents.model.shutil.which', return_value=None) as find:
            with self.assertRaises(ModelError):
                codex_executable()
            find.assert_called_once_with('codex')


class NativeSafety(unittest.IsolatedAsyncioTestCase):
    async def test_native_start_requires_complete_enrollment_before_any_connection(self):
        with tempfile.TemporaryDirectory() as temporary:
            bridge = NativeBridge(Path(temporary))
            with patch.object(bridge.relay, '__aenter__', new_callable=AsyncMock) as connect:
                with self.assertRaises(ValueError):
                    await bridge.start()
                connect.assert_not_called()

    async def test_startup_failure_still_closes_partial_bridge_resources(self):
        class PartialBridge:
            start = AsyncMock(side_effect=RuntimeError('Scoped enrollment refused'))
            close = AsyncMock()
        bridge = PartialBridge()
        app = create_app(bridge)
        with self.assertRaises(RuntimeError):
            async with app.router.lifespan_context(app):
                self.fail('Failed startup must not begin serving requests')
        bridge.close.assert_awaited_once()

    async def test_cross_origin_or_rebinding_cannot_trigger_presenter_stage(self):
        with tempfile.TemporaryDirectory() as temporary:
            bridge = NativeBridge(Path(temporary))
            app = native_app(bridge)
            transport = httpx.ASGITransport(app=app)
            with patch.object(bridge, 'queue_stage', return_value={'status': 'queued'}) as stage:
                async with httpx.AsyncClient(transport=transport, base_url='http://127.0.0.1:4319') as client:
                    for headers in ({'Origin': 'https://unrelated.example'}, {'Origin': 'null'},
                                    {'Host': 'rebinding.example'}, {'Origin': 'http://localhost:9999'}):
                        response = await client.post('/api/native/stage', content='{"stage":"approve_cloud"}', headers=headers)
                        self.assertEqual(403, response.status_code)
                    stage.assert_not_called()
                    response = await client.post('/api/native/stage', json={'stage': 'incident'})
                    self.assertEqual(202, response.status_code)
                    stage.assert_called_once_with('incident')

    async def test_native_invalid_json_never_queues_a_stage(self):
        with tempfile.TemporaryDirectory() as temporary:
            bridge = NativeBridge(Path(temporary))
            with patch.object(bridge, 'queue_stage') as stage:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=native_app(bridge)), base_url='http://localhost:4319') as client:
                    for body in ('[]', '{not json'):
                        response = await client.post('/api/native/stage', content=body)
                        self.assertEqual(400, response.status_code)
                    response = await client.post('/api/native/stage', content='x' * 64001)
                    self.assertEqual(413, response.status_code)
                    stage.assert_not_called()

    async def test_native_case_cannot_be_reset_or_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            bridge = NativeBridge(directory)
            with self.assertRaises(ValueError):
                await bridge.reset()
            prior = directory / 'native-state.json'
            prior.write_text('{"case":"recorded-case","status":"complete"}')
            original = prior.read_bytes()
            with self.assertRaises(ValueError):
                NativeBridge(directory)
            self.assertEqual(original, prior.read_bytes())

    def test_incomplete_cloud_measurements_and_stale_chat_result_cannot_pass(self):
        for canary in ({'status': 'healthy', 'attempted': 6, 'succeeded': 6},
                       {'status': 'healthy', 'attempted': 6, 'succeeded': 6, 'results': []},
                       {'status': 'healthy', 'attempted': True, 'succeeded': True, 'results': [{'passed': True}]}):
            self.assertFalse(cloud_check_passed({'observation': {'gatewayCanary': canary}}))
        self.assertFalse(delivery_check_passed({'status': 'healthy', 'attempted': 24, 'delivered': 24, 'fresh': False}))


if __name__ == '__main__':
    unittest.main()
