"""TeamChat / HarborCloud: real local HTTP, bounded capacity and durable messages.

The gateway deliberately models HTTP admission saturation, not packet loss or AWS.
Workers are logical serving allocations, not virtual machines. A timed-out real
readiness request leaves a terminal failed allocation consuming the app pool.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import hashlib
import hmac
import json
import mimetypes
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import error, parse, request
import uuid
from .http_boundary import permitted_request

ROOT = Path(__file__).resolve().parents[1]


def now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def http_json(url, body=None, token=None, timeout=4, method=None):
    headers = {"content-type": "application/json"}
    if token:
        headers["authorization"] = "Bearer " + token
    req = request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                          headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return response.status, json.load(response)
    except error.HTTPError as exc:
        try:
            value = json.load(exc)
        except (ValueError, OSError):
            value = {"error": "HTTP request failed"}
        return exc.code, value


class HTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 128


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def body(self):
        length = int(self.headers.get("content-length", "0"))
        if not 0 <= length <= 64_000:
            raise ValueError("Request body length must be between 0 and 64000 bytes")
        value = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(value, dict):
            raise ValueError("JSON object required")
        return value

    def send(self, status, value):
        data = json.dumps(value).encode()
        self.send_bytes(status, data, "application/json; charset=utf-8")

    def send_bytes(self, status, data, content_type):
        try:
            self.send_response(status)
            self.send_header("content-type", content_type)
            self.send_header("content-length", str(len(data)))
            self.send_header("cache-control", "no-store")
            self.send_header("connection", "close")
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass
        self.close_connection = True

    def do_GET(self):
        self.handle_route()

    def do_POST(self):
        self.handle_route()

    def handle_route(self):
        try:
            if not permitted_request(self.headers.get("host"), self.headers.get("origin"),
                                     method=self.command, fetch_site=self.headers.get("sec-fetch-site")):
                return self.send(403, {"error": "Loopback host and same-origin browser request required"})
            self.server.route(self)
        except (ValueError, KeyError, TypeError) as exc:
            self.send(400, {"error": str(exc)})
        except Exception as exc:
            self.server.engine.event("engine", "request_error", type(exc).__name__)
            self.send(500, {"error": "Local engine request failed", "type": type(exc).__name__})


class Engine:
    TARGET_WORKERS = 4
    MAX_ALLOCATIONS = 6
    BACKEND_DELAY = .10
    UPSTREAM_TIMEOUT = .24
    REJECT_DELAY = .40
    WORKER_WAIT = .75
    PROBE_COUNT = 24
    PROBE_CONCURRENCY = 12
    SLO_MS = 1100

    def __init__(self, directory=None, port=4318, bridge_port=4319):
        self.directory = Path(directory or ROOT / ".runtime")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.condition = threading.Condition(self.lock)
        self.operation_lock = threading.Lock()
        self.servers = []
        self.threads = []
        self.bridge_port = bridge_port
        self.main_port = port
        self.db_path = self.directory / "messages.sqlite3"
        self.state_path = self.directory / "state.json"
        self.audit_path = self.directory / "audit.jsonl"
        self.credentials = {role: {kind: secrets.token_urlsafe(24) for kind in ("readToken", "applyToken")}
                            for role in ("app", "cloud")}
        self.internal_token = secrets.token_urlsafe(24)
        self.generation = 0
        self.active_submissions = 0
        self.active_canaries = 0
        self.pending_provisions = 0
        self.resetting = False
        self._initialize_database()
        self.state = {}
        self._fresh_state()

    def _initialize_database(self):
        with sqlite3.connect(self.db_path) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, text TEXT NOT NULL, author TEXT NOT NULL, createdAt TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS attempts (attemptId TEXT PRIMARY KEY, id TEXT NOT NULL, text TEXT NOT NULL, author TEXT NOT NULL, startedAt TEXT NOT NULL, status TEXT NOT NULL, latencyMs REAL, error TEXT)")

    def _fresh_state(self):
        self.generation += 1
        self.state = {"version": 1, "scenario": {"name": "TeamChat / HarborCloud", "phase": "ready"},
                      "app": {"revision": 1, "allocations": [], "busy": [], "reconciling": False},
                      "cloud": {"revision": 1, "capacity": 1, "inFlight": 0, "admitted": 0, "rejected": 0},
                      "gatewayCanary": {"status": "unmeasured", "testedAt": None},
                      "burst": {"running": False, "id": None, "offered": 0, "completed": 0},
                      "health": {"status": "unmeasured", "testedAt": None, "attempted": 0, "delivered": 0,
                                 "successRate": None, "p95LatencyMs": None},
                      "proposals": [], "events": []}
        self.persist()

    def persist(self):
        # All callers hold the process-wide reentrant lock, or run before servers.
        temp = self.state_path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.state, indent=2))
        os.replace(temp, self.state_path)

    def event(self, company, kind, message, **extra):
        with self.lock:
            value = {"id": "event_" + uuid.uuid4().hex[:10], "at": now(), "company": company,
                     "kind": kind, "message": message, **extra}
            self.state["events"].append(value)
            self.state["events"] = self.state["events"][-250:]
            with self.audit_path.open("a") as stream:
                stream.write(json.dumps(value) + "\n")
            self.persist()
            return value

    def start(self):
        for name, route, port in (("backend", self.backend_route, 0), ("gateway", self.gateway_route, 0),
                                  ("app", self.app_route, 0), ("public", self.public_route, self.main_port)):
            server = HTTPServer(("127.0.0.1", port), Handler)
            server.route, server.engine = route, self
            self.servers.append(server)
            setattr(self, name + "_url", "http://127.0.0.1:" + str(server.server_port))
            thread = threading.Thread(target=server.serve_forever, daemon=True, name=name)
            thread.start()
            self.threads.append(thread)
        config = {"apiBase": self.public_url, "ports": {name: int(getattr(self, name + "_url").rsplit(":", 1)[1])
                  for name in ("app", "gateway", "backend", "public")}, "credentials": self.credentials,
                  "pid": os.getpid(), "bridgeBase": "http://127.0.0.1:" + str(self.bridge_port)}
        config_path = self.directory / "engine.json"
        config_path.write_text(json.dumps(config, indent=2))
        config_path.chmod(0o600)
        for _ in range(self.TARGET_WORKERS):
            self.provision_one()
        self.event("TeamChat", "ready", "Chat is serving ordinary traffic; the cloud route is at its quiet-period capacity.")
        return self

    def stop(self):
        for server in reversed(self.servers):
            server.shutdown()
            server.server_close()
        self.servers = []

    def authorized(self, handler, token):
        return hmac.compare_digest(handler.headers.get("authorization", ""), "Bearer " + token)

    def backend_route(self, handler):
        if not self.authorized(handler, self.internal_token):
            return handler.send(403, {"error": "Backend credential required"})
        time.sleep(self.BACKEND_DELAY)
        if handler.path == "/health":
            return handler.send(200, {"ready": True})
        if handler.path != "/messages":
            return handler.send(404, {"error": "Unknown backend route"})
        if handler.command == "GET":
            with sqlite3.connect(self.db_path) as db:
                rows = db.execute("SELECT id,text,author,createdAt FROM messages ORDER BY createdAt").fetchall()
            return handler.send(200, {"messages": [dict(zip(("id", "text", "author", "createdAt"), row)) for row in rows]})
        body = handler.body()
        message = {key: str(body[key]) for key in ("id", "text", "author")}
        if not message["id"] or not message["text"] or len(message["id"]) > 160 or len(message["text"]) > 2000:
            raise ValueError("A short ID and message text are required")
        with sqlite3.connect(self.db_path, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT text,author FROM messages WHERE id=?", (message["id"],)).fetchone()
            if existing and existing != (message["text"], message["author"]):
                return handler.send(409, {"error": "Message ID already belongs to different content"})
            duplicate = existing is not None
            db.execute("INSERT OR IGNORE INTO messages VALUES (?,?,?,?)", (*message.values(), now()))
        return handler.send(200, {"ok": True, "id": message["id"], "duplicate": duplicate, "persisted": True})

    def gateway_route(self, handler):
        if not self.authorized(handler, self.internal_token):
            return handler.send(403, {"error": "Route credential required"})
        with self.lock:
            generation = self.generation
            cloud = self.state["cloud"]
            admitted = cloud["inFlight"] < cloud["capacity"]
            cloud["admitted" if admitted else "rejected"] += 1
            if admitted:
                cloud["inFlight"] += 1
            self.persist()
        if not admitted:
            self.event("HarborCloud", "admission_timeout", "A request exceeded the route's concurrent HTTP admission capacity.")
            time.sleep(self.REJECT_DELAY)
            return handler.send(503, {"error": "Gateway admission capacity exhausted"})
        try:
            body = handler.body() if handler.command == "POST" else None
            status, result = http_json(self.backend_url + handler.path, body, self.internal_token, timeout=3,
                                       method=handler.command)
            return handler.send(status, result)
        finally:
            with self.lock:
                if generation == self.generation:
                    self.state["cloud"]["inFlight"] -= 1
                    self.persist()

    def provision_one(self, expected_generation=None):
        with self.lock:
            if expected_generation is not None and expected_generation != self.generation:
                return None
            if len(self.state["app"]["allocations"]) >= self.MAX_ALLOCATIONS:
                return None
            generation = self.generation
            item = {"id": "worker_" + uuid.uuid4().hex[:8], "status": "provisioning", "createdAt": now(),
                    "checkedAt": None, "lastError": None}
            self.state["app"]["allocations"].append(item)
            self.state["app"]["revision"] += 1
            self.persist()
        started = time.monotonic()
        try:
            code, value = http_json(self.gateway_url + "/health", token=self.internal_token, timeout=self.UPSTREAM_TIMEOUT)
            ready = code == 200 and value.get("ready") is True
            failure = None if ready else "Readiness returned HTTP " + str(code)
        except (OSError, error.URLError, TimeoutError):
            ready, failure = False, "Readiness HTTP request timed out"
        with self.condition:
            if generation != self.generation:
                return None
            item.update(status="ready" if ready else "failed", checkedAt=now(), lastError=failure,
                        readinessMs=round((time.monotonic() - started) * 1000, 2))
            self.state["app"]["revision"] += 1
            self.persist()
            self.condition.notify_all()
        self.event("TeamChat", "worker_ready" if ready else "provisioning_failed",
                   "Worker passed its actual backend readiness request." if ready else
                   "Worker's actual readiness request failed; its allocation still occupies a pool slot.", allocationId=item["id"])
        return item

    def maybe_provision(self):
        with self.lock:
            app = self.state["app"]
            if self.resetting or app["reconciling"] or len(app["allocations"]) + self.pending_provisions >= self.MAX_ALLOCATIONS:
                return
            # A real queued request triggers replacement/scale-up; no oracle fault flag.
            # Bound scheduled work before spawning, and refuse old-generation work
            # if a reset happened before a queued thread acquired the lock.
            generation = self.generation
            self.pending_provisions += 1
            def run():
                try:
                    self.provision_one(generation)
                finally:
                    with self.lock:
                        self.pending_provisions -= 1
            threading.Thread(target=run, daemon=True).start()

    def app_route(self, handler):
        if handler.path == "/health":
            return handler.send(200, {"up": True})
        if handler.path != "/messages":
            return handler.send(404, {"error": "Unknown application route"})
        body = handler.body() if handler.command == "POST" else None
        started = time.monotonic()
        deadline = started + self.WORKER_WAIT
        worker = None
        with self.condition:
            if self.resetting:
                return handler.send(503, {"error": "A local reset is running"})
            generation = self.generation
            while worker is None and time.monotonic() < deadline:
                if generation != self.generation:
                    return handler.send(503, {"error": "The previous local demonstration was reset"})
                app = self.state["app"]
                worker = next((item for item in app["allocations"] if item["status"] == "ready" and item["id"] not in app["busy"]), None)
                if worker:
                    app["busy"].append(worker["id"])
                    break
                self.maybe_provision()
                self.condition.wait(.025)
            self.persist()
        if worker is None:
            return handler.send(503, {"error": "No serving worker became available before the request deadline"})
        upstream_failed = False
        try:
            status, value = http_json(self.gateway_url + "/messages", body, self.internal_token,
                                      timeout=self.UPSTREAM_TIMEOUT, method=handler.command)
            upstream_failed = status >= 500
            return handler.send(status, value)
        except (OSError, error.URLError, TimeoutError):
            upstream_failed = True
            return handler.send(504, {"error": "Backend HTTP request timed out"})
        finally:
            with self.condition:
                if generation == self.generation:
                    app = self.state["app"]
                    if worker["id"] in app["busy"]:
                        app["busy"].remove(worker["id"])
                    if upstream_failed:
                        # A separate real readiness HTTP attempt determines terminal failure.
                        worker["status"] = "checking"
                    self.condition.notify_all()
                    self.persist()
            if upstream_failed:
                self.recheck_worker(worker, generation)

    def recheck_worker(self, worker, generation):
        try:
            status, result = http_json(self.gateway_url + "/health", token=self.internal_token, timeout=self.UPSTREAM_TIMEOUT)
            ready = status == 200 and result.get("ready") is True
        except (OSError, error.URLError, TimeoutError):
            ready = False
        with self.condition:
            if generation != self.generation:
                return
            worker.update(status="ready" if ready else "failed", checkedAt=now(),
                          lastError=None if ready else "Actual backend readiness request failed after serving timeout")
            self.state["app"]["revision"] += 1
            self.persist()
            self.condition.notify_all()
        if not ready:
            self.event("TeamChat", "worker_failed", "A serving worker failed its backend readiness check and is awaiting reconciliation.", allocationId=worker["id"])
            self.maybe_provision()

    def submit(self, body):
        with self.lock:
            if self.resetting:
                return {"ok": False, "id": str(body.get("id") or ""), "status": 503,
                        "latencyMs": 0, "duplicate": False, "error": "A local reset is running; retry after it completes"}
            self.active_submissions += 1
        try:
            return self._submit(body)
        finally:
            with self.lock:
                self.active_submissions -= 1

    def _submit(self, body):
        message = {"id": str(body.get("id") or "message_" + uuid.uuid4().hex),
                   "text": str(body.get("text", "")), "author": str(body.get("author") or "You")}
        if not message["text"] or len(message["text"]) > 2000 or len(message["id"]) > 160:
            raise ValueError("Message text (1–2000 characters) and a short id are required")
        attempt_id, began = "attempt_" + uuid.uuid4().hex, now()
        with sqlite3.connect(self.db_path, timeout=10) as db:
            db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?)", (attempt_id, message["id"], message["text"],
                       message["author"], began, "pending", None, None))
        start = time.monotonic()
        try:
            code, value = http_json(self.app_url + "/messages", message, timeout=4)
        except (OSError, error.URLError, TimeoutError):
            code, value = 504, {"error": "Application request timed out"}
        latency = round((time.monotonic() - start) * 1000, 2)
        ok = code == 200 and value.get("persisted") is True
        with sqlite3.connect(self.db_path, timeout=10) as db:
            db.execute("UPDATE attempts SET status=?,latencyMs=?,error=? WHERE attemptId=?",
                       ("delivered" if ok else "failed", latency, value.get("error"), attempt_id))
        return {"ok": ok, "id": message["id"], "status": code, "latencyMs": latency,
                "duplicate": value.get("duplicate", False), "error": value.get("error")}

    def workload(self, count=None, concurrency=None, label="Load test", story_message=None):
        count, concurrency = count or self.PROBE_COUNT, concurrency or self.PROBE_CONCURRENCY
        run_id = "load_" + uuid.uuid4().hex[:8]
        began = time.monotonic()
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
            offered = [{"id": run_id + "_" + str(i), "text": "Delivery check " + str(i + 1), "author": label}
                       for i in range(count)]
            if story_message:
                # One expressly submitted message participates in ordinary offered traffic.
                # Its outcome is never forced; if it succeeds, choose an actually failed
                # recorded message to demonstrate a retry instead.
                offered[-1] = story_message
            with self.lock:
                if self.state["burst"]["running"]:
                    self.state["burst"]["id"] = run_id
            futures = [pool.submit(self.submit, message) for message in offered]
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())
                with self.lock:
                    if self.state["burst"]["id"] == run_id:
                        self.state["burst"]["completed"] = len(results)
        latencies = sorted(item["latencyMs"] for item in results)
        delivered = sum(item["ok"] for item in results)
        p95 = latencies[max(0, __import__("math").ceil(.95 * len(latencies)) - 1)]
        result = {"id": run_id, "status": "healthy" if delivered == count and p95 <= self.SLO_MS else "degraded",
                  "testedAt": now(), "attempted": count, "delivered": delivered, "successRate": round(delivered / count, 4),
                  "p95LatencyMs": p95, "durationMs": round((time.monotonic() - began) * 1000, 2),
                  "concurrency": concurrency, "sloMs": self.SLO_MS, "results": results}
        with self.lock:
            result["appRevision"] = self.state["app"]["revision"]
            result["cloudRevision"] = self.state["cloud"]["revision"]
            self.state["health"] = {k: v for k, v in result.items() if k != "results"}
            self.state["scenario"]["phase"] = "recovered" if result["status"] == "healthy" else "incident"
            self.persist()
        return result

    def gateway_canary(self):
        """Independent real gateway HTTP check; bypasses TeamChat's serving pool."""
        with self.lock:
            if self.resetting:
                raise ValueError("Wait for the local reset to finish before probing the gateway")
            self.active_canaries += 1
        try:
            return self._gateway_canary()
        finally:
            with self.lock:
                self.active_canaries -= 1

    def _gateway_canary(self):
        with self.lock:
            revision = self.state["cloud"]["revision"]
        barrier = threading.Barrier(self.MAX_ALLOCATIONS)
        def one():
            barrier.wait(timeout=2)
            started = time.monotonic()
            try:
                code, body = http_json(self.gateway_url + "/health", token=self.internal_token, timeout=self.UPSTREAM_TIMEOUT)
                passed = code == 200 and body.get("ready") is True
            except (OSError, error.URLError, TimeoutError):
                code, passed = 504, False
            return {"httpStatus": code, "passed": passed, "latencyMs": round((time.monotonic() - started) * 1000, 2)}
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.MAX_ALLOCATIONS) as pool:
            results = list(pool.map(lambda _: one(), range(self.MAX_ALLOCATIONS)))
        result = {"status": "healthy" if all(x["passed"] for x in results) else "degraded", "testedAt": now(),
                  "cloudRevision": revision, "concurrency": self.MAX_ALLOCATIONS,
                  "attempted": len(results), "succeeded": sum(x["passed"] for x in results), "results": results,
                  "scope": "Six actual concurrent gateway-to-backend readiness requests; does not establish TeamChat message delivery."}
        with self.lock:
            self.state["gatewayCanary"] = result
            self.persist()
        return result

    def burst(self, story_message=None):
        with self.lock:
            if self.resetting or self.state["burst"]["running"] or self.state["app"]["reconciling"]:
                raise ValueError("A load test or recovery is already running")
            self.state["burst"] = {"running": True, "id": "starting", "offered": self.PROBE_COUNT, "completed": 0}
            self.persist()
        def run():
            self.event("TeamChat", "load_started", "A real concurrent message burst has started.")
            try:
                result = self.workload(story_message=story_message)
                self.event("TeamChat", "load_completed", f"{result['delivered']}/{result['attempted']} actual HTTP messages persisted; p95 {result['p95LatencyMs']} ms.")
            finally:
                with self.lock:
                    self.state["burst"]["running"] = False
                    self.state["burst"]["completed"] = self.PROBE_COUNT
                    self.persist()
        threading.Thread(target=run, daemon=True).start()
        return {"accepted": True, "burst": self.state["burst"]}

    def observation(self, role):
        with self.lock:
            if role == "app":
                app = self.state["app"]
                return {"role": role, "company": "TeamChat", "at": now(), "revision": app["revision"],
                        "targetWorkers": self.TARGET_WORKERS, "maxAllocations": self.MAX_ALLOCATIONS,
                        "readyWorkers": sum(x["status"] == "ready" for x in app["allocations"]),
                        "busyWorkers": len(app["busy"]), "allocations": json.loads(json.dumps(app["allocations"])),
                        "events": [x for x in self.state["events"] if x["company"] == "TeamChat"][-25:],
                        "allowedOperation": "reconcile_failed_allocations",
                        "operationContract": "Name only terminal failed allocation IDs at this revision. Healthy, checking and provisioning allocations cannot be removed. Reprovisioning uses actual readiness HTTP at concurrency one."}
            cloud = self.state["cloud"]
            return {"role": role, "company": "HarborCloud", "at": now(), **cloud,
                    "gatewayCanary": json.loads(json.dumps(self.state["gatewayCanary"])),
                    "maximumAllowedCapacity": 16,
                    "validationContract": {"gatewayConnectionCheck": {
                        "simultaneousRequests": self.MAX_ALLOCATIONS,
                        "requiredSuccesses": self.MAX_ALLOCATIONS,
                        "successCondition": "Every simultaneous real gateway-to-backend readiness request must succeed before this connection is called healthy.",
                        "scope": "HarborCloud's declared recovery check for this dedicated route; it does not establish TeamChat message delivery."}},
                    "events": [x for x in self.state["events"] if x["company"] == "HarborCloud"][-25:],
                    "allowedOperation": "increase_gateway_capacity",
                    "operationContract": "Propose a bounded integer capacity increase for this dedicated local route. Cannot inspect or change TeamChat allocations or messages."}

    def propose(self, role, args):
        with self.lock:
            if self.resetting:
                return 409, {"error": "Wait for the local reset to finish"}
            revision = self.state[role if role == "app" else "cloud"]["revision"]
            if args.get("expectedRevision") != revision:
                return 409, {"error": "Resource revision changed; inspect fresh evidence", "currentRevision": revision}
            if not str(args.get("reason", "")).strip():
                raise ValueError("Evidence-based reason is required")
            if role == "cloud":
                capacity = args.get("capacity")
                if isinstance(capacity, bool) or not isinstance(capacity, int) or not self.state["cloud"]["capacity"] < capacity <= 16:
                    raise ValueError("Capacity must be an integer increase up to 16")
                operation, target = "increase_gateway_capacity", {"capacity": capacity}
                summary = f"Increase this route's concurrent HTTP capacity from {self.state['cloud']['capacity']} to {capacity}."
            else:
                ids = args.get("allocationIds")
                if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)):
                    raise ValueError("A nonempty unique allocationIds list is required")
                allowed = {x["id"] for x in self.state["app"]["allocations"] if x["status"] == "failed"}
                if not set(ids) <= allowed:
                    return 409, {"error": "Only currently terminal failed allocations may be reconciled"}
                operation, target = "reconcile_failed_allocations", {"allocationIds": sorted(ids), "maxConcurrency": 1}
                summary = f"Remove {len(ids)} named terminal failed allocations, preserve healthy workers, and reprovision toward {self.TARGET_WORKERS} ready workers at concurrency one."
            value = {"id": "proposal_" + uuid.uuid4().hex[:12], "role": role, "operation": operation,
                     "expectedRevision": revision, "target": target, "reason": str(args["reason"])[:3000],
                     "createdAt": now(), "expiresAt": time.time() + 600, "summary": summary}
            value["digest"] = digest(value)
            value["status"] = "proposed"
            self.state["proposals"].append(value)
            self.persist()
            return 200, json.loads(json.dumps(value))

    def apply(self, role, args):
        if not self.operation_lock.acquire(blocking=False):
            return 409, {"error": "Another owner operation is running"}
        try:
            with self.lock:
                if self.resetting:
                    return 409, {"error": "Wait for the local reset to finish"}
                proposal = next((x for x in self.state["proposals"] if x["id"] == args.get("proposalId")), None)
                if not proposal or proposal["role"] != role:
                    return 404, {"error": "Proposal does not belong to this owner"}
                if not hmac.compare_digest(str(args.get("digest", "")), proposal["digest"]):
                    return 409, {"error": "Exact proposal digest required"}
                if proposal["status"] != "proposed":
                    return 409, {"error": "Proposal is not pending"}
                resource = self.state[role]
                if resource["revision"] != proposal["expectedRevision"] or time.time() > proposal["expiresAt"]:
                    proposal["status"] = "stale"
                    self.persist()
                    return 409, {"error": "Proposal stale or expired; inspect and propose again"}
                proposal["status"] = "applying"
                if role == "cloud":
                    self.state["cloud"]["capacity"] = proposal["target"]["capacity"]
                    self.state["cloud"]["revision"] += 1
                    self.state["gatewayCanary"]["status"] = "unmeasured"
                else:
                    ids = set(proposal["target"]["allocationIds"])
                    if any(x["status"] != "failed" for x in resource["allocations"] if x["id"] in ids):
                        return 409, {"error": "Allocation is no longer terminal failed"}
                    resource["allocations"] = [x for x in resource["allocations"] if x["id"] not in ids]
                    resource["revision"] += 1
                    resource["reconciling"] = True
                self.state["health"]["status"] = "unmeasured"
                self.persist()
            self.event("TeamChat" if role == "app" else "HarborCloud", "owner_operation_applied", proposal["summary"], proposalId=proposal["id"], proposalDigest=proposal["digest"])
            if role == "cloud":
                self.gateway_canary()
            if role == "app":
                for _ in range(self.MAX_ALLOCATIONS):
                    with self.lock:
                        ready = sum(x["status"] == "ready" for x in self.state["app"]["allocations"])
                        full = len(self.state["app"]["allocations"]) >= self.MAX_ALLOCATIONS
                    if ready >= self.TARGET_WORKERS or full:
                        break
                    self.provision_one()
                with self.lock:
                    self.state["app"]["reconciling"] = False
            with self.lock:
                proposal["status"] = "applied"
                proposal["appliedAt"] = now()
                self.persist()
            return 200, {"applied": True, "proposalId": proposal["id"], "digest": proposal["digest"],
                         "observation": self.observation(role), "verification": self.workload(label="Recovery check")}
        finally:
            self.operation_lock.release()

    def reset_demo(self):
        with self.lock:
            app = self.state["app"]
            if (self.resetting or self.active_submissions or self.active_canaries or self.pending_provisions
                    or self.state["burst"]["running"] or app["reconciling"] or app["busy"]
                    or any(x["status"] in {"checking", "provisioning"} for x in app["allocations"])
                    or self.state["cloud"]["inFlight"] or self.operation_lock.locked()):
                return 409, {"error": "Wait for running requests, load and recovery to finish"}
            self.resetting = True
        try:
            with self.lock:
                self._fresh_state()
            with sqlite3.connect(self.db_path, timeout=10) as db:
                db.execute("DELETE FROM messages")
                db.execute("DELETE FROM attempts")
            for _ in range(self.TARGET_WORKERS):
                self.provision_one()
            self.event("TeamChat", "reset", "New local demonstration; ordinary chat is ready.")
            return 200, self.public_state()
        finally:
            with self.lock:
                self.resetting = False

    def public_state(self):
        with sqlite3.connect(self.db_path, timeout=10) as db:
            # Preserve user-submitted messages even after many generated probes.
            humans = db.execute("SELECT id,text,author,startedAt,status,latencyMs,error FROM attempts WHERE author NOT IN ('Load test','Recovery check') ORDER BY startedAt DESC LIMIT 100").fetchall()
            recent = db.execute("SELECT id,text,author,startedAt,status,latencyMs,error FROM attempts ORDER BY startedAt DESC LIMIT 60").fetchall()
            attempts = sorted(humans + recent, key=lambda row: row[3], reverse=True)
            persisted = {x[0] for x in db.execute("SELECT id FROM messages")}
            totals = dict(db.execute("SELECT status,count(*) FROM attempts GROUP BY status"))
            times = sorted(x[0] for x in db.execute("SELECT latencyMs FROM attempts WHERE latencyMs IS NOT NULL"))
        messages = []
        seen = set()
        for row in attempts:
            if row[0] in seen:
                continue
            seen.add(row[0])
            item = dict(zip(("id", "text", "author", "createdAt", "status", "latencyMs", "error"), row))
            if item["id"] in persisted:
                item["status"] = "delivered"
            messages.append(item)
        with self.lock:
            app = self.state["app"]
            ready = sum(x["status"] == "ready" for x in app["allocations"])
            failed = sum(x["status"] == "failed" for x in app["allocations"])
            delivered, failed_attempts, pending = (totals.get(k, 0) for k in ("delivered", "failed", "pending"))
            count = delivered + failed_attempts + pending
            health = self.state["health"].copy()
            health["fresh"] = health.get("appRevision") == app["revision"] and health.get("cloudRevision") == self.state["cloud"]["revision"]
            canary = self.state["gatewayCanary"]
            cloud_status = canary["status"] if canary.get("cloudRevision") == self.state["cloud"]["revision"] else "unmeasured"
            return {"version": 1, "updatedAt": now(), "scenario": self.state["scenario"].copy(),
                    "messages": list(reversed(messages)),
                    "storyMessages": [m for m in reversed(messages) if m["author"] not in ("Load test", "Recovery check")],
                    "impact": {"attempted": count, "delivered": delivered, "failed": failed_attempts, "pending": pending,
                               "successRate": round(delivered / count, 4) if count else None,
                               "p95LatencyMs": times[max(0, __import__('math').ceil(.95 * len(times)) - 1)] if times else None},
                    "app": {"readyWorkers": ready, "failedAllocations": failed, "totalAllocations": len(app["allocations"]),
                            "maxAllocations": self.MAX_ALLOCATIONS, "revision": app["revision"],
                            "status": "serving" if ready >= self.TARGET_WORKERS else "under_capacity" if ready else "no_capacity"},
                    "cloud": {**self.state["cloud"], "status": cloud_status, "gatewayCanary": json.loads(json.dumps(canary))},
                    "health": health, "burst": self.state["burst"].copy(),
                    "events": self.state["events"][-80:], "proposals": json.loads(json.dumps(self.state["proposals"]))}

    def public_route(self, handler):
        path = parse.urlsplit(handler.path).path
        if path == "/api/coordination" or path.startswith("/api/coordination/"):
            try:
                data = handler.body() if handler.command == "POST" else None
                code, value = http_json("http://127.0.0.1:" + str(self.bridge_port) + handler.path, data, timeout=130, method=handler.command)
                return handler.send(code, value)
            except (OSError, error.URLError, TimeoutError):
                return handler.send(503, {"error": "Coordination bridge is not running", "status": "offline"})
        if path.startswith("/api/role/"):
            parts = path.split("/")
            if len(parts) != 5 or parts[3] not in self.credentials:
                return handler.send(404, {"error": "Unknown role route"})
            role, endpoint = parts[3], parts[4]
            if endpoint == "observation" and handler.command == "GET":
                if not self.authorized(handler, self.credentials[role]["readToken"]):
                    return handler.send(403, {"error": "Owner diagnostic credential required"})
                return handler.send(200, self.observation(role))
            if endpoint == "tool" and handler.command == "POST":
                body = handler.body()
                action, args = body.get("action"), body.get("args", {})
                required = "applyToken" if action == "apply_recovery" else "readToken"
                if not self.authorized(handler, self.credentials[role][required]):
                    return handler.send(403, {"error": "Distinct owner approval credential required" if required == "applyToken" else "Owner diagnostic credential required"})
                if action == "inspect_evidence":
                    return handler.send(200, self.observation(role))
                if action == "probe_gateway" and role == "cloud":
                    return handler.send(200, self.gateway_canary())
                if action == "propose_recovery":
                    return handler.send(*self.propose(role, args))
                if action == "apply_recovery":
                    return handler.send(*self.apply(role, args))
                return handler.send(400, {"error": "Action outside this owner's tool inventory"})
            return handler.send(404, {"error": "Unknown role operation"})
        if path == "/api/state" and handler.command == "GET":
            return handler.send(200, self.public_state())
        if path == "/api/health":
            return handler.send(200, {"up": True, "application": "Relay Demo"})
        if path == "/api/messages" and handler.command == "POST":
            result = self.submit(handler.body())
            return handler.send(200 if result["ok"] else result["status"], result)
        if path in ("/api/demo/burst", "/api/demo/probe") and handler.command == "POST":
            try:
                body = handler.body()
                return handler.send(202, self.burst(story_message=body.get("message")))
            except ValueError as exc:
                return handler.send(409, {"error": str(exc)})
        if path == "/api/demo/reset" and handler.command == "POST":
            return handler.send(*self.reset_demo())
        if path.startswith("/api/"):
            return handler.send(404, {"error": "Unknown public API route"})
        target = (ROOT / "web" / ("index.html" if path == "/" else path.lstrip("/"))).resolve()
        if not target.is_relative_to((ROOT / "web").resolve()) or not target.is_file():
            return handler.send(404, {"error": "Web page not found"})
        return handler.send_bytes(200, target.read_bytes(), mimetypes.guess_type(str(target))[0] or "application/octet-stream")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=4318)
    parser.add_argument("--bridge-port", type=int, default=4319)
    parser.add_argument("--runtime", type=Path, default=ROOT / ".runtime")
    args = parser.parse_args()
    engine = Engine(args.runtime, args.port, args.bridge_port).start()
    print(json.dumps({"ready": True, "url": engine.public_url, "runtime": str(args.runtime)}), flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()


if __name__ == "__main__":
    main()
