# Phase 2 — completion checklist

**Status: complete.** Course authoring, the content tree, publishing, access
control, the student catalogue and the course player are built, tested and
verified against a running stack.

Last verified: 2026-08-31 · 324 backend tests (90% coverage) · 45 frontend unit tests · 23 end-to-end tests

| Symbol | Meaning |
| --- | --- |
| ✅ | Done and verified by a test, a scan or a live run |
| 🟡 | Foundation in place, full feature intentionally deferred |
| ⬜ | Deferred — out of scope for this phase |

---

## §1 Scope

| Item | Status |
| --- | --- |
| Course management | ✅ |
| Course categories | ✅ |
| Course metadata | ✅ |
| Modules | ✅ |
| Lessons | ✅ |
| Lesson resources | ✅ |
| Video content | ✅ metadata + provider abstraction |
| Documents | ✅ |
| External links | ✅ |
| Course publishing | ✅ |
| Draft states | ✅ draft / in review / published / archived |
| Content ordering | ✅ explicit, deferred-unique positions |
| Course-level permissions | ✅ |
| Trainer authoring permissions | ✅ per-course assignment |
| Admin course management | ✅ |
| Student course browsing | ✅ |
| Course detail page | ✅ |
| Content security | ✅ |
| API | ✅ 23 routes |
| Tests | ✅ |
| Staging seed data | ✅ |
| Batches / enrolment / attendance / assignments / quizzes / exams / certificates / payments | ⬜ not built, as instructed |

---

## §2–3 Course and categories

| Field / requirement | Status |
| --- | --- |
| ID (UUID) | ✅ |
| Public identifier (slug) | ✅ unique, reserved words refused |
| Course code | ✅ `GRS-C-00013`, sequence-allocated |
| Title, short description, full description | ✅ |
| Thumbnail | ✅ validated, re-encoded, served through an authenticated view |
| Category | ✅ `PROTECT` on delete |
| Difficulty | ✅ |
| Estimated duration | ✅ |
| Learning objectives, prerequisites | ✅ bounded arrays |
| Status: DRAFT / PUBLISHED / ARCHIVED | ✅ plus IN_REVIEW |
| Visibility | ✅ public / internal / private |
| Created by, updated by, timestamps | ✅ |
| Students cannot access unpublished content | ✅ tested by id and by slug |
| Category name, slug, description, status | ✅ |
| Duplicate slugs prevented | ✅ case-insensitive unique constraint |
| Filter courses by category | ✅ |
| Not over-engineered into a hierarchy | ✅ flat, with the reason recorded |

---

## §4–5 Modules and lessons

| Requirement | Status |
| --- | --- |
| Module title, description, ordering, visibility, status | ✅ |
| Deterministic course order | ✅ explicit `position`, unique per parent |
| Explicit ordering, not creation date | ✅ with the reasoning documented |
| Lesson title, slug, description | ✅ slug unique within its module |
| Content type and content | ✅ |
| Duration, ordering, status | ✅ |
| Preview setting | ✅ `is_preview` — readable without enrolment |
| Required/optional | ✅ |
| Text / Video / Document / External link | ✅ all four |
| Extensible to more types | ✅ one enum member + one requirements entry + one render branch |

---

## §6–7 Resources and video

| Requirement | Status |
| --- | --- |
| PDF, DOCX, PPTX, images | ✅ |
| ZIP where explicitly allowed | ✅ accepted, never unpacked |
| External links | ✅ https only |
| Safe upload controls | ✅ see §15 below |
| Not every file type allowed | ✅ allowlist + explicit deny-list |
| No large video in the app container | ✅ metadata only |
| S3-compatible storage modelled | 🟡 modelled; signed URL not implemented |
| Managed video service modelled | 🟡 modelled; provider call not implemented |
| External video URLs | ✅ playable today |
| Duration, provider, asset id, thumbnail, status | ✅ |
| Private video URLs not exposed | ✅ absent from every payload; issued by the playback endpoint after an access check |

---

## §8–9 Authoring and publishing

| Requirement | Status |
| --- | --- |
| Admin: create / edit course | ✅ |
| Admin: create category | ✅ |
| Admin: add and reorder modules | ✅ |
| Admin: add and reorder lessons | ✅ |
| Admin: add resources | ✅ |
| Admin: publish / unpublish / archive | ✅ |
| Trainer permissions configurable | ✅ per-course `CourseAssignment` with owner/editor roles |
| Trainers have no global editing rights by default | ✅ asserted in tests against the capability matrix |
| Draft → Review → Published → Archived | ✅ all four states reachable |
| Review simplifiable, architecture retained | ✅ editors submit, owners approve; making it mandatory is a table change |
| Published content stable | ✅ publish checklist blocks incomplete courses |
| No untracked changes to published content | ✅ audit records `published_course_edited` and previous values |

---

## §10–12 Access, course page and player

| Requirement | Status |
| --- | --- |
| Students do not get unrestricted API access | ✅ every listing is bounded by a visibility queryset |
| Backend verifies course visibility | ✅ |
| Backend verifies user status | ✅ inactive users refused by `IsActiveUser` |
| Enrolment rules prepared | ✅ `COURSE_CONTENT_REQUIRES_ENROLMENT` + `is_enrolled`, both covered by tests |
| Course page: title, description, instructor, category, difficulty, duration, objectives, modules, lessons, resources | ✅ |
| Students do not see restricted unpublished content | ✅ tested at course, module and lesson level |
| Player: current lesson | ✅ |
| Player: module navigation | ✅ |
| Player: lesson navigation | ✅ |
| Player: video integration | ✅ real player for external URLs, honest placeholder otherwise |
| Player: text content | ✅ rendered as text, never as HTML |
| Player: resource list | ✅ |
| Player: next/previous | ✅ |
| Completion tracking | ⬜ deliberately not built |

---

## §13–14 Search and permissions

| Requirement | Status |
| --- | --- |
| Search by title | ✅ |
| Search by course code | ✅ |
| Search by description | ✅ |
| Category filter | ✅ |
| Status filter for admin | ✅ (a student passing `?status=draft` gets an empty page) |
| Pagination | ✅ capped at 100 per page |
| No unbounded queries | ✅ every filter maps to an indexed column or an enumeration |
| Admin: full management | ✅ |
| Authorised trainer: assigned courses only | ✅ |
| Student: accessible courses only | ✅ |
| `course_id` never trusted as authorization | ✅ resolved inside an entitled queryset before any check runs |

---

## §15 Security review

| Threat | Status |
| --- | --- |
| Unauthorised unpublished content access | ✅ |
| IDOR | ✅ |
| Mass assignment | ✅ |
| Unsafe uploads | ✅ |
| Public file exposure | ✅ `MEDIA_ROOT` is not web-served |
| Malicious filenames | ✅ |
| Path traversal | ✅ |
| Excessive API data | ✅ |
| Unauthorised course modification | ✅ |
| Tested by direct API calls, not only the UI | ✅ 34 dedicated tests plus live curl verification |

### Defects found during Phase 2 and fixed

| # | Defect | Fix |
| --- | --- | --- |
| 1 | The resource download filename was built from the resource title with dots preserved, so a title like `report.sh` produced `report.sh.pdf` — a double extension in the `Content-Disposition` header | Dots are stripped from the base; only the server-derived extension remains |
| 2 | Eight course views produced `drf_spectacular` errors and were silently dropped from the OpenAPI document, so "document all implemented endpoints" was quietly untrue | Explicit `responses=` on every operation, plus `@extend_schema_field` on each `SerializerMethodField` |
| 3 | Anonymous enum names collided during schema generation (`RoleC3bEnum`, `Status68aEnum`), producing unstable client types | A shared `CONTENT_STATUS_CHOICES` constant and five `ENUM_NAME_OVERRIDES` entries |
| 4 | The lesson editor performed a side effect inside a `useState` lazy initialiser | Moved to `useEffect` with cancellation |

---

## §16–17 Database and API

| Requirement | Status |
| --- | --- |
| Course / Category / Module / Lesson / Resource relations | ✅ |
| Foreign-key constraints | ✅ `PROTECT` on category, `CASCADE` on the content tree |
| Ordering indexes | ✅ `(course, position)`, `(module, position)` |
| Unique constraints | ✅ course code, course slug (CI), lesson slug per module, one assignment per (course, user) |
| Slug constraints | ✅ format validator + reserved words + case-insensitive uniqueness |
| Database-level constraints | ✅ including a `CheckConstraint` that a file resource actually has a file, and **deferred** unique positions so reordering is possible |
| `/api/v1/courses/`, `/categories/`, `/modules/`, `/lessons/`, `/resources/` | ✅ |
| CRUD where authorized | ✅ |
| Filtering, search, pagination | ✅ |
| Validation | ✅ |
| Permission checks | ✅ |
| Consistent errors | ✅ shared envelope |
| All endpoints documented | ✅ `docs/api.md` + a clean OpenAPI schema |

---

## §18 Frontend

| Page | Status |
| --- | --- |
| Admin: course list | ✅ `/admin/courses` |
| Admin: course creation | ✅ dialog on the list page |
| Admin: course editor | ✅ `/admin/courses/[courseId]` |
| Admin: module editor | ✅ inline, with reordering |
| Admin: lesson editor | ✅ inline, content-type aware |
| Admin: resource uploader | ✅ files and links |
| Admin: categories | ✅ `/admin/categories` |
| Trainer: assigned course management | ✅ same pages, scoped by the API |
| Student: course catalog | ✅ `/courses` |
| Student: course details | ✅ `/courses/[slug]` |
| Student: course player | ✅ `/courses/[slug]/learn/[lessonId]` |
| Reusable components, no duplication | ✅ `CourseCard`, `LessonBody`, `useList`, `ListToolbar`, `Pagination`, `Field` all shared |

---

## §19–20 Audit and testing

| Audited action | Status |
| --- | --- |
| Course creation | ✅ |
| Course modification | ✅ with previous values when published |
| Publish / unpublish / archive | ✅ |
| Module creation / change / deletion | ✅ |
| Lesson creation / change / deletion | ✅ |
| Resource upload / deletion | ✅ |
| Permission-related changes (author assigned/removed) | ✅ |
| Content reordering | ✅ |

| Test area | Status |
| --- | --- |
| Course CRUD | ✅ |
| Module ordering | ✅ |
| Lesson ordering | ✅ |
| Publishing | ✅ |
| Archiving | ✅ |
| Trainer authorization | ✅ |
| Student restrictions | ✅ |
| Search | ✅ |
| Pagination | ✅ |
| File upload | ✅ |
| File access | ✅ |
| Unauthorized API access | ✅ |
| **Changing a course ID cannot expose another course** | ✅ by UUID and by slug, at course, module, lesson and resource level |

---

## §21–22 Staging data and acceptance

| Requirement | Status |
| --- | --- |
| 5 categories | ✅ |
| 5 courses | ✅ (4 published, 1 left in draft on purpose) |
| 3 modules per course | ✅ 15 total |
| 4 lessons per module | ✅ 60 total |
| Mixed content types | ✅ all four |
| Fake resources | ✅ generated PDFs and `.invalid` links |
| Fake video metadata | ✅ `videos.example.invalid` — reserved, unresolvable |
| Safe sample files | ✅ generated in memory, no binaries committed |

| Acceptance criterion | Status |
| --- | --- |
| Admin can create and manage courses | ✅ verified live |
| Authorized trainers can manage permitted courses | ✅ verified live (edit assigned → 200, unassigned → 403, create → 403) |
| Modules work | ✅ |
| Lessons work | ✅ |
| Ordering works | ✅ |
| Resources work | ✅ |
| Course publishing works | ✅ incl. checklist refusal |
| Students can browse published courses | ✅ 4 of 5 seeded courses |
| Unauthorized content access is blocked | ✅ draft course 404 by id and slug |
| Course pages work | ✅ |
| Course player foundation works | ✅ |
| Search works | ✅ |
| Pagination works | ✅ capped at 100 |
| API documentation updated | ✅ |
| Tests pass | ✅ 392 total |
| Security tests pass | ✅ |
| CI passes | 🟡 all checks pass locally; still never executed on GitHub (no remote) |
| Staging data available | ✅ |
| Staging deployment works | ✅ config unchanged; deploy checks clean for staging and production |

---

## Outstanding — requires a human

1. Decide the real video host (S3 + CloudFront, Cloudflare Stream, Vimeo…). The
   model and the playback route are ready; the signed-URL call is not written
   because it depends on that choice.
2. Confirm the resource file-type allowlist matches what trainers actually
   upload — particularly whether `.zip` should stay enabled.
3. Confirm whether review should become mandatory before publishing. It is
   optional today; making it compulsory is a change to one table.
4. Push to a remote and confirm the first CI run is green.
5. Provision object storage if course media is expected to outgrow a container
   volume.

---

## Next phase

Batches and enrolment: a `Batch` joining a course to a trainer with a schedule,
and an `Enrolment` joining a student to a batch. That is the point at which
`COURSE_CONTENT_REQUIRES_ENROLMENT` gets switched on and `is_enrolled` gets a
real body — both seams already exist and are covered by tests.
