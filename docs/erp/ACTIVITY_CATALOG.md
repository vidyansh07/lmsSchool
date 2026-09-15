# Activity catalog

The seeded `ActivityType` rows (`is_system=True`). An administrator can add
types, disable these, or change any column except `slug`. "Form" names the
seeded `FormDefinition` from `FORM_CATALOG.md`. "Performance" is the type's
weight in the activity component (ADR-10); 0 = no effect. "Risk" says whether
a low score feeds the activity-risk rule (ADR-11). "Next action" is the seeded
`next_action` JSON, if any.

Role names are role slugs; `trainer` includes managers who hold a teaching
profile (D-130).

| Slug | Name | Category | Form | Creators | Assignees | Student sees | Default duration | Review | Performance | Risk | Next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| mock-interview | Mock Interview | interview | mock-interview | manager, trainer | trainer | yes (score + feedback) | 30 min | no | 1.0 | score < threshold | score < 6 → `communication-practice`, assign same trainer, notify manager |
| technical-interview | Technical Interview | interview | technical-interview | manager, trainer | trainer | yes | 45 min | no | 1.0 | score < threshold | score < 6 → `doubt-session`, assign batch trainer |
| hr-interview | HR Interview | interview | hr-interview | manager | trainer, manager | yes | 30 min | no | 0.5 | score < threshold | — |
| mentoring | Mentoring | mentoring | mentoring-note | manager, trainer | trainer | yes (summary only) | 30 min | no | 0 | no | — |
| counselling | Counselling | counselling | counselling-note | manager, counsellor | counsellor, manager | no | 30 min | no | 0 | no | — |
| career-guidance | Career Guidance | counselling | counselling-note | manager, counsellor | counsellor, manager | yes (summary) | 30 min | no | 0 | no | — |
| doubt-session | Doubt Session | mentoring | doubt-session | trainer, manager, student (request) | trainer | yes | 30 min | no | 0 | no | — |
| code-review | Code Review | review | code-review | trainer, manager | trainer | yes (score + comments) | 30 min | no | 1.0 | score < threshold | — |
| resume-review | Resume Review | placement | resume-review | manager, counsellor, trainer | trainer, manager | yes | 20 min | no | 0.5 | placement rule | score < 6 → `resume-review` again in 7 days |
| project-review | Project Review | review | project-review | trainer, manager | trainer | yes | 45 min | yes (manager) | 1.0 | score < threshold | — |
| placement-call | Placement Call | placement | placement-call | manager, counsellor | counsellor, manager | no | 15 min | no | 0 | placement rule (outcome) | outcome = not_ready → `mock-interview`, assign batch trainer |
| feedback | Feedback | feedback | feedback-note | any staff | — | configurable (default yes) | — | no | 0 | no | — |
| parent-meeting | Parent Meeting | counselling | parent-meeting | counsellor, manager | counsellor, manager | no | 30 min | no | 0 | no | — |
| warning | Warning | warning | warning-note | manager | — | yes | — | yes (admin acknowledges) | 0 | yes (count) | — |
| performance-review | Performance Review | review | (uses PerformanceReview) | manager | manager | yes when shared | — | no | 0 | no | — |
| follow-up | Follow-up | follow_up | follow-up-note | counsellor, manager, trainer | counsellor, trainer | no | 10 min | no | 0 | no | — |
| communication-practice | Communication Practice | mentoring | communication-practice | trainer, manager, automation | trainer | yes | 30 min | no | 0.5 | score < threshold | score ≥ 7 → none; score < 5 after 2 sessions → notify manager |
| attendance-counselling | Attendance Counselling | counselling | counselling-note | automation, manager, counsellor | counsellor | no | 20 min | no | 0 | no | created by the ATTENDANCE_THRESHOLD automation |

## Lifecycle (§25)

Statuses: DRAFT, PLANNED, ASSIGNED, IN_PROGRESS, COMPLETED, MISSED, OVERDUE,
CANCELLED, REOPENED, UNDER_REVIEW, APPROVED, REQUIRES_ACTION.

| From | To | Who | Rule |
| --- | --- | --- | --- |
| DRAFT | PLANNED, CANCELLED | creator | planned_at required for PLANNED |
| PLANNED | ASSIGNED, CANCELLED | creator, activity.assign | assignee required |
| ASSIGNED | IN_PROGRESS, MISSED, CANCELLED | assignee (start), system (missed after planned_at + grace) | |
| ASSIGNED, IN_PROGRESS | OVERDUE | system | due_at passed and not completed; a person cannot set it |
| IN_PROGRESS, OVERDUE, ASSIGNED | COMPLETED | assignee, activity.complete | form valid; score within max; if type.requires_review → UNDER_REVIEW instead |
| COMPLETED | UNDER_REVIEW | reviewer | only for types that require review — set by the system on completion |
| UNDER_REVIEW | APPROVED, REQUIRES_ACTION | activity.review, not the performer | note required for REQUIRES_ACTION |
| REQUIRES_ACTION | IN_PROGRESS | assignee | |
| MISSED, CANCELLED, COMPLETED, APPROVED | REOPENED | activity.review or creator | reason required; audit |
| REOPENED | ASSIGNED | creator | |

Terminal for performance purposes: COMPLETED and APPROVED. Only those feed
the performance component and the risk rule. UNDER_REVIEW counts as pending
work for the trainer.

## What completing an activity does (in order, one transaction + tasks)

1. Validate the form response against the pinned `FormVersion`.
2. Derive `score` from the field flagged `performance_key` (or the explicit
   score field), `result` from the form's `outcome` field when present.
3. Write `Activity` + `FormResponse` + `ActivityHistory`; audit
   `activity.completed`.
4. On commit: `risk.recompute(enrollment)`, `automation.dispatch(
   ACTIVITY_COMPLETED, activity)`, notifications per the type's
   `notify` settings (student if visible; creator if different from
   performer; reviewer if review required).
5. The type's own `next_action` runs through the automation engine as a
   system rule so it is logged as an `AutomationRun` like any other.

## Student visibility

A student sees an activity only when `type.visible_to_student` and the
activity's `student_visible` are both true, and then only the fields whose
`FormField.visible_to_student` is true. Counselling, placement calls,
parent meetings and follow-ups are never shown.

## Trainer work metrics (§31)

Per trainer, per period: assigned, completed, pending, overdue, by type,
median completion time, review outcomes. Each number links to the list it
was counted from (the same "provenance" rule as performance).
