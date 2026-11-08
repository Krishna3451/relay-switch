# Recorded local verification

These are bounded synthetic local checks, not a production deployment or a
support-speed comparison. The selected final video is
[final Relay video](../demo/final-v3/delivery/Relay-final.mp4) (1080p24).

The recorded native run used 12 live model calls in separate company histories,
six reviewed Switch releases and nine original enrolled-account source posts.
All eleven native audit checks passed. Its fixed app workload was 24 actual HTTP
requests at concurrency 12 with a 1,100 ms p95 target.

| Recorded stage | Cloud check | App delivery | App p95 |
|---|---:|---:|---:|
| Incident | Unrepaired | 13/24 | 781.03 ms |
| Cloud recovery | 6/6 | 15/24 | 823.19 ms |
| App recovery, before retry | Already verified | 24/24 | 355.58 ms |
| Closing check, after retry | Already verified | 24/24 | 341.11 ms |

The originally failed message was retried with its unchanged ID/body/author.
The repeated identical request was recognized as a duplicate and exactly one
message row was persisted. The video retains cloud recovery → app recovery →
original-message retry → closing-check order.

The separate four-arm causal check delivered 14/24 with neither repair, app-only
repair or cloud-only repair, and 24/24 after both repairs. It tests actual local
HTTP contention/readiness and logical serving allocations, not EC2 or packet loss.

The reviewer accounts belong to a fictional scenario controlled by one presenter.
Their replies are scripted presenter inputs; the underlying scoped agents,
Switch events, approval checks and workload execution were real. Separate model
contexts/API credentials do not provide OS isolation from trusted host admins.
A central agent granted equivalent access remains a valid alternative.

- [Native aggregate evidence](native-verification.json)
- [Four-arm causal evidence](causal-proof.json)
- [Earlier web-bridge aggregate audit](live-audit.json)
- [Final assembly checks](../demo/final-v3/assembly-manifest.json)
- [Final join/content review](../demo/final-v3/qa/review-report.json)
- [Publication omissions and prerequisites](../SUBMISSION-NOTES.md)

Public JSON files explicitly state sanitization and preserve original artifact
hashes. Private transport transcripts, actor/room/source IDs, session data and
multi-gigabyte raw frames are omitted. The selected film and its QA checkpoints
remain available. The recorded source hashes describe the historical run; later
submission cleanup must not be described as a new live verification.
