# Permission catalog

The catalog is the `Capability` enum in `backend/apps/accounts/roles.py`,
mirrored into `Permission` rows (ADR-01). This document lists every code —
the 71 that exist plus the 24 the ERP adds — with its resource, action,
allowed scopes, which system roles hold it by default, and whether it may be
locked. Scope column lists the scopes an administrator may choose for a
custom role; the effective scope can never exceed the role kind's floor
(ADR-02): superadmin/admin `all`, manager/counsellor `branch`, trainer
`assigned`, student `own`.

Categories: **People**, **Academic**, **Operations**, **Configuration**,
**Communication**, **System**.

## Existing (71)

| Code | Category | Scopes | Superadmin | Admin | Manager | Counsellor | Lockable |
| --- | --- | --- | --- | --- | --- | --- | --- |
| user.view_any | People | all, branch | ✓ | ✓ | ✓ | ✓ | |
| user.create | People | all, branch | ✓ | ✓ | | | ✓ |
| user.update_any | People | all, branch | ✓ | ✓ | | | ✓ |
| user.set_active | People | all, branch | ✓ | ✓ | | | ✓ |
| user.change_role | People | all, branch | ✓ | ✓ | | | ✓ |
| profile.view_own | People | own | everyone | | | | |
| profile.update_own | People | own | everyone | | | | |
| student.view_any | People | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | |
| student.create | People | all, branch | ✓ | ✓ | ✓ | ✓ | |
| student.update_any | People | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | |
| student.set_fee_status | People | all, branch | ✓ | ✓ | ✓ | ✓ | |
| fee.view_any | People | all, branch | ✓ | ✓ | ✓ | ✓ | |
| fee.manage_any | People | all, branch | ✓ | ✓ | ✓ | ✓ | ✓ |
| trainer.view_any | People | all, branch | ✓ | ✓ | ✓ | ✓ | |
| trainer.create | People | all, branch | ✓ | ✓ | ✓ | | |
| trainer.update_any | People | all, branch | ✓ | ✓ | ✓ | | |
| platform.configure | Configuration | all | ✓ | | | | ✓ |
| audit.view | System | all, branch | ✓ | ✓ | | | ✓ |
| organisation.view_any | Configuration | all, branch | ✓ | ✓ | ✓ | ✓ | |
| organisation.manage | Configuration | all | ✓ | ✓ | | | ✓ |
| organisation.assign_users | Configuration | all | ✓ | ✓ | | | ✓ |
| settings.manage | Configuration | all | ✓ | ✓ | | | ✓ |
| record.view_deleted | System | all, branch | ✓ | ✓ | | | |
| record.restore | System | all, branch | ✓ | ✓ | | | |
| record.purge | System | all | ✓ | | | | ✓ locked by default |
| academic.configure | Configuration | all | ✓ | ✓ | | | ✓ |
| category.manage | Academic | all | ✓ | ✓ | ✓ | ✓ | |
| course.view_any | Academic | all | ✓ | ✓ | ✓ | ✓ | |
| course.create | Academic | all | ✓ | ✓ | ✓ | ✓ | |
| course.update_any | Academic | all, assigned | ✓ | ✓ | ✓ | ✓ | |
| course.publish_any | Academic | all | ✓ | ✓ | ✓ | ✓ | |
| course.assign_authors | Academic | all | ✓ | ✓ | ✓ | ✓ | |
| batch.view_any | Academic | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | |
| batch.create | Academic | all, branch | ✓ | ✓ | ✓ | ✓ | |
| batch.update_any | Academic | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | |
| batch.manage_schedule | Academic | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | |
| enrolment.view_any | Academic | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | |
| enrolment.create | Academic | all, branch | ✓ | ✓ | ✓ | ✓ | |
| enrolment.update_any | Academic | all, branch | ✓ | ✓ | ✓ | ✓ | |
| session.manage_any | Operations | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | |
| attendance.correct_any | Operations | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | |
| attendance.view_any | Operations | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | |
| dsr.view_any | Operations | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | |
| dsr.manage_any | Operations | all, branch | ✓ | ✓ | ✓ | ✓ | |
| dsr.review | Operations | all, branch | ✓ | ✓ | ✓ | ✓ | |
| performance.view_any | Operations | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | |
| review.manage_any | Operations | all, branch | ✓ | ✓ | ✓ | ✓ | |
| assignment.view_any | Academic | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | |
| assignment.manage_any | Academic | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | |
| assignment.grade_any | Academic | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | |
| assessment.view_any | Academic | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | |
| assessment.manage_any | Academic | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | |
| result.manage_any | Academic | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | |
| project.view_any | Academic | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | |
| project.manage_any | Academic | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | |
| project.review_any | Academic | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | |
| question.view_any | Academic | all | ✓ | ✓ | ✓ | ✓ | |
| question.manage_any | Academic | all | ✓ | ✓ | ✓ | ✓ | |
| exam.view_any | Academic | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | |
| exam.manage_any | Academic | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | |
| exam.grade_any | Academic | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | |
| completion.view_any | Academic | all, branch | ✓ | ✓ | ✓ | ✓ | |
| completion.approve | Academic | all, branch | ✓ | ✓ | | | ✓ |
| certificate.manage | Academic | all, branch | ✓ | ✓ | | | ✓ |
| announcement.manage_any | Communication | all, branch | ✓ | ✓ | ✓ | ✓ | |
| requirement.manage | Communication | all, branch | ✓ | ✓ | ✓ | | |
| discussion.moderate_any | Communication | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | |
| report.view_any | System | all, branch | ✓ | ✓ | ✓ | ✓ | |
| data.export | System | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | ✓ |
| data.import | System | all, branch | ✓ | ✓ | ✓ | ✓ | ✓ |
| export.view_any | System | all, branch | ✓ | ✓ | | | |

Trainer and student system roles hold only `profile.*`; their reach is per
record (D-015) and unchanged.

## Added by the ERP (24)

| Code | Category | Scopes | Superadmin | Admin | Manager | Counsellor | Trainer | Lockable | Phase |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| role.view | Configuration | all | ✓ | ✓ | | | | | 1 |
| role.manage | Configuration | all | ✓ | ✓ | | | | ✓ | 1 |
| permission.assign | Configuration | all | ✓ | ✓ | | | | ✓ | 1 |
| permission.lock | Configuration | all | ✓ | | | | | ✓ locked | 2 |
| policy.view | Configuration | all, branch | ✓ | ✓ | ✓ | | | | 3 |
| policy.manage | Configuration | all, branch | ✓ | ✓ | | | | ✓ | 3 |
| session.view_any | System | all, branch | ✓ | ✓ | | | | | 6 |
| session.revoke_any | System | all, branch | ✓ | ✓ | | | | ✓ | 6 |
| form.view | Configuration | all | ✓ | ✓ | ✓ | ✓ | | | 8 |
| form.manage | Configuration | all | ✓ | ✓ | | | | ✓ | 8 |
| activity_type.manage | Configuration | all | ✓ | ✓ | | | | ✓ | 9 |
| activity.view_any | Operations | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | (assigned) | | 9 |
| activity.create | Operations | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | (assigned) | | 9 |
| activity.assign | Operations | all, branch | ✓ | ✓ | ✓ | ✓ | | | 9 |
| activity.complete | Operations | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | (assigned) | | 9 |
| activity.review | Operations | all, branch | ✓ | ✓ | ✓ | | | | 9 |
| activity.delete | Operations | all, branch | ✓ | ✓ | ✓ | | | | 9 |
| automation.manage | Configuration | all | ✓ | ✓ | | | | ✓ | 14 |
| template.manage | Communication | all | ✓ | ✓ | | | | ✓ | 19 |
| template.approve | Communication | all | ✓ | ✓ | | | | ✓ | 19 |
| communication.send | Communication | all, branch, assigned | ✓ | ✓ | ✓ | ✓ | | ✓ | 19 |
| communication.view_any | Communication | all, branch | ✓ | ✓ | ✓ | ✓ | | | 19 |
| search.global | System | all, branch, assigned, own | everyone | | | | | | 11 |
| saved_filter.manage | System | own | everyone | | | | | | 11 |

Trainer "(assigned)" means the trainer system role gains the permission with
scope `assigned` for the batches they teach, so a trainer can create,
complete and see activities for their own students without a global grant —
the same per-record rule as assignments and DSRs, made explicit as a grant
so a custom trainer-kind role can be narrowed further.

## Locking rules

- `permission.lock` is itself locked to superadmin at seed time.
- A locked grant on a system role cannot be removed by anyone but a
  superadmin with a step-up (ADR-03). The matrix renders it as **Locked**.
- `record.purge` and `platform.configure` are seeded locked on superadmin
  and absent everywhere else; the service refuses to grant them to any
  non-superadmin-kind role.
- Locking never *adds* a permission; it only freezes the current answer.

## Role examples

| Custom role | Kind | Built from | Change |
| --- | --- | --- | --- |
| Placement coordinator | manager | manager | − fee.manage_any, − dsr.review; + activity.* limited to category placement (a *type* restriction, on the ActivityType's allowed roles) |
| Front desk | counsellor | counsellor | − enrolment.update_any, − batch.create; keeps student.create and fee.manage_any |
| Senior trainer | trainer | trainer | + dsr.review (scope assigned) so they can review a junior's report for their own batch |
| Read-only auditor | admin | admin | every `*.view*` plus audit.view, nothing that writes; locked |

## Drift protection

- `sync_permissions` runs in the migration that creates the table and on
  every deploy (`deploy.sh` step 3c); it is idempotent.
- `tests/test_permission_catalog.py` asserts set(Permission.code) ==
  set(Capability.values) and that every view's `required_capability` is in
  the enum.
- `frontend/tests/unit/capability-mirror.test.ts` (exists) keeps the
  frontend names equal to the backend's.
