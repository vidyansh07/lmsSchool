# Data model — ERP additions

Every entity the ERP adds or changes, with relationships. Existing tables are
named where the new ones attach to them; their own fields are documented in
`docs/architecture.md` and the app docstrings. Conventions for every new
table: UUID primary key, `created_at`/`updated_at` (`BaseModel`); soft delete
(`SoftDeleteBaseModel`: `deleted_at`, `deleted_by`, `delete_reason`) where a
person can delete it; every foreign key indexed; every unique constraint
partial on `deleted_at IS NULL` for soft-deletable tables; every state
change written to `AuditLog`.

Notation: `→` foreign key, `⇄` one-to-one, `*` many, `[soft]` soft-deletable.

---

## 1. Authorization

### Role `[soft]`
| Field | Type | Notes |
| --- | --- | --- |
| slug | char(60) unique | e.g. `manager`, `placement-coordinator` |
| name | char(80) | |
| description | text | |
| kind | char(12) | one of `UserRole` values; the ladder rung and scoping floor (ADR-01) |
| status | `active` / `disabled` | disabled roles cannot be assigned; existing holders keep the system role of their kind |
| is_system | bool | six seeded rows; cannot be deleted or have `kind` changed |
| is_locked | bool | only a superadmin with step-up edits a locked role |
| created_by, updated_by | → User | |

Relationships: Role *→ RolePermission; User.custom_role → Role (nullable; `custom_role.kind == user.role` enforced in the service and a check in `clean()`).

### Permission
| Field | Type | Notes |
| --- | --- | --- |
| code | char(60) unique | equals a `Capability` value, e.g. `student.view_any` |
| resource | char(30) | prefix before the dot |
| action | char(30) | suffix |
| category | char(30) | People, Academic, Operations, Configuration, Communication, System |
| description | text | |
| is_system | bool | always true — the catalog is code (ADR-01) |
| is_lockable | bool | |
| status | `active` / `retired` | retired = the enum member was removed; rows are never deleted |

A management command `sync_permissions` upserts rows from `Capability`; a test asserts equality both ways.

### RolePermission
| Field | Type | Notes |
| --- | --- | --- |
| role | → Role | |
| permission | → Permission | |
| scope | char(10) | `all`, `branch`, `assigned`, `own`; NULL = the kind's floor |
| is_locked | bool | |
| granted_by | → User | |
| unique | (role, permission) | |

### ScopeGrant
| Field | Type | Notes |
| --- | --- | --- |
| user | → User | |
| batch | → Batch (nullable) | exactly one of batch/course |
| course | → Course (nullable) | |
| granted_by | → User | |
| unique | (user, batch), (user, course) | |

Used by `assigned` scope for staff who are not the batch trainer.

### Change history (read model)
No table. `ChangeHistory` is a queryset over `AuditLog` filtered by `resource_type` and `resource_id`, rendering `context.changes` (`{field: {from, to}}`) — the shape the fee, settings and DSR services already write.

---

## 2. Authentication

### OneTimeCode
| Field | Type | Notes |
| --- | --- | --- |
| user | → User | |
| purpose | `login`, `step_up`, `enrol` | |
| code_hash | char(64) | SHA-256(salt + code) |
| salt | char(32) | |
| sent_to | char(254) | the address at send time |
| expires_at | datetime | 10 min |
| attempts | smallint | refused at 5 |
| consumed_at | datetime null | single use, `select_for_update` |
| request_ip | inet | |
| index | (user, purpose, created_at) | |

### MfaDevice
| Field | Type | Notes |
| --- | --- | --- |
| user | ⇄ User | one TOTP device per user |
| secret_encrypted | binary | Fernet with `MFA_ENCRYPTION_KEY` |
| confirmed_at | datetime null | unconfirmed devices are ignored |
| last_used_step | bigint | replay guard |
| name | char(60) | "Phone" |

### RecoveryCode
| user → User | code_hash char(64) | used_at datetime null | ten per enrolment |

### UserSession
| Field | Type | Notes |
| --- | --- | --- |
| user | → User | indexed |
| session_key_hash | char(64) unique | never the key itself |
| ip | inet | |
| user_agent | char(512) | |
| device_label | char(80) | derived: "Chrome on macOS" |
| created_at, last_seen_at | datetime | last_seen touched ≤ once / 5 min |
| revoked_at | datetime null | |

User gains: `mfa_enrolled_at` (datetime null). No other change.

---

## 3. Policies

### Policy `[soft]`
| Field | Type | Notes |
| --- | --- | --- |
| category | char(30) | one of the 16 categories (schema registry) |
| key | char(60) | e.g. `mfa.required_roles`, `session.max_age_hours` |
| scope | `global` / `branch` | |
| branch | → Branch (nullable) | required when scope = branch |
| value | JSON | validated against `POLICY_SCHEMAS[category][key]` |
| version | int | increments per write |
| updated_by | → User | |
| unique | (category, key, branch) partial on deleted_at IS NULL | |

### PolicyVersion
| policy → Policy | version int | value JSON | changed_by → User | reason char(300) | created_at |

`AcademicPolicy` (existing, two layers) and `SystemSetting` (existing singleton) remain the academic and institution categories.

---

## 4. Forms

### FormDefinition `[soft]`
| slug char(60) unique | name | entity: `activity`, `student`, `registration`, `review` | status: `active`/`archived` | created_by |

### FormVersion
| Field | Type | Notes |
| --- | --- | --- |
| definition | → FormDefinition | |
| number | int | unique with definition |
| status | `draft` / `published` / `archived` | one published per definition at a time |
| schema_hash | char(64) | hash of the field set, for change detection |
| published_at, published_by | | immutable once published (service refuses field writes) |
| cloned_from | → FormVersion null | |

### FormField
| Field | Type | Notes |
| --- | --- | --- |
| version | → FormVersion | |
| key | char(60) | unique with version; snake_case |
| label, help | | |
| type | char(20) | text, textarea, number, decimal, date, datetime, boolean, select, multiselect, radio, checkbox, email, phone, url, file, image, richtext, relation |
| required | bool | |
| order, group | int, char(60) | |
| options | JSON | for select/multiselect/radio: `[{value,label}]`; for relation: `{model: "student"|"trainer"|"batch"}` |
| validation | JSON | min, max, min_length, max_length, pattern, accept (files), max_mb |
| visible_to_student | bool | |
| performance_key | char(30) null | when set, the field's numeric value feeds the activity score (e.g. `score`) |

### FormResponse
| version → FormVersion | values JSON | content_type → ContentType | object_id uuid | created_by | index (content_type, object_id) |

File-typed values store an upload id from the existing private storage (`apps/common/uploads.py`), never a path.

---

## 5. Work (activities)

### ActivityType `[soft]`
| Field | Type | Notes |
| --- | --- | --- |
| slug, name, description | | |
| category | char(30) | interview, mentoring, counselling, review, placement, feedback, warning, follow_up, other |
| allowed_creator_roles | JSON list of role slugs | |
| allowed_assignee_roles | JSON list | |
| visible_to_student | bool | default per type; an activity may override to hidden, never to visible |
| default_duration_minutes | int | |
| form | → FormDefinition null | |
| requires_review | bool | completion goes to UNDER_REVIEW |
| performance_weight | decimal(4,2) | 0 = no effect |
| risk_effect | `none` / `score_below_threshold` | threshold from policy `risk.activity_score_below` |
| reminder_minutes_before | int null | |
| next_action | JSON null | `{when: "score_below", threshold: 6, create_type: "communication-practice", assign_to: "same_assignee"\|"batch_trainer"\|"creator", notify: ["manager"]}` |
| is_system | bool | seeded catalog rows |
| status | `active` / `disabled` | |

### Activity `[soft]`
| Field | Type | Notes |
| --- | --- | --- |
| student | → StudentProfile | |
| enrollment | → Enrollment null | the batch context |
| batch | → Batch null | denormalised from enrollment |
| branch | → Branch | scoping |
| activity_type | → ActivityType | |
| title | char(160) | defaults to the type name |
| status | char(16) | twelve statuses (§25) |
| priority | `low`/`normal`/`high`/`urgent` | |
| created_by, assigned_to, performed_by, reviewed_by | → User | |
| planned_at, started_at, due_at, completed_at, reviewed_at | datetime null | |
| duration_minutes | int null | |
| form_version | → FormVersion null | pinned at creation |
| form_response | ⇄ FormResponse null | |
| result | char(20) | `pass`, `fail`, `mixed`, `n/a` |
| score, max_score | decimal(5,2) null | normalised as score/max_score×100 |
| summary | text | |
| review_note | text | |
| student_visible | bool | |
| parent | → Activity null | the activity that generated this one |
| automation_run | → AutomationRun null | provenance |
| index | (student, -created_at), (assigned_to, status, due_at), (branch, status) | |

### ActivityHistory
| activity → Activity | actor → User null | from_status | to_status | note | changes JSON | created_at |

### RiskState
| enrollment ⇄ Enrollment | level `none`/`warning`/`critical` | triggered JSON (keys) | numbers JSON | computed_at | previous_level | previous_triggered JSON |

### PerformanceReview (existing, extended)
Adds: `review_type` char(30) (`monthly`, `quarterly`, `probation`, `ad_hoc`, `placement`), `score` decimal(4,1) null, `recommendations` text, `next_review_at` date null, `status` (`draft`, `shared`, `acknowledged`), `weaknesses` (alias of existing `concerns` — not renamed; serializer exposes both names).

### AttendanceCorrection (new history table)
| record → AttendanceRecord | from_status | to_status | corrected_by | reason | created_at |

Written by `correct_record` and by re-posted registers, alongside the audit row.

---

## 6. Automation

### AutomationRule `[soft]`
| Field | Type | Notes |
| --- | --- | --- |
| name, description | | |
| trigger | char(40) | ACTIVITY_COMPLETED, ACTIVITY_OVERDUE, ASSESSMENT_FAILED, ATTENDANCE_THRESHOLD, PROJECT_OVERDUE, ASSIGNMENT_OVERDUE, RISK_CHANGED |
| conditions | JSON | `[{path, op, value}]`, ANDed |
| actions | JSON | `[{type, params}]` |
| status | `draft` / `active` / `paused` | |
| version | int | |
| branch | → Branch null | null = every centre |
| created_by, updated_by | | |

### AutomationRun
| rule → AutomationRule | trigger | object_type, object_id | occurrence_key char(80) | depth smallint | status `queued`/`ran`/`skipped`/`failed` | result JSON | error text | created_at | unique (rule, occurrence_key) |

---

## 7. Communication

### MessageTemplate `[soft]`
| key char(60) unique | name | channel `email`/`whatsapp`/`in_app` | kind (NotificationKind or automation) | language char(8) | status `draft`/`approved`/`published` | current_version → TemplateVersion null |

### TemplateVersion
| template → MessageTemplate | number | subject | body_html | body_text | variables JSON (allowlist) | provider_template_id char(120) | approved_by, approved_at | published_at | immutable once published |

### Delivery
| Field | Type | Notes |
| --- | --- | --- |
| channel | `email` / `whatsapp` / `in_app` | |
| recipient | → User null | |
| address | char(254) | email or E.164 |
| template_version | → TemplateVersion null | |
| variables | JSON | |
| state | `queued`/`processing`/`sent`/`delivered`/`failed`/`cancelled` | |
| attempts | smallint | |
| next_attempt_at | datetime null | |
| provider_message_id | char(120) | |
| error | char(500) | scrubbed |
| related_type, related_id | | e.g. activity, announcement |
| email_message | → EmailMessage null | the transport row for the email channel |
| requested_by | → User null | |
| index | (state, next_attempt_at), (recipient, -created_at) | |

### Announcement (existing, extended)
Adds `publish_at` datetime null, statuses `scheduled`, `cancelled`, audiences `role` (with `role` → Role) and `branch` (with `branch` → Branch). Becomes `[soft]`.

### SavedFilter
| user → User | screen char(60) | name | filters JSON | unique (user, screen, name) |

---

## 8. Relationships (overview)

```
User ─ role(kind) ─┬─ custom_role → Role ─* RolePermission → Permission
                   ├─* ScopeGrant → Batch | Course
                   ├─⇄ MfaDevice, * RecoveryCode, * OneTimeCode, * UserSession
                   └─* SavedFilter
Branch ─* Policy (branch scope) ─* PolicyVersion
FormDefinition ─* FormVersion ─* FormField ; FormVersion ─* FormResponse ─(generic)→ Activity | StudentProfile
StudentProfile ─* Activity ─ ActivityType (─ form → FormDefinition)
Activity ─* ActivityHistory ; Activity ─ parent → Activity ; Activity ─ automation_run → AutomationRun → AutomationRule
Enrollment ─⇄ RiskState
AttendanceRecord ─* AttendanceCorrection
MessageTemplate ─* TemplateVersion ─* Delivery ─ email_message → EmailMessage (existing outbox)
Announcement ─ role → Role ; Announcement ─ branch → Branch
AuditLog (existing) ← every write above
```

## 9. Indexing summary

| Table | Indexes beyond FKs |
| --- | --- |
| Activity | (student, -created_at), (assigned_to, status, due_at), (branch, status), (due_at) partial where status in (planned, assigned, in_progress) |
| Delivery | (state, next_attempt_at), (recipient, -created_at) |
| OneTimeCode | (user, purpose, created_at) |
| UserSession | (user), unique(session_key_hash) |
| AutomationRun | unique(rule, occurrence_key) |
| Policy | unique(category, key, branch) partial |
| FormField | unique(version, key) |

## 10. Soft-delete and history implications

- Deleting an ActivityType is refused while live activities reference it (PROTECT + service check); disabled instead.
- Deleting an Activity hides it from the timeline and performance; restoring re-includes it and triggers a risk recompute.
- Deleting a Role is refused while users hold it; system roles cannot be deleted.
- FormVersions and TemplateVersions are never deleted: a response or delivery keeps pointing at the version that produced it (D-019 extended to configuration history).
