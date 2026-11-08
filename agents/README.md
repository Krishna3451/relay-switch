# Relay agents and owner review

The native presentation has two active investigators: TeamChat's agent and
HarborCloud's agent. Each receives its own service observations and reviewed
messages from the other company. Maya and Leo control what is shared and which
changes execute. One presenter roleplays these fictional reviewers.

## Native first run

Use Python 3.12+, the dependencies in requirements.txt, and an authenticated
Codex CLI. Enrollment requires an installed, running macOS Switch Console server
with its Mattermost bridge. It reads that installation's privileged local setup
metadata; it is not a hosted-service OAuth integration.

From the repository root:

~~~sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m engine.server
~~~

In another terminal:

~~~sh
source .venv/bin/activate
python -m agents.native_enroll
python -m agents.native
~~~

The first enrollment creates fictional accounts, scoped agents and private
rooms. Partial setup is checkpointed under agents/.runtime/switch. Rerunning
the same command reconciles those resources. Native rooms reuse the identities
under agents/.runtime/native. Setup also has a room-owner/recorder identity for
the earlier diagnostic path; native presentation connects only the two
investigators. Enrollment never raises a global member cap.

Optional environment overrides:

~~~sh
export RELAY_SWITCH_RUNTIME="/path/to/local-switch-server"
export RELAY_SWITCH_BUNDLE="/path/to/local-server"
export CODEX_BIN="/path/to/codex"
~~~

CODEX_BIN is unnecessary when codex is on PATH. The runtime/bundle overrides
must point to a compatible Switch Console installation. Enrollment reports
safe errors without printing credentials. The private browser-session.json
contains room URLs and scoped fictional reviewer sessions; do not publish it.

## Owner inputs and camera gates

Find RELAY · Incident, TeamChat · Maya review and HarborCloud · Leo review in
Mattermost. The accepted inputs are:

| Where | Owner input |
|---|---|
| Shared incident | TeamChat Agent, can you investigate? |
| Maya's question thread | Share with HarborCloud |
| Each company's recovery proposal thread | Approve this change |
| Each company's result thread | Share this result |
| Original failed-message thread | Retry this message |

An investigation reflects actual service state. A healthy service may correctly
require no change. The recorded demo's explicit fixture generates real offered
traffic before the owner report. Its camera gates are ordered:

~~~text
incident → presence → share_question → approve_cloud → share_cloud_result
         → approve_app → share_app_result → retry → close
~~~

~~~sh
curl --fail-with-body -sS http://127.0.0.1:4319/api/native/stage -H 'Content-Type: application/json' -d '{"stage":"incident"}'
curl --fail-with-body -sS http://127.0.0.1:4319/api/native/state
~~~

A stage returns HTTP 202 and moves through queued, running, then complete or
failed. Wait for completion before advancing. These are trusted local presenter
controls: they post scripted inputs through the actual enrolled reviewer
accounts. Their original Switch events authorize the flow. This is roleplay,
not independent human or company participation. The separate presence gate
avoids concurrent creation of the initial native thread. Incomplete cloud/app
checks, failed retry or failed closing checks stop the fixture.

## Another take

A native incident cannot be reset or silently overwritten. Stop the prior
bridge first, reset the idle workload and enroll fresh rooms while reusing the
base identities:

~~~sh
curl --fail-with-body -sS -X POST http://127.0.0.1:4318/api/demo/reset -H 'Content-Type: application/json' -d '{}'
python -m agents.native_enroll --state-dir agents/.runtime/take-002 --base-state-dir agents/.runtime/switch
python -m agents.native --state-dir agents/.runtime/take-002
~~~

The engine refuses reset while requests, provisioning, canaries, load or recovery
are active, and refuses new sends during reset. Fresh rooms change the agents'
addressing policies: do not run multiple takes over those identities at once.
Keep completed state directories for audit.

## Exact authorization and controlled disclosure

An approval must come from the enrolled account as an original unedited
Mattermost post and match both the exact native root post and Switch thread.
Account/source binding is checked against the bridged event. The incident,
review digest, expiry and private operation fingerprint must match before
release. The separate executor credential then reaches an engine that checks
its own proposal digest, revision, expiry, owner and allowed resources. Replay
cannot apply the same operation twice.

Operation approval shares the visible public summary and bounded change
description before executing the local change. Internal resource IDs, private
rationale and full authorization fields remain local. A fingerprint prevents
swapping that local operation after review. Native review text states the
sharing effect explicitly.

Peer content permits only reviewed title/summary, bounded change, fixed
execution status and evidence references. References must be actual observed
event/batch/message IDs. Arbitrary hidden fields or free-form reference text are
rejected. The readable shared post retains this same approved projection in
compact Markdown-title machine metadata, so the opposing model receives the
actual Switch message. That encoding is not encryption.

Human review is the disclosure boundary for visible text. Relay does not claim
a universal secret/PII detector. It does not automatically copy private histories
into peer context; approved incident findings are shared.

## Trust and lifecycle

Models run tool-free in temporary directories using separate histories. Their
environment lacks engine/Switch execution credentials. The parser rejects tool
events, incomplete responses and provider errors. Exhausting a call budget does
not declare the incident successfully resolved. Partial startup and normal
shutdown both close bridge resources.

Servers bind to loopback. Host/origin checks reject DNS-rebinding hosts,
foreign/null browser origins and cross-site control POSTs, including native
presenter gates. Same-origin console requests and the engine-to-bridge proxy
still work. Origin-less local CLI callers are trusted. This is not user
authentication or protection from local malware/administrators. The presenter
and host/service administrators can inspect both sides. Room/API scoping is not
OS isolation or a production security claim.

## Verification and earlier interface

~~~sh
python -m unittest discover -s tests -v
python -m unittest discover -s tests_agents -v
python -m engine.proof --output .runtime/causal-proof.json
~~~

Unit tests use explicit fake models/transports and temporary real HTTP services
where indicated; they do not call a model provider or enroll live accounts.
Historical filmed source hashes remain separate from current publication
hardening. After a complete native take, agents.native_audit checks source,
owner and thread binding, scoped model contexts, cloud-vs-app results, fresh
24/24 and the original failed message's same-ID/body retry with one stored row.

The earlier diagnostic web bridge is available through python -m agents.bridge.
It provides explicit investigate/approve/reject/reset routes and an opt-in
--scripted test-operator mode. Native mode refuses those investigation, approval
and reset shortcuts. Defaults are port 4318 for the engine and 4319 for either
bridge; do not run both bridge modes together. See the main README for the video,
recorded measurements and current validation results.
