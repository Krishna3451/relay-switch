"""Independent four-arm causal check. No agents, Switch, or model calls.

Each arm starts from fresh services, receives the same real offered workload,
and uses exactly the owner API available to the bridge. Outcome is measured
by HTTP results and SQLite message rows, never by a pair of repaired flags.
"""
import argparse
import json
from pathlib import Path
import tempfile
import time

from .server import Engine, ROOT, http_json, now


def wait_settled(engine, timeout=5):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        observation = engine.observation("app")
        if not any(x["status"] in ("provisioning", "checking") for x in observation["allocations"]):
            return
        time.sleep(.03)
    raise AssertionError("Readiness requests did not settle")


def recover(engine, role):
    base = engine.public_url + "/api/role/" + role
    credentials = engine.credentials[role]
    code, observation = http_json(base + "/observation", token=credentials["readToken"])
    assert code == 200
    args = {"expectedRevision": observation["revision"], "reason": "Independent causal proof using observed resource state"}
    if role == "app":
        args["allocationIds"] = [x["id"] for x in observation["allocations"] if x["status"] == "failed"]
    else:
        args["capacity"] = 8
    code, proposal = http_json(base + "/tool", {"action": "propose_recovery", "args": args}, credentials["readToken"])
    assert code == 200, proposal
    code, result = http_json(base + "/tool", {"action": "apply_recovery", "args": {"proposalId": proposal["id"], "digest": proposal["digest"]}},
                             credentials["applyToken"], timeout=15)
    assert code == 200, result
    wait_settled(engine)
    return result


def matrix(output):
    rows = []
    for arm in ("neither", "app_only", "cloud_only", "both"):
        with tempfile.TemporaryDirectory(prefix="relay-proof-") as directory:
            engine = Engine(directory, port=0).start()
            try:
                initial = engine.submit({"id": "original-message", "text": "Can the team see this?", "author": "Avery"})
                assert initial["ok"], initial
                incident = engine.workload(story_message={"id": "busy-morning-message", "text": "Can anyone see this?", "author": "Avery"})
                wait_settled(engine)
                observed = {"app": engine.observation("app"), "cloud": engine.observation("cloud")}
                operations = []
                if arm in ("cloud_only", "both"):
                    operations.append(recover(engine, "cloud"))
                if arm in ("app_only", "both"):
                    operations.append(recover(engine, "app"))
                final = engine.workload()
                wait_settled(engine)
                after = engine.public_state()
                retried_message = None
                if arm == "both":
                    # Select an honestly failed offered request. The expressly supplied
                    # human message may legitimately have succeeded; never force it red.
                    failed_id = next(x["id"] for x in incident["results"] if not x["ok"])
                    with __import__("sqlite3").connect(engine.db_path) as db:
                        body_row = db.execute("SELECT text,author FROM attempts WHERE id=? LIMIT 1", (failed_id,)).fetchone()
                    body = {"id": failed_id, "text": body_row[0], "author": body_row[1]}
                    first_retry, repeated_retry = engine.submit(body), engine.submit(body)
                    with __import__("sqlite3").connect(engine.db_path) as db:
                        stored = db.execute("SELECT count(*) FROM messages WHERE id=?", (failed_id,)).fetchone()[0]
                    retried_message = {"id": failed_id, "originalAttemptFailed": True, "retry": first_retry,
                                       "repeatedRetry": repeated_retry, "persistedRows": stored}
                    assert first_retry["ok"] and repeated_retry["duplicate"] and stored == 1
                rows.append({"arm": arm, "initialOrdinaryMessage": initial,
                             "incident": {k: v for k, v in incident.items() if k != "results"},
                             "before": observed, "operations": operations,
                             "retriedFailedMessage": retried_message,
                             "measurement": {k: v for k, v in final.items() if k != "results"},
                             "after": {key: after[key] for key in ("app", "cloud", "health")},
                             "assertion": final["status"] == ("healthy" if arm == "both" else "degraded")})
                print(json.dumps({"arm": arm, "incident": incident["delivered"], "delivered": final["delivered"],
                                  "offered": final["attempted"], "p95LatencyMs": final["p95LatencyMs"],
                                  "readyWorkers": after["app"]["readyWorkers"], "failedAllocations": after["app"]["failedAllocations"],
                                  "passed": rows[-1]["assertion"]}), flush=True)
            finally:
                engine.stop()
    artifact = {"createdAt": now(), "mechanism": "Actual HTTP admission timeout and failed readiness allocations; logical workers, not EC2 or packet simulation",
                "fixedWorkload": {"messages": Engine.PROBE_COUNT, "concurrency": Engine.PROBE_CONCURRENCY, "sloMs": Engine.SLO_MS},
                "arms": rows, "allPassed": all(x["assertion"] for x in rows)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2))
    if not artifact["allPassed"]:
        raise SystemExit("Causal matrix failed; inspect recorded measurements")
    return artifact


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / ".runtime" / "causal-proof.json")
    args = parser.parse_args()
    matrix(args.output)


if __name__ == "__main__":
    main()
