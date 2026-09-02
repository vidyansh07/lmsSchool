# Course catalogue and learning content

How the Phase 2 domain is put together, and why.

---

## 1. The content tree

```
Category ──┐
           ▼
        Course ──── CourseAssignment ──── User   (who may author it)
           │
           ├── Module (position 0, 1, 2 …)
           │     │
           │     └── Lesson (position 0, 1, 2 …)
           │           ├── VideoAsset            (metadata only)
           │           └── LessonResource        (file or link)
           │
           └── status: draft → in_review → published → archived
```

All six models live in one app. They are a single aggregate — a lesson is
meaningless without its module, a module without its course — so splitting them
would buy circular imports and no boundary. The boundary that *does* exist is a
question, not a structure: "who may see or change this?", answered in
`apps/courses/access.py`.

---

## 2. Identifiers

| Model | Internal key | Human identifier | URL |
| --- | --- | --- | --- |
| Course | UUID | `GRS-C-00013` | `slug` |
| Module | UUID | — | — |
| Lesson | UUID | — | `slug`, unique within its module |

Course codes come from a PostgreSQL sequence, like student and trainer IDs:
allocation is atomic, so two concurrent creations can never collide. Slugs are
generated from the title and de-duplicated with a counter; reserved words
(`new`, `edit`, `admin`, `api`, …) are refused so `/courses/new` can never be
ambiguous between a route and a record.

The course detail endpoint accepts **either** the UUID or the slug, so
student-facing URLs read well without introducing a second identifier space.

---

## 3. Ordering

Position is explicit and starts at zero. Creation date is not an order: two
lessons added in the same second would tie, and reordering would mean rewriting
timestamps.

`(course, position)` and `(module, position)` are unique — and **deferred**.
That last part is what makes reordering possible at all: any reshuffle passes
through intermediate states where two rows briefly share a position, and a
deferred constraint permits that inside one transaction while still guaranteeing
the committed state is valid.

Reorder endpoints require the **complete** new order. A partial list would leave
the remainder ambiguous, so it is rejected rather than guessed at:

```http
POST /api/v1/courses/<id>/modules/reorder/
{ "ordered_ids": ["<id-c>", "<id-a>", "<id-b>"] }
```

---

## 4. Publishing

```
DRAFT ─────► IN_REVIEW ─────► PUBLISHED ─────► ARCHIVED
  ▲              │                │                │
  └──────────────┴────────────────┴────────────────┘
```

Transitions live in one table (`services.TRANSITIONS`), not scattered through
views, so an unreachable transition is a data-integrity error rather than
whichever view forgot to check.

**Review is real but not mandatory.** An author with publish rights may go
straight from draft to published; an assigned *editor* may only submit for
review, and an owner or administrator approves. Requiring every course to pass
through review later is a change to that table plus a flag — not a migration.

**Publishing has a checklist.** A course needs a title, a description, at least
one published module, and at least one published lesson inside it. A draft is
*allowed* to be incomplete — that is what draft means — so the check happens at
publish time, and `GET /courses/<id>/publish-checklist/` reports what is missing.

**Published content does not change silently.** Editing a published course is
permitted, but the audit entry records `published_course_edited: true` and the
previous values of every changed field. Structural changes underneath it stamp
`content_updated_at`, so a reviewer can see that a live course moved.

---

## 5. Access control

Three questions, deliberately separate, all answered in `access.py`:

### May I see this course exists?

`course.view_any`, **or** an authoring assignment, **or** the course is
published with public/internal visibility.

Listing applies this **as a queryset**, so paging, sorting and filtering cannot
reach past it — a student passing `?status=draft` gets an empty page, not a
draft. Detail endpoints resolve the record *inside* that queryset, which is why
a guessed identifier returns 404 rather than 403: the record is not merely
forbidden, it is not in the caller's world at all.

### May I read its content?

The above, **plus** one of: the lesson is a free preview, the caller may manage
the course, or content is not gated.

Filtering happens at every level. A draft lesson inside a published module
inside a published course is still hidden — filtering one level up and not the
next is exactly where this kind of gap appears.

### May I change it?

`course.update_any`, or an authoring assignment. Status changes additionally
need `course.publish_any` or the `owner` assignment role.

---

## 6. Trainer authoring rights

A trainer holds **no** global course capability. This is deliberate, and is what
§8 of the brief asks for: "do not give all trainers global course-editing rights
unless explicitly configured."

Everything a trainer may do comes from a `CourseAssignment` row scoped to one
course:

| Role | May |
| --- | --- |
| `editor` | Edit the course and its content; submit for review |
| `owner` | The above, plus change the course's status |

Removing the row removes the access on the next request — there is no cache and
no second source of truth. Granting trainers a global right, if that is ever
wanted, is one line in `ROLE_CAPABILITIES`.

---

## 7. The enrolment seam

Enrolment arrives in Phase 3. Until then there is nothing to check, and gating
content on an unanswerable question would mean nobody could read anything. So:

```python
COURSE_CONTENT_REQUIRES_ENROLMENT = False   # settings

def is_enrolled(user, course) -> bool:      # access.py
    return False                            # Phase 3 replaces this body
```

Every content check already routes through `is_enrolled`, and the gated
behaviour is covered by tests today — with the flag on, preview lessons stay
readable, non-preview bodies return 403, and the course outline stays visible
so a prospective student can still decide to enrol.

Phase 3 is one flag and one function body.

---

## 8. Video

The application container stores **no** video bytes. It is the wrong place for
large files and the wrong process to stream them from.

`VideoAsset` holds metadata: provider, asset identifier, duration, thumbnail,
status. Three providers are modelled:

| Provider | Playable today | Notes |
| --- | --- | --- |
| `external_url` | ✅ | An https URL the player loads directly |
| `s3` | ⬜ | Needs a presigned-URL call |
| `managed` | ⬜ | Needs a provider API call |

**The playable URL is issued, never published.** `source_url` appears in no list
or detail payload. A caller who is entitled to watch fetches it from
`GET /lessons/<id>/video/`, which re-checks access first. Adding S3 or a managed
service means implementing the signed-URL call in that one view; nothing else
changes.

---

## 9. Resources

Files are documents, not images, so they cannot be re-encoded the way profile
photos are. The defence is layered instead — see `docs/security.md` §5b for the
full table. The essentials:

* Extension allowlist, with an explicit deny-list checked first.
* Magic bytes validated **paired with the extension**, because `.docx`, `.pptx`,
  `.xlsx` and `.zip` are all ZIP containers.
* Storage name generated server-side; the uploader's filename is display text.
* Stored under `MEDIA_ROOT`, which is never web-served.
* Delivered by an authenticated view as an `attachment` with `nosniff` and a
  server-built filename.

Resources may also be external links, which must be https.

---

## 10. Adding a lesson content type

The whole change:

1. A member on `LessonContentType`.
2. An entry in `LESSON_CONTENT_REQUIREMENTS` naming the field it requires.
3. A branch in `frontend/components/lesson-content.tsx`.

Nothing else in the codebase branches on content type — summaries, navigation,
ordering and access rules are all type-agnostic — so a new type cannot be left
half-implemented.
