# Automation catalog

Automations are rows (`AutomationRule`) evaluated by a fixed vocabulary
(ADR-13). This catalog defines the vocabulary — triggers, their context,
conditions, actions — and the rules seeded at install. Nothing here runs
code a person typed.

## Triggers and their context

Each trigger exposes an allowlisted context. A condition path must be one
of the listed keys; anything else is refused when the rule is saved.

| Trigger | Fired by | Context paths |
| --- | --- | --- |
| ACTIVITY_COMPLETED | `work.services.complete_activity` (on commit) | activity.id, activity.type (slug), activity.category, activity.score (0–100 normalised), activity.result, activity.performed_by_role, form.<key> for every numeric/select field of the pinned form, student.id, student.batch, student.branch, student.risk_level |
| ACTIVITY_OVERDUE | beat `work.mark_overdue` (every 15 min) | activity.id, activity.type, activity.assigned_to_role, activity.days_overdue, student.* |
| ASSESSMENT_FAILED | `assessments.services.record_result` when percent < policy passing | assessment.id, assessment.percent, assessment.attempt_number, student.*, batch.trainer |
| ATTENDANCE_THRESHOLD | `risk.recompute` when attendance percent crosses `risk.attendance_percent` downward | attendance.percent, attendance.absent_streak, student.* |
| PROJECT_OVERDUE | beat `work.mark_overdue` | project.id, project.days_overdue, student.* |
| ASSIGNMENT_OVERDUE | beat `work.mark_overdue` | assignment.id, assignment.days_overdue, student.* |
| RISK_CHANGED | `risk.recompute` when level or triggered set changes | risk.level, risk.previous_level, risk.triggered (list), risk.newly_triggered (list), student.* |

`student.*` always means: id, name, batch, branch, trainer (user id),
counsellor (user id of `created_by` on the profile), risk_level.

## Conditions

`[{ "path": "form.communication", "op": "lt", "value": 6 }]` — all must
hold. Operators: `eq`, `ne`, `lt`, `lte`, `gt`, `gte`, `in`, `not_in`,
`contains` (list or string). Values are literals only. Missing path → the
condition is false (never an error).

## Actions

| Action | Params | Permission the rule's author must hold | Notes |
| --- | --- | --- | --- |
| create_activity | type (slug), assign_to (`same_assignee` / `batch_trainer` / `counsellor` / `creator` / user id), due_in_days, priority, title | activity.create | `parent` = triggering activity; `automation_run` set |
| send_notification | to (`student` / `trainer` / `counsellor` / `manager` / `assignee` / role slug), kind (a NotificationKind), title, body (variables `{{student.name}}` etc. from the context) | communication.send | in-app, email by preference |
| send_email | to (as above or address), template (published key) | communication.send | through `Delivery`, channel email |
| send_whatsapp | to, template (published key with provider id) | communication.send | requires an approved template and a configured provider; otherwise the run is `skipped` with reason |
| create_review | review_type, reviewer (`manager` / user id), due_in_days | review.manage_any | creates a draft `PerformanceReview` |
| flag_risk | level (`warning` / `critical`), reason | review.manage_any | writes a manual `RiskState` override with expiry (policy `risk.manual_flag_days`) |

An action that needs a permission the author lacks cannot be saved; a rule
whose author later loses the permission is paused by `sync` and shown as
such in the builder.

## Guards

- **Idempotency**: `AutomationRun.occurrence_key` = `f"{trigger}:{object_id}:{occurrence}"` where `occurrence` is the activity completion id, the overdue day, or the risk computed_at. Unique per rule.
- **Depth**: a run carries `depth`; an action fired by a run at depth 3 is skipped and logged.
- **Rate**: at most `automation.max_runs_per_object_per_day` (policy, default 10) runs per object.
- **Dry run**: the builder's "Test against a recent event" evaluates conditions and lists the actions without executing them.
- **Audit**: every run writes `automation.ran` / `automation.skipped` / `automation.failed` with the rule version.

## Seeded rules (`is_system=False`, editable, all `active`)

| Name | Trigger | Conditions | Actions | Notification | Audit |
| --- | --- | --- | --- | --- | --- |
| Communication practice after a weak mock | ACTIVITY_COMPLETED | activity.type eq mock-interview; form.communication lt 6 | create_activity(communication-practice, same_assignee, due 7 d); send_notification(manager, activity.assigned) | manager | automation.ran |
| Doubt session after a weak technical interview | ACTIVITY_COMPLETED | activity.type eq technical-interview; activity.score lt 60 | create_activity(doubt-session, batch_trainer, due 5 d) | trainer | automation.ran |
| Resume again if revise | ACTIVITY_COMPLETED | activity.type eq resume-review; form.outcome eq revise | create_activity(resume-review, same_assignee, due 7 d) | trainer | |
| Not ready for placement | ACTIVITY_COMPLETED | activity.type eq placement-call; form.outcome eq not_ready | create_activity(mock-interview, batch_trainer, due 7 d); send_notification(manager) | manager | |
| Attendance counselling | ATTENDANCE_THRESHOLD | attendance.percent lt 75 | create_activity(attendance-counselling, counsellor, due 3 d); send_notification(student, attendance.warning) | student, counsellor | |
| Failed a test twice | ASSESSMENT_FAILED | assessment.attempt_number gte 2 | create_activity(doubt-session, batch_trainer, due 5 d); send_notification(manager) | manager | |
| Overdue activity nudge | ACTIVITY_OVERDUE | activity.days_overdue gte 2 | send_notification(assignee, activity.overdue); send_notification(manager, activity.overdue) | assignee, manager | |
| Risk went critical | RISK_CHANGED | risk.level eq critical; risk.previous_level ne critical | send_notification(manager, risk.changed); send_notification(counsellor, risk.changed); create_review(ad_hoc, manager, due 7 d) | manager, counsellor | |
| Project overdue | PROJECT_OVERDUE | project.days_overdue gte 3 | send_notification(student, project.overdue); send_notification(trainer) | student, trainer | |

Every seeded rule can be paused from the builder; none is locked.

## Builder screen contract (see DESIGN_DECISIONS §Automation Builder)

Pick trigger → the condition editor offers only that trigger's paths →
add actions from the list, each with its typed parameter form → "Test"
(dry run against the last 20 events of that trigger, shows would-fire /
would-not) → Save as draft → Activate (explicit confirmation naming how
many events per day it matched in the last 7 days).
