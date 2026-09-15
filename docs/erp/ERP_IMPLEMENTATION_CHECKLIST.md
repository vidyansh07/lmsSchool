# ERP implementation checklist

Statuses: NOT_STARTED · PLANNED · IN_PROGRESS · BLOCKED · IMPLEMENTED (code
exists) · TESTED (automated tests pass) · VERIFIED (the user journey works
end to end on staging) · PRODUCTION_READY (§101: journey, authorization,
errors, nulls, migration, performance, logging, audit, backup, no broken
links, no broken calls, no accidental destructive action, no placeholder).

Updated at the end of every phase. A row moves forward only with the
evidence named in its last column.

## Phase 0 — Planning

| Item | Status | Evidence |
| --- | --- | --- |
| USER_JOURNEYS.md | IMPLEMENTED | this directory |
| DESIGN_DECISIONS.md | IMPLEMENTED | |
| ARCHITECTURE_DECISIONS.md | IMPLEMENTED | |
| ERP_IMPLEMENTATION_CHECKLIST.md | IMPLEMENTED | |
| ERP_GAP_MATRIX.md | IMPLEMENTED | measured from code 2026-09-15 |
| DATA_MODEL.md | IMPLEMENTED | |
| API_CONTRACTS.md | IMPLEMENTED | |
| PERMISSION_CATALOG.md | IMPLEMENTED | 71 existing + 24 new |
| ACTIVITY_CATALOG.md | IMPLEMENTED | 18 seeded types |
| FORM_CATALOG.md | IMPLEMENTED | |
| AUTOMATION_CATALOG.md | IMPLEMENTED | 9 seeded rules |
| COMMUNICATION_CATALOG.md | IMPLEMENTED | |
| SECURITY_DECISIONS.md | IMPLEMENTED | |
| PERFORMANCE_PLAN.md | IMPLEMENTED | |
| BACKUP_AND_RECOVERY.md | IMPLEMENTED | drill log started |
| IMPLEMENTATION_PLAN.md | IMPLEMENTED | |

## Phases 1–25

Each phase has the same fifteen tracks. A track is "n/a" when the phase
adds nothing in it.

| Phase | Product | UX | Frontend | Backend | Database | API | Authorization | Security | Caching | Logging | Audit | Testing | Migration | Backup | Docs | Deploy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 Dynamic authorization | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | n/a | VERIFIED | VERIFIED | VERIFIED | n/a | VERIFIED | VERIFIED |
| 2 Scopes and locking | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | n/a | VERIFIED | VERIFIED | VERIFIED | n/a | VERIFIED | VERIFIED |
| 3 Policy management | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | n/a | VERIFIED | VERIFIED |
| 4 Email OTP | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | n/a | VERIFIED | VERIFIED | VERIFIED | VERIFIED | n/a | VERIFIED | VERIFIED |
| 5 MFA | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | n/a | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED | VERIFIED |
| 6 Session management | PLANNED | PLANNED | PLANNED | TESTED | TESTED | TESTED | TESTED | TESTED | n/a | n/a | TESTED | TESTED | TESTED | n/a | TESTED | PLANNED |
| 7 Soft delete | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | n/a | n/a | PLANNED | PLANNED | PLANNED | n/a | PLANNED | PLANNED |
| 8 Dynamic forms | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | n/a | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED |
| 9 Activity engine | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | n/a | PLANNED | PLANNED |
| 10 Activity timeline | PLANNED | PLANNED | PLANNED | PLANNED | n/a | PLANNED | PLANNED | PLANNED | n/a | n/a | n/a | PLANNED | n/a | n/a | PLANNED | PLANNED |
| 11 Student 360 | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | n/a | PLANNED | PLANNED |
| 12 Performance engine | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | n/a | PLANNED | n/a | PLANNED | PLANNED | PLANNED | n/a | PLANNED | PLANNED |
| 13 Risk engine | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | n/a | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | n/a | PLANNED | PLANNED |
| 14 Next action automation | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | n/a | PLANNED | PLANNED | PLANNED | PLANNED | n/a | PLANNED | PLANNED |
| 15 DSR | PLANNED | PLANNED | PLANNED | PLANNED | n/a | PLANNED | PLANNED | n/a | n/a | n/a | PLANNED | PLANNED | n/a | n/a | PLANNED | PLANNED |
| 16 Trainer workspace | PLANNED | PLANNED | PLANNED | PLANNED | n/a | PLANNED | PLANNED | n/a | PLANNED | n/a | n/a | PLANNED | n/a | n/a | PLANNED | PLANNED |
| 17 Counsellor workspace | PLANNED | PLANNED | PLANNED | PLANNED | n/a | PLANNED | PLANNED | PLANNED | PLANNED | n/a | PLANNED | PLANNED | n/a | n/a | PLANNED | PLANNED |
| 18 Manager dashboard and reviews | PLANNED | PLANNED | PLANNED | PLANNED | n/a | PLANNED | PLANNED | n/a | PLANNED | n/a | PLANNED | PLANNED | n/a | n/a | PLANNED | PLANNED |
| 19 Communication center | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED |
| 20 Export system | PLANNED | PLANNED | PLANNED | PLANNED | n/a | PLANNED | PLANNED | PLANNED | n/a | PLANNED | PLANNED | PLANNED | n/a | n/a | PLANNED | PLANNED |
| 21 Caching | n/a | PLANNED | PLANNED | PLANNED | n/a | n/a | PLANNED | PLANNED | PLANNED | n/a | n/a | PLANNED | n/a | n/a | PLANNED | PLANNED |
| 22 Performance hardening | n/a | PLANNED | PLANNED | PLANNED | PLANNED | n/a | n/a | n/a | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | n/a | PLANNED | PLANNED |
| 23 Backup and recovery | n/a | n/a | n/a | PLANNED | n/a | n/a | n/a | PLANNED | n/a | PLANNED | n/a | PLANNED | n/a | PLANNED | PLANNED | PLANNED |
| 24 Security and regression | n/a | n/a | PLANNED | PLANNED | n/a | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | n/a | PLANNED | PLANNED |
| 25 Production readiness | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED | PLANNED |

## Deliberately not started

| Item | Status | Reason |
| --- | --- | --- |
| DEPARTMENT scope | NOT_STARTED | no department entity; product call (gap matrix) |
| HIBP breached-password check | NOT_STARTED | needs network egress decision |
| WAL archiving (RPO < 24 h) | NOT_STARTED | follow-up after Phase 23 |
| Meta Cloud WhatsApp credentials | BLOCKED | human: provider account |
| S3 backup bucket | BLOCKED | human: `BACKUP_S3_BUCKET` (carried from FEATURE_STATUS gaps) |

## Release blockers (§102) — checked at Phase 25

broken links · broken routes · broken API calls · unauthorized access ·
accidental destructive mutation · exposed secrets · unhandled exceptions ·
undefined/NaN/Invalid Date · data loss · broken migration · failed backup
recovery · critical N+1 regression · insecure export · duplicate critical
transaction · incorrect permissions · stale authorization cache granting
access · fake or placeholder functionality. Each has a named test or crawl
check in Phase 24–25.
