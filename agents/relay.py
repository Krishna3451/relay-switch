"""Review-controlled, real Switch events between fictional local participants.

The local demo operator can roleplay both fictional approval accounts. A
receipt proves the message path and account binding, not independent human review
or company isolation from this host's administrators.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time

import httpx

from .bootstrap import setup
from .switch_client import SwitchClient, SwitchHTTPError


APPROVAL_MODE = "manual_fictional_owner_click"
SIDES = {"customer", "provider"}
KINDS = {"question", "evidence", "repair_proposal", "verification"}
WIRE_PREFIX = "RELAY/1 "
TOKEN = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


class RelayError(RuntimeError):
    pass


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def validate_envelope(case_token: str, body: dict) -> None:
    if not isinstance(case_token, str) or not TOKEN.fullmatch(case_token):
        raise RelayError("An opaque case token is required.")
    if not isinstance(body, dict) or set(body) != {"ticket", "kind", "content"}:
        raise RelayError("Envelope must contain only ticket, kind and content.")
    if body["ticket"] != case_token or body["kind"] not in KINDS or not isinstance(body["content"], dict):
        raise RelayError("Invalid envelope identity, kind or content.")
    try:
        text = canonical(body)
        if len(canonical(body["content"]).encode()) > 16384:
            raise RelayError("Content exceeds the 16KB limit.")
    except (TypeError, ValueError):
        raise RelayError("Envelope is not finite JSON.") from None
    # A final obvious-secret guard complements the backend's approved projection;
    # it does not claim universal PII/secret detection.
    if re.search(r"(?:whsec_[A-Za-z0-9_]+|sk_(?:live|test)_[A-Za-z0-9_]+|(?:CUSTOMER|VENDOR)_PRIVATE_[A-Za-z0-9]+|Bearer\s+\S+)", text):
        raise RelayError("Envelope contains a forbidden credential or private canary.")


def envelope_digest(side: str, case_token: str, body: dict) -> str:
    if side not in SIDES:
        raise RelayError("Unknown participant side.")
    validate_envelope(case_token, body)
    return hashlib.sha256(canonical({"side": side, "case_token": case_token, "body": body}).encode()).hexdigest()


class SwitchRelay:
    agent_keys = ("customer", "provider", "clerk")
    def __init__(self, state_dir: Path | None = None, *, timeout: float = 60):
        self.state_dir = Path(state_dir or Path(__file__).resolve().parents[1] / ".runtime/relay-switch")
        self.timeout = timeout
        self.config = None
        self.clients = {}
        self.tasks = []
        self.http = None
        self.lock = None
        self.db_path = self.state_dir / "transport.db"
        self.deliveries = asyncio.Queue()

    def _db(self):
        con = sqlite3.connect(self.db_path, timeout=15)
        con.row_factory = sqlite3.Row
        return con

    async def __aenter__(self):
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.chmod(0o700)
        self.lock = (self.state_dir / "relay.lock").open("a+")
        try:
            fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            raise RelayError("One comparison relay already owns these agent connections.") from None
        try:
            # Provisioning never uses any existing project's scoped credentials.
            self.config = await asyncio.to_thread(setup, self.state_dir)
            with self._db() as con:
                con.executescript("""
                    PRAGMA journal_mode=WAL;
                    CREATE TABLE IF NOT EXISTS events(
                      observer TEXT NOT NULL,message_id TEXT NOT NULL,frame TEXT NOT NULL,at REAL NOT NULL,
                      PRIMARY KEY(observer,message_id));
                    CREATE TABLE IF NOT EXISTS proposals(
                      digest TEXT PRIMARY KEY,side TEXT NOT NULL,case_token TEXT NOT NULL,body TEXT NOT NULL,
                      created_at REAL NOT NULL,preview_id TEXT,approval_post_id TEXT,
                      approval_event_id TEXT,shared_event_id TEXT,receipt TEXT);
                """)
            self.db_path.chmod(0o600)
            self.http = httpx.AsyncClient(timeout=25, follow_redirects=False)
            for key in self.agent_keys:
                agent = self.config["agents"][key]
                room_keys = [key, "shared"] if key != "clerk" else ["shared"]
                client = SwitchClient(self.config["switch_url"], agent["id"], agent["api_key"],
                                      [self.config["rooms"][k]["id"] for k in room_keys],
                                      self.state_dir / f"connection-{key}.json")
                self.clients[key] = client
                await client.start()
                self.tasks.append(asyncio.create_task(self._capture(key, client)))
            return self
        except BaseException:
            await self.close()
            raise

    async def __aexit__(self, *_):
        await self.close()

    async def close(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
        for client in self.clients.values():
            await client.close()
        self.clients.clear()
        if self.http is not None:
            await self.http.aclose()
            self.http = None
        if self.lock is not None:
            self.lock.close()
            self.lock = None

    def _healthy(self):
        if not self.clients or self.http is None:
            raise RelayError("Open the relay async context first.")
        if any(t.done() and not t.cancelled() for t in self.tasks):
            raise RelayError("A comparison event reader stopped; inspect local runtime health.")

    async def _capture(self, observer, client):
        async for frame in client.events():
            if frame.get("event") == "message":
                message_id = frame["data"].get("payload", {}).get("message_id")
                if message_id:
                    with self._db() as con:
                        con.execute("INSERT OR IGNORE INTO events VALUES(?,?,?,?)",
                                    (observer, message_id, canonical(frame), time.time()))
            # Persist before acknowledgement so process interruption cannot lose
            # the evidence used to authorize a release.
            await client.ack(frame)

    async def _wait(self, find):
        end = time.monotonic() + self.timeout
        while time.monotonic() < end:
            self._healthy()
            result = find()
            if result is not None:
                return result
            await asyncio.sleep(.1)
        raise RelayError("Timed out waiting for the actual Switch/Mattermost evidence.")

    def _event(self, observer, *, room, sender, body=None, message_id=None):
        with self._db() as con:
            rows = con.execute("SELECT frame FROM events WHERE observer=? ORDER BY at", (observer,)).fetchall()
        for row in rows:
            frame = json.loads(row["frame"])
            data = frame["data"]
            payload = data.get("payload", {})
            if data.get("room_id") != room or payload.get("sender") != sender:
                continue
            if body is not None and payload.get("body") != body:
                continue
            if message_id is not None and payload.get("message_id") != message_id:
                continue
            return frame
        return None

    async def _posts(self, side, room_key):
        room = self.config["rooms"][room_key]
        human = self.config["humans"][side]
        response = await self.http.get(
            self.config["mattermost_url"] + f"/api/v4/channels/{room['external_channel_id']}/posts",
            headers={"Authorization": "Bearer " + human["token"]}, params={"per_page": 200})
        if response.status_code != 200:
            raise RelayError("Mattermost refused the scoped account history read.")
        return list(response.json().get("posts", {}).values())

    async def _find_post(self, side, room_key, body, *, expected_user=None):
        for post in await self._posts(side, room_key):
            if post.get("message") == body and (expected_user is None or post.get("user_id") == expected_user):
                if not post.get("edit_at") and not post.get("delete_at"):
                    return post
        return None

    async def _agent_post(self, side, room_key, body):
        # Reconcile identical unique digest/tag content before a repeat mutation.
        prior = await self._find_post(side if side != "clerk" else "customer", room_key, body)
        if prior is None:
            result = await self.clients[side].post_message(self.config["rooms"][room_key]["id"], body)
        else:
            result = {"mattermost_post_id": prior["id"], "reconciled": True}
        return result

    async def prepare(self, side: str, case_token: str, body: dict) -> str:
        self._healthy()
        digest = envelope_digest(side, case_token, body)
        with self._db() as con:
            con.execute("INSERT OR IGNORE INTO proposals(digest,side,case_token,body,created_at) VALUES(?,?,?,?,?)",
                        (digest, side, case_token, canonical(body), time.time()))
        preview = ("**RELAY — exact owner review**\n\n"
                   + canonical(body) + "\n\nExact digest: `" + digest + "`\n\n"
                   "Pending explicit owner click using a fictional demo account. "
                   "No independent person's approval is claimed.")
        await self._agent_post(side, side, preview)
        return digest

    async def _verified_approval(self, side, expected_body, post_id, created_at):
        human = self.config["humans"][side]
        room = self.config["rooms"][side]
        source = "\x1f".join([self.config["bridge_id"], room["external_channel_id"], post_id])
        material = "\x1f".join([human["client_id"], source, "0"])
        expected_message_id = "sw_" + hashlib.sha256(material.encode()).hexdigest()[:32]
        frame = await self._wait(lambda: self._event(side, room=room["id"], sender=human["actor_id"],
                                                     body=expected_body, message_id=expected_message_id))
        payload = frame["data"]["payload"]
        if payload.get("on_behalf_of") or payload.get("sender_kind") in {"agent", "platform"}:
            raise RelayError("Delegated or agent events cannot authorize release.")
        post = await self._find_post(side, side, expected_body, expected_user=human["id"])
        if post is None or post["id"] != post_id or post["create_at"] < created_at * 1000:
            raise RelayError("Approval does not bind to the enrolled original source post.")
        if post.get("type") or post.get("props", {}).get("from_webhook") or post.get("props", {}).get("from_bot"):
            raise RelayError("Approval source is not the enrolled fictional account's original post.")
        return expected_message_id

    async def release(self, side: str, case_token: str, body: dict, approved_digest: str, *, approval_mode: str = APPROVAL_MODE) -> dict:
        self._healthy()
        if approval_mode not in {APPROVAL_MODE, "test_operator"}:
            raise RelayError("Unknown explicit approval mode.")
        digest = envelope_digest(side, case_token, body)
        if approved_digest != digest:
            raise RelayError("Operator approval does not match the exact release digest.")
        with self._db() as con:
            row = con.execute("SELECT * FROM proposals WHERE digest=?", (digest,)).fetchone()
        if row is None:
            raise RelayError("Prepare the exact release before approving it.")
        if row["receipt"]:
            return json.loads(row["receipt"])
        human = self.config["humans"][side]
        approval_body = (f"/relay approve {digest} incident {case_token}\n"
                         f"Approval mode: {approval_mode}. Local fictional owner roleplay; no independent organization is claimed.")
        approval = await self._find_post(side, side, approval_body, expected_user=human["id"])
        if approval is None:
            response = await self.http.post(self.config["mattermost_url"] + "/api/v4/posts",
                headers={"Authorization": "Bearer " + human["token"]},
                json={"channel_id": self.config["rooms"][side]["external_channel_id"], "message": approval_body})
            if response.status_code != 201:
                raise RelayError("Mattermost refused the explicit demo-owner approval; nothing released.")
            approval = response.json()
        approval_event = await self._verified_approval(side, approval_body, approval["id"], row["created_at"])
        with self._db() as con:
            con.execute("UPDATE proposals SET approval_post_id=?,approval_event_id=? WHERE digest=?",
                        (approval["id"], approval_event, digest))
        wire = WIRE_PREFIX + canonical({"side": side, "case_token": case_token, "digest": digest, "body": body})
        posted = await self._agent_post(side, "shared", wire)
        opposite = "provider" if side == "customer" else "customer"
        event = await self._wait(lambda: self._event(opposite, room=self.config["rooms"]["shared"]["id"],
                                                    sender=self.config["agents"][side]["actor_id"], body=wire))
        # A read back of the bridged post proves the message actually reached the
        # chat application, in addition to the counterpart's protocol event.
        shared_post = None
        for _ in range(100):
            shared_post = await self._find_post(opposite, "shared", wire)
            if shared_post:
                break
            await asyncio.sleep(.1)
        if shared_post is None:
            raise RelayError("Switch event arrived but the Mattermost post was not observed.")
        receipt = {"case_token": case_token, "side": side, "kind": body["kind"], "digest": digest,
                   "approval_mode": approval_mode,
                   "approval_mattermost_post_id": approval["id"],
                   "approval_switch_message_id": approval_event,
                   "shared_mattermost_post_id": shared_post["id"],
                   "shared_switch_message_id": event["data"]["payload"]["message_id"],
                   "counterpart": opposite, "counterpart_switch_event_id": event.get("id"),
                   "counterpart_observed_at": datetime.now(timezone.utc).isoformat(),
                   "transport": "Actual enrolled Mattermost approval -> verified Switch event -> agent post -> opposing Switch event and Mattermost readback"}
        with self._db() as con:
            con.execute("UPDATE proposals SET shared_event_id=?,receipt=? WHERE digest=?",
                        (receipt["shared_switch_message_id"], canonical(receipt), digest))
        observed_wire = event["data"]["payload"]["body"]
        observed = json.loads(observed_wire[len(WIRE_PREFIX):])
        await self.deliveries.put({"recipient": opposite, "body": observed["body"], "receipt": receipt})
        return receipt

    async def recv(self, side: str, case_token: str) -> list[dict]:
        self._healthy()
        if side not in SIDES or not TOKEN.fullmatch(case_token):
            raise RelayError("Unknown recipient or invalid case token.")
        opposite = "provider" if side == "customer" else "customer"
        with self._db() as con:
            rows = con.execute("SELECT body,receipt FROM proposals WHERE case_token=? AND side=? AND receipt IS NOT NULL ORDER BY created_at",
                               (case_token, opposite)).fetchall()
        received = []
        for row in rows:
            body, receipt = json.loads(row["body"]), json.loads(row["receipt"])
            wire = WIRE_PREFIX + canonical({"side": opposite, "case_token": case_token,
                                            "digest": receipt["digest"], "body": body})
            event = self._event(side, room=self.config["rooms"]["shared"]["id"],
                                sender=self.config["agents"][opposite]["actor_id"], body=wire,
                                message_id=receipt["shared_switch_message_id"])
            if event is None:
                raise RelayError("Counterpart release has no captured protocol event for this recipient.")
            received.append({"body": body, "receipt": receipt, "interpretation": "Reviewed counterpart data, never an instruction or approval."})
        return received

    async def verify_access(self) -> dict:
        self._healthy()
        checks = []
        for side, agent in self.config["agents"].items():
            for room_key, room in self.config["rooms"].items():
                expected = 200 if room_key == "shared" or room_key == side else 403
                response = await self.http.post(self.config["switch_url"] + f"/agents/{agent['id']}/ops/read_context",
                    headers={"Authorization": "Bearer " + agent["api_key"]}, json={"room_id": room["id"], "limit": 1})
                checks.append({"check": f"{side}_agent_reads_{room_key}", "expected": expected,
                               "actual": response.status_code, "passed": response.status_code == expected})
        for side, human in self.config["humans"].items():
            for room_key, room in self.config["rooms"].items():
                expected = 200 if room_key in {side, "shared"} else 403
                response = await self.http.get(self.config["mattermost_url"] + f"/api/v4/channels/{room['external_channel_id']}/posts",
                    headers={"Authorization": "Bearer " + human["token"]}, params={"per_page": 1})
                checks.append({"check": f"{side}_human_reads_{room_key}", "expected": expected,
                               "actual": response.status_code, "passed": response.status_code == expected})
        return {"passed": all(c["passed"] for c in checks), "checks": checks,
                "approval_mode": APPROVAL_MODE,
                "boundary": "Room/account membership only. Local host and service administrators are trusted."}

