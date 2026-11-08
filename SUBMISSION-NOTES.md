# Public source package

This repository contains the Relay application/gateway model, scoped agent and
approval workflow, native Mattermost transport, tests, diagnostic UI, recording
and editing source, the selected final demo video, captions and public evidence
summaries. The README links the selected final video and captions.

The recording depicts fictional companies and presenter-controlled reviewer
accounts. The underlying scoped model calls, Switch events, HTTP requests,
owner-bound approvals and persistence checks were real local executions.

## Reproduce the behavior

The backend and its tests need Python 3.12 or newer. Agent boundary tests also
need the dependencies pinned in `requirements.txt`; they use explicit fake
models/transports and make no paid model calls. A fresh `engine.proof` run checks
the causal failure/recovery mechanism with actual local HTTP requests.

The native live workflow additionally needs the macOS Switch Console native
runtime, its running Core/Mattermost bridge, operator setup access and an
authenticated Codex CLI. Native enrollment creates dedicated fictional identities
and private rooms in that operator's tenant. It is not a generic hosted Slack or
AWS deployment. No production credentials are supplied.

The shell launchers use `RELAY_PYTHON`, then `.venv/bin/python`, then `python3` on
`PATH`. Python media helpers resolve `ffmpeg` and `ffprobe` from `PATH`. Swift
illustration renderers require macOS AppKit; shell renderers support `FFMPEG`.
Native Chromium capture uses Node.js 22 or newer and `CHROME_BIN` when Chrome is
outside the standard macOS application path. The unselected `opening-v4` browser
experiment additionally needs `playwright-core` and a Chromium installation.

## Evidence publication

Public JSON evidence is a deliberately reduced publication copy. It retains the
recorded aggregate checks, workload, measured outcomes and original artifact
hash, while omitting private transport transcripts, account/room/source IDs,
runtime URLs and source-post bodies. The original raw local evidence is preserved
outside this export. Each transformed evidence file describes its omissions.
These summaries are evidence of a bounded local demonstration, not third-party
attestation, performance benchmarking or production reliability.

The selected movie and final QA frames are included. Multi-gigabyte raw capture
frames, local enrollment credentials, API keys, sessions, logs, SQLite databases,
provider catalogs/account metadata, speech request metadata and abandoned
generated media are excluded. Source for the production helpers and alternative
visual treatments is included. Re-rendering their historical outputs requires
fresh private setup/captures and local media inputs; it is not necessary to run
the backend or tests.

The recorded run's source hashes describe that historical run. Later submission
cleanup may improve code without changing the preserved movie or measurements.

## Attribution and licensing

The incident mechanism is a small causal adaptation of
[Slack's January 4, 2021 engineering incident](https://slack.engineering/slacks-outage-on-january-4th-2021/).
No Slack or AWS code, customer data or production infrastructure is included.
The model uses logical local workers and HTTP admission timeouts, not an AWS
emulator or a reconstruction of Slack's architecture.

Relay integrates with Switch Console/Mattermost and invokes the locally
authenticated Codex CLI. Those upstream products are separate prerequisites and
are not redistributed here. Narration in the selected video was generated with
ElevenLabs Will; the API credential and account information are excluded.

Direct Python dependencies retain their upstream licensing: FastAPI (MIT),
Uvicorn (BSD-3-Clause), HTTPX (BSD-3-Clause) and websockets (BSD-3-Clause), as stated
by the installed distribution metadata for the pinned versions. Python, FFmpeg,
Node.js, Chromium, Swift and platform fonts have their respective upstream terms.
No dependency source or bundled binaries are vendored in this package. See any
repository-level license chosen by the author for the Relay source itself;
this note does not grant a new license to upstream products or media.
