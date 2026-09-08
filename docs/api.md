# API reference (Phase 3)

The authoritative contract is the generated OpenAPI document:

- Schema: `GET /api/schema/`
- Swagger UI: `GET /api/docs/` (local, development and staging; off in production unless enabled)

This page summarises the conventions and the endpoints that exist today.

---

## Conventions

**Base URL and versioning.** All application endpoints live under `/api/v1/`.
Health checks are unversioned so orchestrators need not track API versions.

**Content type.** JSON only, both directions.

**Authentication.** Session cookie. A browser client:

1. `GET /api/v1/auth/csrf/` — sets the `grras_csrftoken` cookie
2. `POST /api/v1/auth/login/` with the cookie value in the `X-CSRFToken` header
3. Subsequent requests send the session cookie; unsafe methods must keep
   sending `X-CSRFToken`

`credentials: 'include'` is required on every cross-origin request. The
bundled client (`frontend/lib/api.ts`) handles all of this.

**Errors.** Every failure returns:

```json
{
  "error": {
    "code": "validation_error",
    "message": "The submitted data is invalid.",
    "details": { "email": ["Enter a valid email address."] },
    "request_id": "0f3c1a4b…"
  }
}
```

| `code` | HTTP | Meaning |
| --- | --- | --- |
| `validation_error` | 400 | Input rejected; `details` holds field errors |
| `bad_request` | 400 | Malformed request |
| `authentication_required` | 401 / 403 | No valid session |
| `authentication_failed` | 401 | Invalid credentials (never says which part) |
| `permission_denied` | 403 | Authenticated, but not allowed |
| `csrf_failed` | 403 | Missing or invalid CSRF token |
| `not_found` | 404 | No such resource |
| `method_not_allowed` | 405 | Wrong HTTP method |
| `conflict` | 409 | Conflicts with current state |
| `rate_limited` | 429 | Too many requests; `details.retry_after_seconds` |
| `invalid_token` | 400 | Password-reset or verification link is unknown, expired or already used |
| `invalid_transition` | 400 | The requested status change is not allowed from the current one |
| `schedule_conflict` | 409 | The class would double-book a trainer or a batch |
| `batch_full` | 409 | No seats left on the batch |
| `duplicate_enrollment` | 409 | The student already holds a live enrolment on that batch |
| `internal_error` | 500 | Unexpected failure; quote `request_id` to support |

**Pagination.** `?page=2&page_size=50`, capped at 100.

```json
{
  "count": 13, "page": 1, "page_size": 25, "total_pages": 1,
  "next": null, "previous": null, "results": [ ]
}
```

**Rate limits.** 60/min anonymous, 600/min authenticated, 10/min on
authentication endpoints (all configurable per environment).

**Request ids.** Every response carries `X-Request-ID`; error bodies repeat it
as `request_id`. A client-supplied `X-Request-ID` is honoured only when it
matches `^[A-Za-z0-9._-]{8,64}$`.

---

## Endpoints

### Health and discovery

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `/health/live/` | public — never touches the database |
| `GET` | `/health/ready/` | public — 200 healthy, 503 degraded |
| `GET` | `/api/` | public — version discovery |

### Authentication — `/api/v1/auth/`

| Method | Path | Access | Notes |
| --- | --- | --- | --- |
| `GET` | `csrf/` | public | Sets the `grras_csrftoken` cookie |
| `POST` | `login/` | public, rate limited | Identical 401 for every failure reason |
| `POST` | `logout/` | authenticated | Ends the current session |
| `POST` | `logout-all/` | authenticated | Revokes every session, including this one |
| `GET` | `me/` | authenticated | Current user plus their capability list |
| `PATCH` | `me/` | authenticated | First name, last name, phone — nothing else |
| `GET` | `me/email/` | authenticated | Email verification status |
| `POST` | `me/profile-image/` | authenticated | Multipart upload, re-encoded server-side |
| `DELETE` | `me/profile-image/` | authenticated | Remove the image |
| `POST` | `password/change/` | authenticated, rate limited | Requires the current password |
| `POST` | `password/reset/` | public, rate limited | Always 202, identical for unknown addresses |
| `POST` | `password/reset/confirm/` | public, rate limited | Single-use, expiring token |
| `POST` | `email/verify/` | authenticated, rate limited | Sends (or resends) the link |
| `POST` | `email/verify/confirm/` | public, rate limited | Single-use, expiring token |

### Users — `/api/v1/users/`

| Method | Path | Capability |
| --- | --- | --- |
| `GET` | `` | `user.view_any` |
| `POST` | `` | `user.create` |
| `GET` | `<id>/` | `user.view_any` |
| `PATCH` | `<id>/` | `user.update_any` (plus `user.change_role` to alter a role) |
| `POST` | `<id>/set-active/` | `user.set_active` |
| `GET` | `<id>/profile-image/` | any authenticated, active user |
| `DELETE` | `<id>/profile-image/remove/` | `user.update_any` |

Listing supports `?search=`, `?role=`, `?is_active=`, `?is_email_verified=`,
`?joined_after=`, `?joined_before=`, `?ordering=` and pagination. Search matches
name, email, student ID and trainer ID.

### Students — `/api/v1/students/`

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `` | `student.view_any` |
| `POST` | `` | `student.create` — creates the account and profile together |
| `GET` | `me/` | the signed-in student |
| `PATCH` | `me/` | the signed-in student, self-editable fields only |
| `GET` | `<id>/` | `student.view_any`, or the owner |
| `PATCH` | `<id>/` | `student.update_any`, or the owner (restricted fields) |
| `POST` | `<id>/fee-status/` | `student.set_fee_status` |
| `POST` | `<id>/fee-amount/` | `student.set_fee_status` — set or clear (`null`) the agreed fee |

Filters: `?fee_status=`, `?qualification=`, `?city=`, `?is_active=`, `?search=`
(student ID, name, email, institution), `?institution=` (contains),
`?institution_kind=`, `?referred_by=<student id>`, `?ordering=`.

**The agreed fee.** `POST /students/` accepts a top-level `fee_amount` (rupees,
minimum 1000, two decimals) alongside `profile`; it is checked against
`student.set_fee_status` in the service, so creating a student and quoting a
fee are two permissions even though they arrive in one request. `null` means
"not decided"; zero is refused. Students read `fee_amount` on `me/` and cannot
change it — it is not in the self-editable set, and the strict serializer names
the field rather than ignoring it. Every change is audited with both values
(`student.fee_amount.changed`).

**College or employer.** `profile.institution` is the name; `profile.institution_kind`
says which it is (`college` | `employer` | empty). Both are self-editable.

**Referrals.** A working professional who joins to learn a new skill is also a
channel, so a counsellor may record `profile.referred_by` — the id of the
existing student who sent them — at registration or later via `PATCH <id>/`.
Not self-editable (a student naming their own referrer is how a scheme gets
gamed), never the student themselves, and it survives the referrer's record
being removed. Reads carry `referred_by_label` ("Priya Shah (GRS-S-00012)");
the admin view adds `referrals_count`, and `?referred_by=` lists them.

### Trainers — `/api/v1/trainers/`

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `` | `trainer.view_any` |
| `POST` | `` | `trainer.create` |
| `GET` | `me/` | the signed-in trainer |
| `PATCH` | `me/` | the signed-in trainer, self-editable fields only |
| `GET` | `<id>/` | `trainer.view_any`, or the owner |
| `PATCH` | `<id>/` | `trainer.update_any`, or the owner (restricted fields) |

Filters: `?skill=`, `?is_accepting_assignments=`, `?min_experience=`,
`?search=` (trainer ID, name, email, title), `?ordering=`.

### Categories — `/api/v1/categories/`

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `` | any signed-in user (retired categories are hidden from non-managers) |
| `POST` | `` | `category.manage` |
| `GET` | `<id>/` | `category.manage` |
| `PATCH` | `<id>/` | `category.manage` |

### Courses — `/api/v1/courses/`

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `` | any signed-in user — scoped to what they may see |
| `POST` | `` | `course.create` |
| `GET` | `mine/` | any signed-in user — courses they may author |
| `GET` | `<id-or-slug>/` | visible to the caller |
| `PATCH` | `<id-or-slug>/` | assigned author, or `course.update_any` |
| `POST` | `<id>/status/` | assigned owner or `course.publish_any` (an editor may only submit for review) |
| `GET` | `<id>/publish-checklist/` | anyone who may manage the course |
| `GET` | `<id>/thumbnail/` | visible to the caller |
| `POST` | `<id>/thumbnail/` | anyone who may manage the course |
| `GET` | `<id>/authors/` | `course.assign_authors` |
| `POST` | `<id>/authors/` | `course.assign_authors` |
| `DELETE` | `<id>/authors/<user_id>/` | `course.assign_authors` |
| `GET` | `<id>/modules/` | visible to the caller |
| `POST` | `<id>/modules/` | anyone who may manage the course |
| `POST` | `<id>/modules/reorder/` | anyone who may manage the course |

Listing supports `?search=` (title, code, description), `?category=<slug>`,
`?difficulty=`, `?status=`, `?visibility=`, `?mine=true`, `?ordering=` and
pagination. Filters never widen visibility: a student passing `?status=draft`
gets an empty page, not a draft.

### Modules — `/api/v1/modules/`

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `<id>/` | visible to the caller |
| `PATCH` / `DELETE` | `<id>/` | anyone who may manage the parent course |
| `POST` | `<id>/status/` | anyone who may manage the parent course |
| `GET` | `<id>/lessons/` | visible to the caller |
| `POST` | `<id>/lessons/` | anyone who may manage the parent course |
| `POST` | `<id>/lessons/reorder/` | anyone who may manage the parent course |

### Lessons — `/api/v1/lessons/`

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `<id>/` | course visible **and** content entitlement |
| `PATCH` / `DELETE` | `<id>/` | anyone who may manage the parent course |
| `POST` | `<id>/status/` | anyone who may manage the parent course |
| `GET` | `<id>/video/` | content entitlement — the only place a playback URL is issued |
| `GET` | `<id>/resources/` | content entitlement |
| `POST` | `<id>/resources/` | anyone who may manage the parent course (multipart upload) |
| `POST` | `<id>/resources/link/` | anyone who may manage the parent course |

### Resources — `/api/v1/resources/`

| Method | Path | Access |
| --- | --- | --- |
| `PATCH` / `DELETE` | `<id>/` | anyone who may manage the parent course |
| `GET` | `<id>/download/` | content entitlement; served as an attachment |

---

## Course access model

Three separate questions, answered by `apps/courses/access.py`:

| Question | Rule |
| --- | --- |
| **May I see this course exists?** | `course.view_any`, or an authoring assignment, or the course is published and its visibility is public/internal |
| **May I read its content?** | The above, **plus** — the lesson is a free preview, or the caller may manage the course, or (when `COURSE_CONTENT_REQUIRES_ENROLMENT` is off) any viewer |
| **May I change it?** | `course.update_any`, or an authoring assignment. Status changes additionally need `course.publish_any` or the `owner` assignment role |

Listing endpoints apply the first rule **as a queryset**, so paging, sorting and
filtering cannot reach past it. Detail endpoints resolve the record inside that
queryset, which is why a guessed identifier returns 404 rather than 403 — the
record is not merely forbidden, it is not in the caller's world at all.

### The enrolment seam

`COURSE_CONTENT_REQUIRES_ENROLMENT` is `False` in Phase 2 because enrolment does
not exist yet. Turning it on restricts non-preview lesson bodies, resources and
video to enrolled students; `access.is_enrolled` is the single function Phase 3
replaces. The gated behaviour is already covered by tests, so the switch is one
flag and one function body.

---

## Publishing workflow

```
DRAFT ──────────► IN_REVIEW ──────────► PUBLISHED ──────────► ARCHIVED
  │                   │                     │                     │
  └───────────────────┴─────────────────────┴─────────────────────┘
                    (back to DRAFT)
```

| From | To | Who |
| --- | --- | --- |
| draft | in_review | any assigned author |
| draft | published | owner or `course.publish_any` |
| in_review | published / draft | owner or `course.publish_any` |
| published | archived / draft | owner or `course.publish_any` |
| archived | draft | owner or `course.publish_any` |

Publishing is refused unless the course has a title, a description, at least one
published module and at least one published lesson inside it.
`GET /courses/<id>/publish-checklist/` returns the outstanding blockers.

Editing a published course is allowed but recorded: the audit entry carries
`published_course_edited` and the previous values of the changed fields.

---

## Content types

| Type | Requires | Notes |
| --- | --- | --- |
| `text` | `text_content` | Rendered as plain text, never as HTML |
| `video` | a `video` object | Metadata only; the URL comes from the playback endpoint |
| `document` | an attached file resource | Enforced at publish time |
| `external_link` | `external_url` | https only, opened with `noopener` |

Adding a type means one enum member plus one entry in
`LESSON_CONTENT_REQUIREMENTS`, and one branch in the lesson renderer.

---

### Batches — `/api/v1/batches/`

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `` | any signed-in user — scoped to what they may see |
| `POST` | `` | `batch.create` |
| `GET` | `<id>/` | visible to the caller |
| `PATCH` | `<id>/` | `batch.update_any` |
| `POST` | `<id>/status/` | `batch.update_any` |
| `POST` | `<id>/trainer/` | `batch.update_any` — refuses timetable clashes |
| `GET` | `<id>/roster/` | `enrolment.view_any`, or the batch's own trainer |
| `GET` | `<id>/schedules/` | visible to the caller |
| `POST` | `<id>/schedules/` | `batch.manage_schedule` |

Filters: `?status=`, `?course=<slug>`, `?trainer=<uuid>`, `?starts_after=`,
`?starts_before=`, `?search=` (code, name, course), `?ordering=`.

### Schedules — `/api/v1/schedules/`

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `<id>/` | visible through the parent batch |
| `PATCH` / `DELETE` | `<id>/` | `batch.manage_schedule` |

### Enrolments — `/api/v1/enrollments/`

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `` | scoped: a student sees their own, a trainer sees their batches', an administrator sees all |
| `POST` | `` | `enrolment.create` |
| `GET` | `mine/` | the signed-in student's own enrolments |
| `GET` | `<id>/` | the owner, the batch's trainer, or `enrolment.view_any` |
| `POST` | `<id>/status/` | `enrolment.update_any` |
| `GET` | `<id>/progress/` | the owner, the batch's trainer, or `enrolment.view_any` |

Filters: `?status=`, `?batch=<uuid>`, `?course=<slug>`, `?search=`.

### Progress — `/api/v1/progress/`

| Method | Path | Access |
| --- | --- | --- |
| `POST` | `lessons/<id>/completion/` | the signed-in student, with a live enrolment |

### Calendar — `/api/v1/calendar/`

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `` | any signed-in user — only their own events |

Parameters: `?start=` and `?end=` (ISO dates). The window is capped at 120 days;
a wider request is clipped rather than refused.

### Dashboards — `/api/v1/dashboard/`

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `student/` | any signed-in user; returns `is_student: false` for others |
| `GET` | `trainer/` | any signed-in user; returns `is_trainer: false` for others |

---

## Batch and enrolment lifecycles

**Batch**

```
UPCOMING ──► ACTIVE ──► COMPLETED ──► ARCHIVED
    │           │                        ▲
    └───────────┴──► CANCELLED ──────────┘
```

Activating requires an assigned trainer. Cancelling cascades: every live
enrolment is cancelled with it. Completing completes the *active* enrolments
only — a suspended student did not finish the course, and recording that they
did would be a false statement in a record a certificate may be issued from.

**Enrolment**

```
PENDING ──► ACTIVE ⇄ SUSPENDED
   │           │          │
   │           ▼          │
   │       COMPLETED      │
   └───────► CANCELLED ◄──┘
```

`COMPLETED` and `CANCELLED` are terminal. Re-joining means a new enrolment, so
the old record — and the progress attached to it — stays exactly as it was.

---

## Course access

A student reaches non-preview lesson content, resources and video only when all
of the following hold:

1. Their account is active.
2. They hold an enrolment on the course whose status is `active` or `completed`.
3. That enrolment's batch is not cancelled.
4. Today falls inside the enrolment's access window (`start_date` …
   `access_end_date`), where one is set.

Checked live on every request, so suspending an enrolment or cancelling a batch
closes access immediately. Free-preview lessons stay readable to anyone who can
see the course, and staff — administrators and assigned course authors — are not
gated by enrolment at all.

`COURSE_CONTENT_REQUIRES_ENROLMENT` defaults to on. Turning it off is supported
for an open-catalogue or demo deployment.

---

## Schedule conflicts

A class is refused with `409 schedule_conflict` when it would overlap another,
where overlap means **all three** of:

* the same weekday;
* overlapping times, compared in each slot's own time zone — back-to-back
  classes do **not** clash;
* overlapping batch date ranges.

Both a trainer double-booking and a batch double-booking are refused, and the
error names the clashing class. Assigning a trainer to a batch runs the same
check up front, so the refusal arrives at assignment rather than on the next
timetable edit.

---

---

## Capabilities

Authorization is expressed as capabilities, not roles. `GET /api/v1/auth/me/`
returns the caller's list so the interface can decide what to offer; the server
re-checks each one on every request.

| Capability | Admin | Trainer | Student |
| --- | :---: | :---: | :---: |
| `profile.view_own`, `profile.update_own` | ✅ | ✅ | ✅ |
| `user.view_any`, `user.create`, `user.update_any` | ✅ | — | — |
| `user.set_active`, `user.change_role` | ✅ | — | — |
| `student.view_any`, `student.create`, `student.update_any` | ✅ | — | — |
| `student.set_fee_status` | ✅ | — | — |
| `trainer.view_any`, `trainer.create`, `trainer.update_any` | ✅ | — | — |
| `category.manage` | ✅ | — | — |
| `course.view_any`, `course.create`, `course.update_any` | ✅ | — | — |
| `course.publish_any`, `course.assign_authors` | ✅ | — | — |
| `batch.view_any`, `batch.create`, `batch.update_any` | ✅ | — | — |
| `batch.manage_schedule` | ✅ | — | — |
| `enrolment.view_any`, `enrolment.create`, `enrolment.update_any` | ✅ | — | — |

As with courses, a trainer holds **no** global batch capability. What they see
comes from being the assigned trainer on a batch: their own batches, those
batches' rosters and schedules, and nothing else. A trainer can view what they
teach but cannot edit it, assign themselves, or enrol anybody — all three are
institutional decisions.

A trainer holds **no** global course capability. Everything they may do comes
from a `CourseAssignment` row scoped to a single course:

| Assignment role | May do |
| --- | --- |
| `editor` | Edit the course and its content; submit for review |
| `owner` | The above, plus change the course's status |

---

## Field-level authorization

A user may only change fields their role permits, and an attempt to send any
other field is **rejected with 400** naming the field — never silently ignored.

| Actor | May change on their own record |
| --- | --- |
| Any user | `first_name`, `last_name`, `phone`, profile image |
| Student | address, date of birth, qualification, institution, graduation year, emergency and guardian contacts |
| Trainer | title, bio, skills, expertise, qualifications, years of experience, professional links |

Never self-editable by anyone: `role`, `is_active`, `is_staff`, `is_superuser`,
`email`, `is_email_verified`, `student_id`, `trainer_id`, `fee_status`, `notes`,
`is_accepting_assignments`, and every timestamp.

On a course, never settable through the editor: `code`, `status`,
`published_at`, `content_updated_at`, `created_by`, `updated_by`. On a module or
lesson: `position` and `status` — both have their own endpoints, so neither can
be changed as a side effect of an edit.

---

## Not yet implemented

Attendance, assignments, quizzes, exams, results, certificates, notifications,
reports and analytics have no endpoints. They arrive with the features that
implement them.

Progress exists as a foundation only: a lesson can be marked complete and a
course percentage is derived from it. Watch position, time on task, completion
rules and gated progression are later work — the `LessonProgress` row is shaped
to carry them without reshaping.
