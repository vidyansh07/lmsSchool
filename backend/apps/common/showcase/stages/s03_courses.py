"""Stage 3 — the catalogue: categories, courses, modules, lessons, questions.

Creates, through ``apps.courses.services``, ``apps.questions.services`` and
``apps.academics.services``, always as ``ctx.superadmin`` (a course belongs to
the institution, not a centre), and idempotently:

* seven **categories** via ``create_category`` — Linux & DevOps, Cloud,
  Programming, Data Science, Cyber Security, Networking, and *Hardware &
  Repair* retired (``is_active=False``) so the catalogue filter has both
  states. Found by slug, then by name, because staging already has a
  ``programming`` and a ``cyber-security`` from the SITP import and a second
  row with the same name would be refused.
* eight **courses** via ``create_course`` — Grras's real offerings, each with
  a fee in rupees, a difficulty, a visibility, objectives and prerequisites;
  the code comes from ``next_course_code`` inside the service. Trainers become
  authors via ``assign_author`` (owner or editor), which is the only way a
  trainer sees a course on ``/admin/courses``. Per course, three **published
  modules** via ``create_module`` holding every content type via
  ``create_lesson``: text lessons with real course material, video lessons
  with an external-URL ``VideoAsset`` on a reserved ``.invalid`` domain,
  document lessons — created draft, given a generated PDF through
  ``create_file_resource`` (so the bytes go through the configured storage,
  S3 included) and only then published through ``update_lesson`` — and
  external links to the vendor's own documentation. One preview and one
  optional lesson per course; link resources via ``create_link_resource`` on
  the third module's text lesson. The DevOps course also carries a *draft*
  and an *archived* module for the authoring screens.
* the **status spread** via ``set_course_status``: five published, one draft
  (Ethical Hacking), one in review (Data Science), one archived (CCNA —
  published first, then archived, because the transition table allows no
  other route). A course found in any other state is walked to its target
  along ``TRANSITIONS``.
* the **imported SITP courses** — every course whose title starts with
  ``SITP ACE 2026`` or whose lower-cased title is a key of
  ``roster.COURSE_RENAMES`` — get one published module *Programme content*
  with three text lessons (a syllabus overview, a lab guide, an assessment
  guide, written for that track's subject) and are published, so the 1,057
  imported enrolments open a real course; the junk title is renamed through
  ``update_course``. Their existing draft *Syllabus* module is left as found.
  This is the one deliberate upgrade of rows this stage did not create. On a
  database with no import it is a no-op, and says so.
* a **course-level academic policy** on RHCSA via ``get_or_create_policy``
  + ``update_policy`` (80 % attendance, against the global 75 %).
* the **question bank** via ``create_question``: for every *published*
  showcase course twelve MCQs (four per difficulty), four true/false, three
  short-answer with an answer key, two long-answer and two multiple-answer,
  all with lower-case tags and negative marks on the hard MCQs — enough for
  stage 7 to publish a two-section exam (``check_readiness`` counts active
  questions of the course plus the shared bank per section) — plus ten
  shared questions (``course=None``) and one question retired through
  ``update_question(is_active=False)``.

Idempotent by slug (categories, courses), by ``(course, title)`` for modules,
``(module, slug)`` for lessons, ``(lesson, kind, title)`` for resources,
``(course, user)`` for authors and ``(course, text)`` for questions. Nothing
here draws from ``ctx.rng``: the catalogue is written out, so a ``--only
courses`` run and a full run are the same run.

Leaves in ``ctx``: ``courses`` keyed by slug — the showcase eight and every
imported one.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from decimal import Decimal
from functools import partial
from typing import Any

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.academics.models import AcademicPolicy
from apps.academics.models import PolicyScope as AcademicScope
from apps.academics.services import get_or_create_policy
from apps.academics.services import update_policy as update_academic_policy
from apps.accounts.models import User
from apps.courses.models import (
    Category,
    Course,
    CourseAssignment,
    Lesson,
    LessonContentType,
    LessonResource,
    Module,
    PublishStatus,
    ResourceKind,
    VideoProvider,
    VideoStatus,
)
from apps.courses.services import (
    TRANSITIONS,
    assign_author,
    create_category,
    create_course,
    create_file_resource,
    create_lesson,
    create_link_resource,
    create_module,
    set_course_status,
    update_course,
    update_lesson,
)
from apps.questions.models import Difficulty, Question, QuestionType
from apps.questions.services import create_question, update_question

from ..context import Context
from ..roster import COURSE_RENAMES
from .s03_courses_content import (
    CATEGORIES,
    COURSES,
    POLICY_COURSE,
    POLICY_RULES,
    QUESTIONS,
    RETIRED_QUESTION,
    SHARED_QUESTIONS,
    SITP_PREFIX,
    LessonSpec,
    sitp_lessons,
)

#: Where the video lessons "live". ``.invalid`` is reserved by RFC 2606 and can
#: never resolve, which is the point: the player renders, nothing is fetched.
VIDEO_HOST = "https://videos.example.invalid"

#: Marks by type and difficulty. Long answers are worth the most because a
#: person reads them; hard MCQs carry a quarter-mark penalty so the exam's
#: negative-marking switch has something to act on.
MARKS: dict[str, dict[str, Decimal]] = {
    QuestionType.MCQ: {"easy": Decimal("1"), "medium": Decimal("2"), "hard": Decimal("3")},
    QuestionType.MULTIPLE: {"easy": Decimal("2"), "medium": Decimal("2"), "hard": Decimal("3")},
    QuestionType.TRUE_FALSE: {"easy": Decimal("1"), "medium": Decimal("1"), "hard": Decimal("1")},
    QuestionType.SHORT_ANSWER: {"easy": Decimal("2"), "medium": Decimal("2"), "hard": Decimal("3")},
    QuestionType.LONG_ANSWER: {"easy": Decimal("5"), "medium": Decimal("5"), "hard": Decimal("5")},
}
NEGATIVE_ON_HARD_MCQ = Decimal("0.25")


def run(ctx: Context) -> None:
    if ctx.superadmin is None:
        raise RuntimeError("No superadmin yet: run the organisation stage first.")
    owner = ctx.superadmin

    categories: dict[str, Category] = {}
    _timed(ctx, "categories", lambda: categories.update(_ensure_categories(ctx, owner)))
    _timed(ctx, "courses", lambda: _ensure_courses(ctx, owner, categories))
    _timed(ctx, "imported courses", lambda: _ensure_imported_courses(ctx, owner))
    _timed(ctx, "course policy", lambda: _ensure_course_policy(ctx, owner))
    _timed(ctx, "question bank", lambda: _ensure_questions(ctx, owner))


def _timed(ctx: Context, what: str, step: Callable[[], Any]) -> None:
    started = time.perf_counter()
    step()
    ctx.out(f"courses/{what}: {time.perf_counter() - started:.1f}s")


def _ensure_quiet[T](ctx: Context, label: str, existing: T | None, create: Callable[[], T]) -> T:
    """``ctx.ensure`` without the log line, for the rows that come in dozens."""
    if existing is not None:
        ctx.found_existing(label)
        return existing
    row = create()
    ctx.created(label)
    return row


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


def _ensure_categories(ctx: Context, owner: User) -> dict[str, Category]:
    found: dict[str, Category] = {}
    for slug, name, description, position, active in CATEGORIES:
        category = (
            Category.objects.filter(slug__iexact=slug).first()
            or Category.objects.filter(name__iexact=name).first()
        )
        category = ctx.ensure(
            "category",
            f"category {name}",
            category,
            partial(
                create_category,
                actor=owner,
                name=name,
                slug=slug,
                description=description,
                position=position,
                is_active=active,
            ),
        )
        found[slug] = category
    return found


# ---------------------------------------------------------------------------
# Courses and their content
# ---------------------------------------------------------------------------


def _trainer_users(ctx: Context) -> dict[str, User]:
    """Roster trainers by local part, from whichever centre holds them."""
    return {
        profile.user.email.split("@", 1)[0]: profile.user
        for profiles in ctx.trainers.values()
        for profile in profiles
    }


def _ensure_courses(ctx: Context, owner: User, categories: dict[str, Category]) -> None:
    trainers = _trainer_users(ctx)
    if not trainers:
        ctx.out("course authors: skipped (no roster trainers yet; run the people stage)")

    for spec in COURSES:
        before = dict(ctx.counts)
        course = ctx.ensure(
            "course",
            f"course {spec.slug} '{spec.title}'",
            Course.objects.filter(slug__iexact=spec.slug).first(),
            partial(
                create_course,
                actor=owner,
                title=spec.title,
                slug=spec.slug,
                category=categories[spec.category],
                difficulty=spec.difficulty,
                visibility=spec.visibility,
                default_fee=spec.fee,
                estimated_duration_minutes=spec.minutes,
                short_description=spec.short,
                description=spec.description,
                learning_objectives=list(spec.objectives),
                prerequisites=list(spec.prerequisites),
            ),
        )

        for local_part, role in spec.authors:
            user = trainers.get(local_part)
            if user is None:
                continue
            _ensure_quiet(
                ctx,
                "course_author",
                CourseAssignment.objects.filter(course=course, user=user).first(),
                partial(assign_author, course=course, user=user, role=role, actor=owner),
            )

        for module_spec in spec.modules:
            module = _ensure_quiet(
                ctx,
                "module",
                Module.objects.filter(course=course, title=module_spec.title).first(),
                partial(
                    create_module,
                    course=course,
                    actor=owner,
                    title=module_spec.title,
                    description=module_spec.description,
                    status=module_spec.status,
                ),
            )
            for lesson_spec in module_spec.lessons:
                _ensure_lesson(ctx, owner, course, module, lesson_spec)

        _ensure_status(ctx, owner, course, spec.status)
        ctx.courses[course.slug] = course

        made = {k: v - before.get(k, 0) for k, v in ctx.counts.items() if v != before.get(k, 0)}
        if made:
            ctx.out(f"  {spec.slug}: created " + ", ".join(f"{n} {k}" for k, n in made.items()))


def _ensure_lesson(
    ctx: Context, owner: User, course: Course, module: Module, spec: LessonSpec
) -> Lesson:
    common: dict[str, Any] = {
        "title": spec.title,
        "slug": spec.slug,
        "description": spec.description,
        "content_type": spec.kind,
        "duration_minutes": spec.minutes,
        "is_preview": spec.preview,
        "is_required": not spec.optional,
    }

    def create() -> Lesson:
        if spec.kind == LessonContentType.TEXT:
            return create_lesson(
                module=module, actor=owner, status=spec.status, text_content=spec.body, **common
            )
        if spec.kind == LessonContentType.EXTERNAL_LINK:
            return create_lesson(
                module=module, actor=owner, status=spec.status, external_url=spec.url, **common
            )
        if spec.kind == LessonContentType.VIDEO:
            ctx.created("video_asset")
            return create_lesson(
                module=module,
                actor=owner,
                status=spec.status,
                video={
                    "provider": VideoProvider.EXTERNAL_URL,
                    "source_url": f"{VIDEO_HOST}/{course.slug}/{spec.slug}.m3u8",
                    "thumbnail_url": f"{VIDEO_HOST}/{course.slug}/{spec.slug}.jpg",
                    "duration_seconds": spec.minutes * 60,
                    "asset_identifier": f"showcase-{course.slug}-{spec.slug}",
                    "status": VideoStatus.READY,
                },
                **common,
            )
        # A document lesson cannot publish without its file, so it is born a
        # draft; the file and the status change follow below.
        return create_lesson(module=module, actor=owner, status=PublishStatus.DRAFT, **common)

    existing = Lesson.objects.filter(module=module, slug=spec.slug).first()
    if existing is not None and spec.kind == LessonContentType.VIDEO:
        # The asset was made with the lesson, so a found lesson is a found
        # asset; counted here so the finish table balances on a re-run.
        ctx.found_existing("video_asset")
    lesson = _ensure_quiet(ctx, "lesson", existing, create)

    if spec.kind == LessonContentType.DOCUMENT:
        _ensure_quiet(
            ctx,
            "lesson_resource",
            LessonResource.objects.filter(lesson=lesson, kind=ResourceKind.FILE).first(),
            lambda: create_file_resource(
                lesson=lesson,
                actor=owner,
                uploaded_file=_handout_pdf(spec.slug, spec.title, course.title, spec.body),
                title=f"{spec.title} (PDF)",
                description="Handout for this lesson. Generated for the showcase.",
            ),
        )
        if lesson.status != spec.status:
            update_lesson(lesson=lesson, actor=owner, status=spec.status)

    for title, url in spec.links:
        _ensure_quiet(
            ctx,
            "lesson_resource",
            LessonResource.objects.filter(
                lesson=lesson, kind=ResourceKind.LINK, title=title
            ).first(),
            partial(
                create_link_resource, lesson=lesson, actor=owner, external_url=url, title=title
            ),
        )
    return lesson


def _handout_pdf(slug: str, title: str, course_title: str, body: str) -> SimpleUploadedFile:
    """A small, real, single-page PDF: title, course, and the lesson's text.

    Built by hand the way ``seed_courses --with-files`` builds its sample —
    nothing binary is committed and nothing is copied from real material —
    but with a content stream and an xref table, so a PDF viewer opens it and
    a reviewer sees words rather than a blank page. Helvetica takes Latin-1
    only, so the dashes and quotes of the source text are plainified.
    """

    def plain(text: str) -> str:
        text = text.replace("—", "-").replace("–", "-").replace("’", "'")  # noqa: RUF001
        text = text.replace("“", '"').replace("”", '"').replace("×", "x")  # noqa: RUF001
        return text.encode("latin-1", "replace").decode("latin-1")

    def escape(text: str) -> str:
        return plain(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    ops = ["BT", "/F1 16 Tf", "56 780 Td", f"({escape(title)}) Tj"]
    ops += ["/F1 10 Tf", "0 -20 Td", f"({escape(course_title)} - Grras Solutions) Tj"]
    ops += ["/F1 11 Tf", "0 -30 Td"]
    lines: list[str] = []
    for paragraph in body.strip().splitlines():
        words, current = paragraph.split(), ""
        for word in words:
            if len(current) + len(word) + 1 > 88:
                lines.append(current)
                current = word
            else:
                current = f"{current} {word}".strip()
        lines.append(current)
    for line in lines[:40]:
        ops += [f"({escape(line)}) Tj", "0 -15 Td"]
    ops.append("ET")
    stream = "\n".join(ops).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + obj + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref_at,
    )
    return SimpleUploadedFile(f"{slug}.pdf", bytes(out), content_type="application/pdf")


def _status_path(current: str, target: str) -> list[str]:
    """The shortest walk through ``TRANSITIONS`` from one status to another.

    Publishing then archiving is the only way to an archived course, and a
    found course may be in any state a previous run or a person left it in;
    a breadth-first search says which transitions to apply, in order.
    """
    if current == target:
        return []
    queue: deque[list[str]] = deque([[current]])
    seen = {current}
    while queue:
        path = queue.popleft()
        for nxt in sorted(TRANSITIONS.get(path[-1], frozenset())):
            if nxt in seen:
                continue
            if nxt == target:
                return [*path[1:], nxt]
            seen.add(nxt)
            queue.append([*path, nxt])
    raise RuntimeError(f"No route from {current} to {target} in the transition table.")


def _ensure_status(ctx: Context, owner: User, course: Course, target: str) -> None:
    for step in _status_path(course.status, target):
        set_course_status(
            course=course,
            target=step,
            actor=owner,
            may_publish=True,
            note=ctx.note("Showcase catalogue."),
        )
        ctx.out(f"  {course.slug}: {step}")


# ---------------------------------------------------------------------------
# The imported SITP courses — the one upgrade of rows this stage did not make
# ---------------------------------------------------------------------------

IMPORTED_MODULE = "Programme content"


def _imported_courses() -> list[Course]:
    """The SITP tracks and the junk-titled import, by title.

    A renamed course no longer matches its old title, so the *new* titles are
    keys too: without that, the second run would skip the course it renamed
    on the first and the finish table would find three rows fewer than it
    made. Showcase slugs are excluded so a showcase course whose title
    happened to match could never be treated as imported.
    """
    showcase_slugs = {spec.slug for spec in COURSES}
    imported_titles = set(COURSE_RENAMES) | {new.lower() for new in COURSE_RENAMES.values()}
    return [
        course
        for course in Course.objects.order_by("code")
        if course.slug not in showcase_slugs
        and (course.title.startswith(SITP_PREFIX) or course.title.lower() in imported_titles)
    ]


def _ensure_imported_courses(ctx: Context, owner: User) -> None:
    courses = _imported_courses()
    if not courses:
        ctx.out("imported courses: none on this database (nothing to upgrade)")
        return

    for course in courses:
        wanted = COURSE_RENAMES.get(course.title.lower())
        if wanted and course.title != wanted:
            update_course(course=course, actor=owner, title=wanted)
            ctx.out(f"imported course {course.code}: renamed to '{wanted}'")
        ctx.found_existing("course")

        module = _ensure_quiet(
            ctx,
            "module",
            Module.objects.filter(course=course, title=IMPORTED_MODULE).first(),
            partial(
                create_module,
                course=course,
                actor=owner,
                title=IMPORTED_MODULE,
                description="What the programme covers, how the labs run and how it is assessed.",
                status=PublishStatus.PUBLISHED,
            ),
        )
        for spec in sitp_lessons(course.title):
            _ensure_lesson(ctx, owner, course, module, spec)

        _ensure_status(ctx, owner, course, PublishStatus.PUBLISHED)
        ctx.courses[course.slug] = course
    ctx.out(f"imported courses: {len(courses)} published with a '{IMPORTED_MODULE}' module")


# ---------------------------------------------------------------------------
# Course-level rules
# ---------------------------------------------------------------------------


def _ensure_course_policy(ctx: Context, owner: User) -> None:
    course = Course.objects.filter(slug=POLICY_COURSE).first()
    if course is None:
        raise RuntimeError(f"Course {POLICY_COURSE} missing; the courses step did not run.")
    existed = AcademicPolicy.objects.filter(scope=AcademicScope.COURSE, course=course).exists()
    policy = get_or_create_policy(course=course)
    unchanged = existed and all(getattr(policy, k) == v for k, v in POLICY_RULES.items())
    update_academic_policy(policy=policy, actor=owner, **POLICY_RULES)
    if unchanged:
        ctx.found_existing("academic_policy")
        ctx.out(f"course policy on {POLICY_COURSE}: found")
    else:
        ctx.created("academic_policy")
        ctx.out(f"course policy on {POLICY_COURSE}: created")


# ---------------------------------------------------------------------------
# The question bank
# ---------------------------------------------------------------------------


def _ensure_questions(ctx: Context, owner: User) -> None:
    published = [
        spec
        for spec in COURSES
        if spec.status == PublishStatus.PUBLISHED and spec.slug in QUESTIONS
    ]
    for spec in published:
        course = Course.objects.get(slug=spec.slug)
        existing = {q.text: q for q in Question.objects.filter(course=course)}
        made = 0
        for item in QUESTIONS[spec.slug]:
            _, created = _ensure_question(ctx, owner, course, existing, item)
            made += created
        ctx.out(
            f"questions for {spec.slug}: {made} created, {len(QUESTIONS[spec.slug]) - made} found"
        )

    existing = {q.text: q for q in Question.objects.filter(course__isnull=True)}
    made = sum(_ensure_question(ctx, owner, None, existing, item)[1] for item in SHARED_QUESTIONS)
    ctx.out(f"shared questions: {made} created, {len(SHARED_QUESTIONS) - made} found")

    # One retired question: written, then withdrawn, the way a trainer would
    # after the syllabus moved on. Retiring is a service call so it is audited.
    slug, item = RETIRED_QUESTION
    course = Course.objects.get(slug=slug)
    existing = {q.text: q for q in Question.objects.filter(course=course, text=item[2])}
    question, _ = _ensure_question(ctx, owner, course, existing, item)
    if question.is_active:
        update_question(question=question, actor=owner, is_active=False)
        ctx.out(f"retired question on {slug}: retired")
    else:
        ctx.out(f"retired question on {slug}: found retired")


def _ensure_question(
    ctx: Context,
    owner: User,
    course: Course | None,
    existing: dict[str, Question],
    item: tuple,
) -> tuple[Question, int]:
    """One question, found by its text within its course (or the shared bank)."""
    qtype, difficulty, text, answer, tags = item[:5]
    explanation = item[5] if len(item) > 5 else ""
    if text in existing:
        ctx.found_existing("question")
        return existing[text], 0

    fields: dict[str, Any] = {
        "question_type": qtype,
        "text": text,
        "difficulty": difficulty,
        "marks": MARKS[qtype][difficulty],
        "negative_marks": (
            NEGATIVE_ON_HARD_MCQ
            if qtype == QuestionType.MCQ and difficulty == Difficulty.HARD
            else Decimal("0")
        ),
        "tags": list(tags),
        "explanation": explanation,
    }
    options: list[dict[str, Any]] | None = None
    if qtype in (QuestionType.MCQ, QuestionType.MULTIPLE):
        # The correct options carry a leading asterisk in the source lists.
        options = [
            {"text": option.lstrip("*"), "is_correct": option.startswith("*")} for option in answer
        ]
    elif qtype == QuestionType.TRUE_FALSE:
        options = [
            {"text": "True", "is_correct": bool(answer)},
            {"text": "False", "is_correct": not answer},
        ]
    elif qtype == QuestionType.SHORT_ANSWER:
        fields["answer_key"] = list(answer)

    question = create_question(actor=owner, course=course, options=options, **fields)
    ctx.created("question")
    existing[text] = question
    return question, 1


__all__ = ["run"]
