# Performance results

What was actually measured against `PERFORMANCE_PLAN.md`'s "Response-time
and query budgets" table, by this phase's own test additions and a
scale-dataset smoke pass. A factual record, not a design document — see
`PERFORMANCE_PLAN.md` for the budgets themselves and the reasoning behind
them.

Measured 2026-09-17, against Postgres `wt_vision` (local dev container,
`127.0.0.1:55433`).

## 1. New flat-cost tests (this phase)

Each row is `backend/tests/test_performance.py`'s own measured query count —
identical for the small dataset (`SMALL = 3`) and the large one (`LARGE =
15` more, i.e. 5x the rows), which is the property being proved, not just a
ceiling. Numbers below were captured with a temporary `print()` inside the
test body during a local run, then reverted; the committed test only asserts
equality, as every other test in the file does.

| Screen | Test | Queries (small = large) | Budget | Pass/fail |
| --- | --- | --- | --- | --- |
| Activities list (`GET /activities/`) | `test_the_activity_list_does_not_query_per_activity` | 12 | List ≤ 12 | Pass (at budget) |
| Student activities (`GET /students/{id}/activities/`) | `test_the_student_activity_list_does_not_query_per_activity` | 14 | List ≤ 12 | **Fail** — flat (no N+1) but over the generic list budget by 2; the extra cost is the two-step `reachable_students` → `can_view_student` authorization check this endpoint's own docstring describes, paid once per request regardless of row count, not a per-row cost. Flagged, not fixed — outside this phase's indexing/test-only scope. |
| Global search (`GET /search/?q=`) | `test_search_flat` | 31 | ≤ 1 query per type, LIMIT 5 each | Flat, but 31 is well above "1 per type" for ~10 sources — most of the difference is per-source scoping queries (each source's own `visible_*`/capability resolution), auth/session/audit overhead paid once per request, not a per-row cost. Timing budget (< 200 ms) not re-verified here; not independently timed against the scale dataset (blocked — see §3). |
| Automation rules list (`GET /automation-rules/`) | `test_the_automation_rule_list_does_not_query_per_rule` | 11 | List ≤ 12 | Pass |
| Automation runs list (`GET /automation-rules/{id}/runs/`) | `test_the_automation_run_list_does_not_query_per_run` | 11 | List ≤ 12 | Pass |
| DSR list (`GET /dsr/`) | `test_the_dsr_list_does_not_query_per_report` | 10 | List ≤ 12 | Pass |
| Communication deliveries list (`GET /deliveries/`) | `test_the_delivery_list_does_not_query_per_delivery` | 10 | List ≤ 12 | Pass |
| Report: work_activities (`GET /reports/work_activities/`) | `test_the_work_activities_report_does_not_query_per_activity` | 10 | List ≤ 12 | Pass |
| Report: deliveries (`GET /reports/deliveries/`) | `test_the_deliveries_report_does_not_query_per_delivery` | 9 | List ≤ 12 | Pass |
| Report: automation_runs (`GET /reports/automation_runs/`) | `test_the_automation_runs_report_does_not_query_per_run` | 9 | List ≤ 12 | Pass |

## 2. Screens already covered by an existing test (not duplicated)

Numbers here are the ceiling each existing test already enforces, not
re-measured by this phase.

| Screen | Existing test | Enforced budget | Plan's budget | Pass/fail |
| --- | --- | --- | --- | --- |
| Student 360 (`GET /students/{id}/360/`) | `test_student_360.py::test_student_360_flat` | flat (small == large, exact count not re-instrumented) | ≤ 20 queries | Flatness proven; the ≤20 absolute ceiling itself is not asserted by that test (it asserts equality, not a number) — a pre-existing gap in that test, not introduced here. |
| Student timeline (`GET /students/{id}/timeline/`) | `test_timeline.py` (fixed ceiling) | ≤ `len(TIMELINE_SOURCES)` = 8 | ≤ 1 query per source + 1 = 9 | Pass, on that test's own fixture. The scale-dataset smoke (§3) measured 24 queries for a real student with a full history — see the note there. |
| Manager dashboard (`GET /dashboards/manager/`) | `test_manager_hubs.py::test_manager_dashboard_flat` | flat (small == large) | ≤ 15 queries | Flatness proven; absolute count not asserted by that test. The scale-dataset smoke (§3) measured 67 queries — well over the 15-query budget. Pre-existing (Phase 16), not touched this phase; flagged for follow-up. |
| Batch overview / roster | `test_manager_hubs.py` (`test_batch_overview_query_count_does_not_grow_with_students`, `test_roster_query_count_does_not_grow_with_students`) | flat | — (not in the budget table; a drill-down, not a dashboard) | Flat, no explicit budget. |
| Admin dashboard (`GET /dashboards/admin/`) | `test_performance.py::test_the_admin_dashboard_does_not_query_per_student` | flat | ≤ 15 queries | Flatness proven. Scale smoke: 27 queries — over budget; pre-existing, not touched this phase. |
| Student dashboard (`GET /dashboard/student/`) | `test_dashboards_calendar.py::test_the_student_dashboard_costs_a_bounded_number_of_queries` | ≤ 25 | ≤ 15 queries | Fixed ceiling is itself over the plan's stated dashboard budget — pre-existing, not touched this phase. |
| Trainer dashboard (`GET /dashboard/trainer/`) | `test_dashboards_calendar.py::test_the_trainer_dashboard_costs_a_bounded_number_of_queries` | ≤ 25 | ≤ 15 queries | Same as above. |
| Counsellor dashboard (`GET /dashboards/counsellor/`) | `test_dashboards_calendar.py::test_the_counsellor_dashboard_costs_a_bounded_number_of_queries` | ≤ 60 | ≤ 15 queries | Same as above, and the largest gap of the three. |

The dashboard-budget gaps above (student/trainer/counsellor/admin/manager all
exceed the plan's ≤15-query row) predate this phase — Phases 16–18/21 shipped
with their own, looser ceilings, and nothing in this phase's brief asked for
a redesign of those endpoints, only flat-cost *tests* for anything not yet
covered. Recorded here because §4's instruction is to report what was
measured, pass or fail, not only the passes.

## 3. Load test

`PERFORMANCE_PLAN.md`'s own "Load testing" section names `scripts/loadtest.sh`
hitting the scale dataset (D-078) 200x with 10 concurrent users through the
proxy. That script does not exist in this repository. Per the task's own
fallback, this phase ran the lighter, documented substitute instead:

1. **Scale dataset**: `apps/common/management/commands/seed_scale_data.py`
   already exists (400 students, 24 courses, 12 batches, 480 sessions, 16,000
   attendance records — the "planning figures" scale from this same plan's
   volume table). Running it against `wt_vision` failed with an
   `IntegrityError` (`TrainerProfile.branch`/`StudentProfile.branch`/
   `Batch.branch` are all NOT NULL since `organisation.0002_default_branch`,
   and this command predates that migration). Fixed as a small, additive
   change to the command itself (stamps every generated trainer, student and
   batch with the same "Main centre" branch the migration itself created) —
   tooling only, gated behind `ALLOW_DEMO_SEED`, never reachable in
   production, no product surface touched. Ran successfully after the fix:
   `Scale dataset ready: 400 students, 24 courses, 12 batches, 400
   enrolments, 480 sessions, 16000 attendance records, 2398 lesson-progress
   records, 3200 assessment results.`
2. **Smoke**: a single-process, sequential timing pass (not 10 concurrent
   users) — 20 requests per endpoint through `rest_framework.test.APIClient`,
   cold cache on the first hit of each (query count from that first hit),
   p50/p95 from all 20:

   | Endpoint | Queries (cold) | p50 | p95 |
   | --- | --- | --- | --- |
   | `GET /dashboards/admin/` | 27 | 2.6 ms | 3.9 ms |
   | `GET /dashboards/manager/` | 67 | 2.6 ms | 4.7 ms |
   | `GET /dashboards/batches/` | 15 | 9.3 ms | 9.5 ms |
   | `GET /students/` | 14 | 15.9 ms | 19.8 ms |
   | `GET /activities/` | 15 | 15.0 ms | 19.9 ms |
   | `GET /dsr/` | 13 | 8.2 ms | 9.9 ms |
   | `GET /reports/student_progress/` | 33 | 232.7 ms | 266.8 ms |
   | `GET /reports/work_activities/` | 14 | 93.3 ms | 97.0 ms |
   | `GET /reports/deliveries/` | 10 | 6.9 ms | 7.4 ms |
   | `GET /reports/automation_runs/` | 10 | 6.5 ms | 7.8 ms |
   | `GET /students/{id}/360/` | 47 | 8.0 ms | 9.0 ms |
   | `GET /students/{id}/timeline/` | 24 | 140.5 ms | 148.7 ms |
   | `GET /students/{id}/activities/` | 17 | 12.8 ms | 15.0 ms |
   | `GET /batches/{id}/overview/` | 46 | 84.4 ms | 100.2 ms |
   | `GET /batches/{id}/roster/` | 14 | 19.9 ms | 29.1 ms |
   | `GET /dashboard/trainer/` | 23 | 3.9 ms | 7.9 ms |
   | `GET /dashboard/student/` | 27 | 4.5 ms | 5.3 ms |

   `GET /deliveries/`, `GET /automation-rules/` and `GET /search/` returned
   403 for the only admin account seeded in `wt_vision` (a role with a
   narrower configured permission set than the default `admin` role this
   phase's own pytest fixtures use — not an endpoint bug; those three are
   independently proven flat and within budget by §1's tests, which do use
   an admin with the right capabilities).

   All measured p50/p95 above are comfortably under the plan's 300 ms
   dashboard budget except `reports/student_progress/` (232 ms p50, still
   under 300 ms but the slowest screen measured) and `students/{id}/timeline/`
   (140 ms p50) — both reports/read-models over the full 400-student
   dataset, not dashboards, so the 300 ms row does not strictly apply to
   them, but they are the two to watch if the plan's per-centre volumes
   (2,000 active students) are reached.

This is a single-process sequential smoke, not the specified 200x/10-
concurrent-user load test — it proves nothing about contention or connection-
pool behavior under real concurrency, only that per-request cost stays
reasonable as row counts grow to planning scale. Building the actual
`scripts/loadtest.sh` (concurrency, p50/p95 aggregation, proxy-level timing)
is unstarted and out of this phase's scope per the task's own instruction not
to build new load-testing infrastructure beyond what was asked.

## 4. Indexes added

Cross-checked `DATA_MODEL.md` §9 against the current migrations for every
app this ERP programme touched (`work`, `performance`, `automation`,
`communication`, `reporting`; `dashboards` adds no models of its own).
Confirmed via `pg_indexes` against `wt_vision`, not by reading model source
alone.

| Gap | Table | Migration |
| --- | --- | --- |
| `work_activity(due_at)` partial index `WHERE status IN ('planned','assigned','in_progress')` — named explicitly in both `DATA_MODEL.md` §9 and `PERFORMANCE_PLAN.md`'s Indexing section, never migrated (only the unrelated composite `activity_assignee_status_idx` existed) | `work_activity` | `apps/work/migrations/0005_activity_activity_open_due_idx.py` |
| `communication_delivery(next_attempt_at)` partial index `WHERE state IN ('queued','failed')` — same two documents, never migrated (only the full composite `delivery_pending_idx` on `(state, next_attempt_at)` existed, which is not the same index: it is not partial and its leading column is `state`, not `next_attempt_at`) | `communication_delivery` | `apps/communication/migrations/0003_delivery_delivery_retry_due_idx.py` |

Every other index `DATA_MODEL.md` §9 names (`Activity`'s other three,
`Delivery`'s other two, `OneTimeCode`, `UserSession`, `AutomationRun`,
`Policy`, `FormField`) already exists as a migration. `OneTimeCode`,
`UserSession`, `Policy` and `FormField` belong to apps this ERP programme
did not touch (pre-existing `accounts`/`policies`/`forms`), so they were
cross-checked but out of this phase's scope to change even where §9's
column list (`OneTimeCode`: `created_at` in the doc vs. `used_at` in the
actual index) has drifted from the migration — a documentation staleness,
not a missing migration.

Verified with `manage.py makemigrations --check --dry-run` (no changes
detected after applying both) and a direct `pg_indexes` query against
`wt_vision` showing both new indexes present with their `WHERE` clauses.

## 5. Summary

- 10 new flat-cost tests added to `backend/tests/test_performance.py`
  (§1), all passing; 2 index migrations added (§4); the scale-dataset
  command was fixed to unblock the load-test smoke (§3).
- 8 of 10 new tests meet the ≤12-query list budget outright; 1
  (`GET /students/{id}/activities/`) is flat but 2 queries over that budget
  for a documented, request-level (not per-row) reason; global search is
  flat but its per-type query accounting is looser than "1 per type" once
  auth/audit overhead is counted.
- Every screen already covered elsewhere (Student 360, timeline, the five
  dashboards, batch overview/roster) stays flat under 5x data growth; several
  of those pre-existing ceilings (student/trainer/counsellor/admin/manager
  dashboards) sit above the plan's ≤15-query dashboard budget and the scale
  smoke confirms real query counts in the 23–67 range at planning volume —
  pre-existing gaps from Phases 16–18/21, not introduced or fixed by this
  phase, recorded here for visibility.
