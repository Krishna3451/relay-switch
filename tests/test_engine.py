import concurrent.futures
import json
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib import error, request

from engine.proof import recover, wait_settled
from engine.server import Engine, http_json


class EngineContract(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="relay-tests-")
        self.engine = Engine(self.temporary.name, port=0).start()

    def tearDown(self):
        self.engine.stop()
        self.temporary.cleanup()

    def test_01_real_message_and_stable_retry(self):
        body = {"id": "stable-human-message", "text": "A real persisted message", "author": "Avery"}
        first, retry = self.engine.submit(body), self.engine.submit(body)
        self.assertTrue(first["ok"])
        self.assertTrue(retry["ok"])
        self.assertTrue(retry["duplicate"])
        with sqlite3.connect(self.engine.db_path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM messages WHERE id=?", (body["id"],)).fetchone()[0], 1)
        conflicting = self.engine.submit({**body, "text": "Different content"})
        self.assertEqual(conflicting["status"], 409)

    def test_02_cross_owner_and_apply_credentials_denied(self):
        base = self.engine.public_url
        app = self.engine.credentials["app"]
        code, _ = http_json(base + "/api/role/cloud/observation", token=app["readToken"])
        self.assertEqual(code, 403)
        cloud = self.engine.credentials["cloud"]
        obs = self.engine.observation("cloud")
        _, proposal = http_json(base + "/api/role/cloud/tool", {"action": "propose_recovery", "args": {
            "expectedRevision": obs["revision"], "reason": "Test distinct approval boundary", "capacity": 2}}, cloud["readToken"])
        code, _ = http_json(base + "/api/role/cloud/tool", {"action": "apply_recovery", "args": {
            "proposalId": proposal["id"], "digest": proposal["digest"]}}, cloud["readToken"])
        self.assertEqual(code, 403)
        code, _ = http_json(base + "/api/role/cloud/tool", {"action": "apply_recovery", "args": {
            "proposalId": proposal["id"], "digest": "changed"}}, cloud["applyToken"])
        self.assertEqual(code, 409)

    def test_03_cannot_delete_healthy_allocation(self):
        observation = self.engine.observation("app")
        code, _ = self.engine.propose("app", {"expectedRevision": observation["revision"],
             "allocationIds": [observation["allocations"][0]["id"]], "reason": "Attempted unsafe cleanup"})
        self.assertEqual(code, 409)

    def test_04_revision_and_expiry_bound(self):
        observation = self.engine.observation("cloud")
        code, _ = self.engine.propose("cloud", {"expectedRevision": observation["revision"] - 1,
                                                "reason": "Stale test", "capacity": 8})
        self.assertEqual(code, 409)
        _, proposal = self.engine.propose("cloud", {"expectedRevision": observation["revision"], "reason": "Expiry test", "capacity": 8})
        with self.engine.lock:
            saved = next(x for x in self.engine.state["proposals"] if x["id"] == proposal["id"])
            saved["expiresAt"] = 0
        code, _ = self.engine.apply("cloud", {"proposalId": proposal["id"], "digest": proposal["digest"]})
        self.assertEqual(code, 409)

    def test_05_public_projection_contains_no_credentials(self):
        text = json.dumps(self.engine.public_state())
        for credentials in self.engine.credentials.values():
            for token in credentials.values():
                self.assertNotIn(token, text)
        self.assertNotIn(self.engine.internal_token, text)
        app, cloud = self.engine.observation("app"), self.engine.observation("cloud")
        self.assertNotIn("allocations", cloud)
        self.assertNotIn("capacity", app)

    def test_06_gateway_canary_measures_actual_http(self):
        degraded = self.engine.gateway_canary()
        self.assertEqual(degraded["attempted"], 6)
        self.assertLess(degraded["succeeded"], 6)
        self.assertEqual(degraded["status"], "degraded")
        with self.engine.lock:
            self.engine.state["cloud"]["capacity"] = 8
            self.engine.state["cloud"]["revision"] += 1
        healthy = self.engine.gateway_canary()
        self.assertEqual(healthy["succeeded"], 6)
        self.assertEqual(healthy["status"], "healthy")
        self.assertEqual(self.engine.public_state()["cloud"]["status"], "healthy")

    def test_07_concurrent_conflicting_ids_have_one_owner(self):
        with self.engine.lock:
            self.engine.state['cloud']['capacity'] = 8
        bodies = [{"id": "racing-id", "text": text, "author": "Avery"} for text in ("One", "Two")]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(self.engine.submit, bodies))
        self.assertEqual(sorted(x["status"] for x in results), [200, 409])

    def test_08_human_message_survives_probe_rows(self):
        self.engine.submit({'id': 'stable-human-message', 'text': 'Human message', 'author': 'Avery'})
        with sqlite3.connect(self.engine.db_path) as db:
            for i in range(125):
                db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?)", ("padding_" + str(i), "load_" + str(i),
                           "Probe", "Load test", "2099-01-01T00:00:00", "failed", 100, "test"))
        users = self.engine.public_state()["storyMessages"]
        self.assertIn("stable-human-message", {x["id"] for x in users})

    def test_09_cross_origin_control_and_rebinding_hosts_cannot_reset(self):
        generation = self.engine.generation
        for headers in ({'Origin': 'https://unrelated.example'}, {'Origin': 'null'}, {'Host': 'rebinding.example'}):
            req = request.Request(self.engine.public_url + '/api/demo/reset', data=b'{}', method='POST', headers=headers)
            with self.assertRaises(error.HTTPError) as raised:
                request.urlopen(req, timeout=3)
            self.assertEqual(403, raised.exception.code)
            self.assertEqual(generation, self.engine.generation)

    def test_10_reset_refuses_an_inflight_ordinary_submission(self):
        entered, release = threading.Event(), threading.Event()
        def delayed(*args, **kwargs):
            entered.set()
            if not release.wait(3):
                raise TimeoutError()
            return 200, {'persisted': True}
        with patch('engine.server.http_json', side_effect=delayed):
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(self.engine.submit, {'id': 'inflight', 'text': 'Still sending'})
                try:
                    self.assertTrue(entered.wait(2))
                    generation = self.engine.generation
                    self.assertEqual(409, self.engine.reset_demo()[0])
                    self.assertEqual(generation, self.engine.generation)
                finally:
                    release.set()
                result.result(timeout=3)
        self.assertEqual(0, self.engine.active_submissions)

    def test_11_new_sends_are_refused_during_reset_and_old_work_cannot_reserve(self):
        entered, release = threading.Event(), threading.Event()
        original = self.engine.provision_one
        generation = self.engine.generation
        def delayed(*args, **kwargs):
            entered.set()
            if not release.wait(3):
                raise TimeoutError()
            return original(*args, **kwargs)
        with patch.object(self.engine, 'provision_one', side_effect=delayed):
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                resetting = pool.submit(self.engine.reset_demo)
                try:
                    self.assertTrue(entered.wait(2))
                    blocked = self.engine.submit({'id': 'during-reset', 'text': 'Do not mix cases'})
                    self.assertEqual(503, blocked['status'])
                finally:
                    release.set()
                self.assertEqual(200, resetting.result(timeout=5)[0])
        self.assertIsNone(self.engine.provision_one(generation))
        self.assertEqual(self.engine.TARGET_WORKERS, len(self.engine.state['app']['allocations']))
        with sqlite3.connect(self.engine.db_path) as db:
            self.assertEqual(0, db.execute('SELECT COUNT(*) FROM attempts WHERE id=?', ('during-reset',)).fetchone()[0])

    def test_12_same_origin_console_can_use_the_loopback_coordination_proxy(self):
        expected = 'http://127.0.0.1:' + str(self.engine.bridge_port) + '/api/coordination'
        with patch('engine.server.http_json', return_value=(200, {'mode': 'isolated-proxy-fixture'})) as forwarded:
            req = request.Request(self.engine.public_url + '/api/coordination', headers={'Origin': self.engine.public_url})
            with request.urlopen(req, timeout=3) as response:
                self.assertEqual('isolated-proxy-fixture', json.load(response)['mode'])
            self.assertEqual(expected, forwarded.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
