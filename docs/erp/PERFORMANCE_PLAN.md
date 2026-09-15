# Performance plan

## Expected data volume (planning figures, per centre, per year)

| Entity | Volume | Notes |
| --- | --- | --- |
| Students | 2,000 active, 10,000 lifetime | matches the profiled 400-student dataset ×5 headroom |
| Batches | 150 active | |
| Class sessions | 40,000 | 150 batches × ~260 days |
| Attendance records | 800,000 | sessions × 20 |
| Activities | 60,000 | 30 per student per year |
| Form responses | 60,000 | one per completed activity |
| Deliveries | 500,000 | notifications × channels |
| Audit rows | 3,000,000 | already the largest table; purge policy exists (`purge_before`) |
| Automation runs | 100,000 | |

Three centres → multiply by three. PostgreSQL handles this comfortably
with the indexes in `DATA_MODEL.md` §9; nothing needs partitioning in this
programme.

## Budgets

| Surface | Budget | How it is enforced |
| --- | --- | --- |
| Any list endpoint | ≤ 12 queries, flat in page size | `tests/test_performance.py::assert_flat` pattern extended to every new list |
| Dashboard endpoint | ≤ 15 queries, flat in data size, p95 < 300 ms at planning volume | same, plus a timing assertion on the scale dataset (D-078) |
| Student 360 overview | ≤ 20 queries | `test_student_360_flat` |
| Timeline page | ≤ 1 query per source + 1 | `test_timeline_flat` |
| Activity complete | ≤ 25 queries in the request; recompute and automation on the worker | `test_complete_activity_queries` |
| Global search | ≤ 1 query per type, each `LIMIT 5`, total < 200 ms | `test_search_flat` |
| Frontend route | first contentful data < 1 s on staging; one summary request per dashboard | crawl script records request count per route |

## Dashboard query strategy

One aggregated endpoint per dashboard built from a handful of `COUNT`/
`EXISTS` queries over already-scoped querysets (the existing
`reporting/dashboards.py` shape), cached 60 s per (user scope key). No
per-row loops. Drill-downs are the ordinary paginated lists with the
filter in the URL, so nothing is fetched until clicked.

## Pagination

Every list is server-paginated (existing `DefaultPagination`, page size ≤
100) with a unique tiebreaker in the ordering (D-079). The timeline uses a
keyset cursor `(occurred_at, id)` because it merges sources.

## Caching (Redis in staging/production, locmem locally)

| Prefix | TTL | Scope key | Invalidation |
| --- | --- | --- | --- |
| auth:roles | 10 min | role slug | any role/permission write (on commit) |
| auth:matrix, auth:permissions | 10 min / 1 h | — | same |
| policy | 10 min | (category, key, branch) | policy write |
| form:published | 1 h | slug | publish/unpublish |
| template:published | 1 h | key + channel | publish |
| work:types | 10 min | — | type write |
| dashboard:* | 1 min | user scope key | TTL (+ forget on the writes that matter: activity complete forgets manager/trainer) |
| student360 | 1 min | (student, viewer scope key) | activity/attendance/result writes for that student |
| risk:summary | 1 min | branch | risk recompute |

A cache key that carries the *viewer's scope key* (`branch_scope_key`,
existing) never serves one centre's data to another.

## Background jobs

| Task | Trigger | Limit | Retry |
| --- | --- | --- | --- |
| risk.recompute(enrollment) | on commit of the events that move numbers; debounced 30 s per enrolment via a cache lock | 60 s | 3, backoff |
| automation.dispatch(trigger, object) | on commit | 120 s | 5, backoff; permanent failures recorded |
| communication.deliver(delivery) | on commit | 30 s | 5 with 1/5/15/60/240 min |
| work.mark_overdue | beat every 15 min | 240 s, batched 500 | — |
| work.reminders | beat every 15 min | 240 s | — |
| announcements.publish_due | beat every minute | 60 s | — |
| reporting.expire_exports | beat nightly | 240 s | — |
| risk.recompute_batch(batch) | nightly, and on threshold change | 240 s, chunked | — |
| backup verification | cron (exists) | — | — |

All tasks re-read state before acting (ADR-17). The worker runs with
`--concurrency 2`, `--max-tasks-per-child 200`; a second worker can be
added for `communication` alone by queue name.

## Exports

Sync ≤ 2,000 rows; above that a job. Row count preflight for the
confirmation dialog. Files expire (new sweep task). PDF is capped at 2,000
rows whichever route (existing).

## Search

`icontains` on a small set of columns per type with `LIMIT 5`, through
`visible_*`. If p95 exceeds 200 ms at planning volume, add `pg_trgm` GIN
indexes on the searched columns (a single additive migration).

## Indexing

Every index in `DATA_MODEL.md` §9 plus a partial index on
`work_activity(due_at) WHERE status IN ('planned','assigned','in_progress')`
for the overdue sweep and `delivery(next_attempt_at) WHERE state IN
('queued','failed')` for the retry sweep.

## N+1 prevention

- `with_related()` on every new queryset (`select_related` for FKs,
  `prefetch_related` for replies/history/fields).
- Serializers never touch a relation that was not prefetched; the flat-cost
  tests catch it.
- The timeline and search compose bounded per-source queries; no source
  may loop.

## Request deduplication and cancellation (frontend)

- `useApi` and `useList` key requests by (path, query) and ignore stale
  responses; an `AbortController` cancels the previous request when the
  key changes (extend the existing 20 s timeout controller).
- The palette debounces 200 ms and cancels on each keystroke.
- No fetch on hover, menu open, tab focus or checkbox; tabs fetch on
  open once and keep the result while the page is mounted.

## Frontend caching

Per-page memory only (React state), plus localStorage for conveniences
(density, saved-filter cache). No service worker.

## Load testing

Before Phase 22 closes: `scripts/loadtest.sh` runs the scale dataset
(D-078) and hits each dashboard and list endpoint 200× with 10 concurrent
users through the proxy, recording p50/p95 and query counts; results in
`docs/erp/PERFORMANCE_RESULTS.md`. Budgets above are the pass criteria.

## Frontend performance budgets

- Route JS ≤ 250 kB gzipped per page (Next build output checked in CI).
- No layout shift on dashboards (skeletons sized like tiles).
- Crawl records request count per route; a route that issues more than
  one request on load without user action fails review.
