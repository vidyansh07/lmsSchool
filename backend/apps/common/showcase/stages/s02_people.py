"""Stage 2 — the people: every roster account, its profile and its role.

Walks ``ctx.roster`` in order and, for every
:class:`~apps.common.showcase.roster.Person` whose email does not exist yet,
creates the account through the service for its role — always with
``password=ctx.password`` and ``send_invitation=False`` — then layers on the
few states the people screens need that an account alone does not give:

* **staff** (admins, managers, counsellors) through
  ``apps.accounts.services.create_user`` as the superadmin, with the branch
  named because the superadmin has no home centre. An admin is ``is_staff``,
  as ``seed_demo_data``'s is — set through ``update_user`` so the flag is
  audited like any other administrator's edit.
* **trainers** through ``apps.trainers.services.create_trainer`` as the
  centre's admin, with a profile that reads like a person: a title and skills
  from the roster, a bio, expertise, qualifications, years and links from
  :data:`TRAINER_PROFILES`. The trainer the roster flags as fully booked is
  created with ``is_accepting_assignments=False``; the one it flags as having
  left is created **active** — stage 4 deactivates him *after* he has taught
  something, so that the inactive-trainer filter shows a row with history.
* **students** through ``apps.students.services.create_student`` as the
  centre's admin, with a unique phone from the roster (duplicate detection
  refuses a repeated one) and a profile drawn from ``ctx.rng``: a Jaipur or
  Pune address, a qualification, a college in the SITP style or an employer
  with a designation, a graduation year, and guardian and emergency contacts.
  A fifth of the profiles are left partly filled so the completion meter has
  a spread. The roster's inactive student is likewise created active for
  stage 4 to deactivate once enrolled.
* every account is **pre-verified** (``is_email_verified``) the way stage 1
  verifies the owner, except the two the roster flags ``unverified`` — one
  staff row, one student — which stay as ``create_user`` left them.
* two **custom roles** through ``apps.authorization.services.create_role``:
  *Placement coordinator* (counsellor kind, a narrowed set with one grant
  scoped below the kind's floor and one grant **locked** through
  ``set_grant_lock``) assigned to ``placement@`` through
  ``update_user(custom_role=…)``, and *Guest lecturer* (trainer kind) left
  **disabled** with nobody on it, so the roles matrix has both states. Roles
  are looked up through ``Role.all_objects`` — the recycle bin included —
  because a later stage soft-deletes the disabled one and ``Role.objects``
  would then hide it and let ``create_role`` make a twin on every re-run. A
  binned role counts as found and is never restored: the bin is that stage's
  state, not this one's.
* one **scope grant** on ``counsellor2@`` through ``grant_scope`` — on the
  oldest non-archived course the database already has (the SITP import's, on
  staging). Any course grant already on him counts as found, whichever course
  it names, so stage 3's newer courses never move the choice. On a database
  with no course yet it is skipped and said so: stage 2 runs before stage 3
  creates any, so on a database that starts empty the *second* full run is
  the one that makes this grant (one row; the finish table's "second run
  creates nothing" holds from the third run on). Staging always has the
  SITP courses, so there it lands on the first run. The clean cure is for
  stage 3 to grant one of its own courses at its end; until then this is
  the one known exception, and it is bounded to a single row.
* a **teaching profile** for ``manager@`` through ``ensure_teaching_profile``,
  so the batch wizard's trainer picker shows a non-trainer role.
* **notification preferences** for the headline trainer and student through
  ``update_preferences`` — only when no row exists yet: a row that is there
  is found and left as it says, so a choice somebody made on the settings
  screen between runs survives the re-run and nothing is re-saved. And
  ``whatsapp_opt_in`` on ten students through ``update_user`` — the WhatsApp
  channel refuses anyone without it.
* **referrals**: a second pass setting ``referred_by`` on twelve students
  through ``update_student_profile``, three of them referred by the headline
  student so his record shows a referrals count.
* one **denied** audit row: the MAIN counsellor attempts to create a manager,
  ``create_user`` refuses (``can_grant_role``: a counsellor holds less than a
  manager), and the refusal is recorded through the audit service.

Idempotent by email, slug, tag and natural key; on a re-run every account is
"found", gets ``ctx.ensure_password``, and the slots are refilled exactly as
:func:`~apps.common.showcase.context.hydrate` fills them, so a full run and a
``--only people`` run agree. Never touches ``@demo.grras.invalid`` or SITP
accounts: nothing here looks up anyone but the roster.

Leaves in ``ctx``: ``users``, ``admins``, ``managers``, ``counsellors``,
``trainers``, ``students`` (all keyed as the context documents) and
``roles["placement-coordinator"]``, ``roles["guest-lecturer"]``.

Why the random draws happen before any database work
-----------------------------------------------------
``ctx.rng`` is reseeded per stage so a ``--only`` run draws what the full run
drew — but only if the *number* of draws does not depend on what the database
already holds. So :func:`_plan` draws every student's profile, the WhatsApp
set and the referral pairs up front, for found and created accounts alike,
and the database walk afterwards draws nothing.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from django.utils import timezone

from apps.accounts.models import User, UserRole
from apps.accounts.services import create_user, update_user
from apps.audit.models import AuditLog
from apps.audit.services import AuditAction, AuditResult, record
from apps.authorization.models import Role, RoleStatus, ScopeGrant
from apps.authorization.services import create_role, grant_scope, set_grant_lock, update_role
from apps.common.exceptions import ApplicationError
from apps.courses.models import PublishStatus
from apps.notifications.models import NotificationPreference
from apps.notifications.services import update_preferences
from apps.students.models import InstitutionKind, Qualification, StudentProfile
from apps.students.services import create_student, update_student_profile
from apps.trainers.models import TrainerProfile
from apps.trainers.services import create_trainer, ensure_teaching_profile

from ..context import Context
from ..roster import FIRST_NAMES, MAIN, PUNE, Person

# ---------------------------------------------------------------------------
# What the roster does not say: the colour on each person
# ---------------------------------------------------------------------------

#: The narrative half of each trainer's profile, keyed by local part. Title
#: and skills come from the roster; this is what makes the directory read
#: like nine people rather than nine rows.
TRAINER_PROFILES: dict[str, dict[str, Any]] = {
    "trainer": {
        "years_of_experience": 14,
        "qualifications": "RHCA, RHCE, CKA, AWS Certified DevOps Engineer - Professional",
        "expertise": (
            "Red Hat system administration from RHCSA through RHCA, container platforms "
            "(Docker, Podman, Kubernetes, OpenShift) and configuration management with "
            "Ansible. Designs the Linux and DevOps tracks and mentors the other trainers "
            "on lab design."
        ),
        "bio": (
            "Vikram has spent fourteen years on Linux — first running production for a "
            "Jaipur ISP, then as a Red Hat certified instructor. He has taught RHCSA to "
            "over two thousand students and still opens every batch with the same line: "
            "read the man page before you read the blog post."
        ),
        "professional_links": {
            "linkedin": "https://www.linkedin.com/in/vikram-shekhawat-rhca",
            "github": "https://github.com/vshekhawat",
        },
    },
    "neha.saxena": {
        "years_of_experience": 8,
        "qualifications": "M.Tech (CSE), MNIT Jaipur; PCAP - Certified Associate in Python",
        "expertise": (
            "Python from the basics to production Django: ORM design, REST APIs with DRF, "
            "PostgreSQL, testing and deployment. Runs the Python Full Stack track and the "
            "capstone project reviews."
        ),
        "bio": (
            "Neha built billing systems in Django for a Gurugram fintech for five years "
            "before moving back to Jaipur to teach. Her batches ship a working project "
            "every module, and she grades the tests before the commit messages."
        ),
        "professional_links": {
            "linkedin": "https://www.linkedin.com/in/neha-saxena-python",
            "github": "https://github.com/nehasaxena-dev",
        },
    },
    "rohit.kumawat": {
        "years_of_experience": 9,
        "qualifications": (
            "AWS Solutions Architect - Professional, HashiCorp Terraform Associate, CCNA"
        ),
        "expertise": (
            "AWS architecture and cost design, infrastructure as code with Terraform, "
            "VPC networking and Linux hardening. Leads the AWS Solutions Architect track."
        ),
        "bio": (
            "Rohit ran cloud migrations for a Pune consultancy before joining Grras. He "
            "teaches AWS the way he was billed for it: every lab ends with the cost "
            "explorer open and a discussion of what would have been cheaper."
        ),
        "professional_links": {"linkedin": "https://www.linkedin.com/in/rohit-kumawat-aws"},
    },
    "priya.malhotra": {
        "years_of_experience": 7,
        "qualifications": (
            "M.Sc. Statistics, University of Rajasthan; TensorFlow Developer Certificate"
        ),
        "expertise": (
            "Applied machine learning with Python — pandas, scikit-learn, model evaluation "
            "and SQL for analysis. Runs the Data Science and Data Analytics tracks and the "
            "Kaggle study group."
        ),
        "bio": (
            "Priya was a data analyst at an insurance firm in Jaipur and taught statistics "
            "on the side until the side became the job. She insists on a clean notebook "
            "and a written interpretation under every chart."
        ),
        "professional_links": {
            "linkedin": "https://www.linkedin.com/in/priya-malhotra-ds",
            "github": "https://github.com/priyamalhotra-ml",
            "website": "https://priyamalhotra.dev",
        },
    },
    "sameer.bhatt": {
        "years_of_experience": 11,
        "qualifications": "CEH, CompTIA Security+, OSCP",
        "expertise": (
            "Ethical hacking, network defence, SIEM operations (Splunk, Wazuh) and Linux "
            "hardening. Runs the Cyber Security and SOC tracks and the institute's CTF."
        ),
        "bio": (
            "Sameer spent a decade in a bank's security operations centre before teaching. "
            "He is booked solid through the current cycle — three batches and the SOC "
            "corporate programme — which is why he is not accepting new assignments."
        ),
        "professional_links": {"linkedin": "https://www.linkedin.com/in/sameer-bhatt-sec"},
    },
    "deepak.purohit": {
        "years_of_experience": 12,
        "qualifications": "CCNP Enterprise, CCNA",
        "expertise": (
            "Routing and switching, network design and troubleshooting labs on real gear."
        ),
        "bio": (
            "Deepak taught the networking track for six years and built the institute's "
            "Cisco lab. He has since moved to a network engineering role in Bengaluru."
        ),
        "professional_links": {},
    },
    "ankit.kulkarni": {
        "years_of_experience": 6,
        "qualifications": "B.E. Computer Engineering, PICT Pune; MongoDB Certified Developer",
        "expertise": (
            "The MERN stack end to end: React with hooks, Node and Express APIs, MongoDB "
            "schema design, deployment to cloud. Runs the Full Stack track at Pune."
        ),
        "bio": (
            "Ankit was a front-end lead at a Hinjewadi product startup and still ships a "
            "side project every quarter. His batches build the same app three times — "
            "badly, then properly, then fast."
        ),
        "professional_links": {
            "github": "https://github.com/ankitkulkarni-mern",
            "website": "https://ankitkulkarni.in",
        },
    },
    "shivani.nair": {
        "years_of_experience": 8,
        "qualifications": (
            "Microsoft Certified: Azure Solutions Architect Expert; AZ-400 DevOps Engineer"
        ),
        "expertise": (
            "Azure infrastructure and DevOps pipelines, PowerShell automation and "
            "Microsoft certification preparation (AZ-104, AZ-204, AZ-400)."
        ),
        "bio": (
            "Shivani ran Azure landing zones for a Pune IT services firm and now teaches "
            "the Microsoft cloud tracks. She prepares every batch for the exam and for "
            "the on-call rota that follows it."
        ),
        "professional_links": {"linkedin": "https://www.linkedin.com/in/shivani-nair-azure"},
    },
    "tushar.patel": {
        "years_of_experience": 5,
        "qualifications": "Microsoft Certified: Power BI Data Analyst Associate (PL-300)",
        "expertise": (
            "Power BI modelling and DAX, SQL for reporting, advanced Excel. Runs the Data "
            "Analytics track at Pune and the PL-300 preparation batches."
        ),
        "bio": (
            "Tushar built management dashboards for a logistics company before teaching. "
            "He starts every batch with a badly made report and spends the term fixing it."
        ),
        "professional_links": {"linkedin": "https://www.linkedin.com/in/tushar-patel-powerbi"},
    },
}

#: What the placement coordinator holds: the student- and activity-facing
#: subset of a counsellor's set, with attendance narrowed to *assigned* — a
#: coordinator sees attendance only for the batches they have been granted,
#: which is the one grant on the matrix scoped below the kind's floor.
PLACEMENT_COORDINATOR: dict[str, Any] = {
    "slug": "placement-coordinator",
    "name": "Placement coordinator",
    "kind": UserRole.COUNSELLOR,
    "description": (
        "Runs mock interviews, placement calls and resume reviews; sees students, "
        "batches and enrolments, but not fees, trainers or academic delivery."
    ),
    "permissions": [
        {"code": "student.view_any"},
        {"code": "student.create"},
        {"code": "student.update_any"},
        {"code": "batch.view_any"},
        {"code": "enrolment.view_any"},
        {"code": "attendance.view_any", "scope": "assigned"},
        {"code": "activity.view_any"},
        {"code": "activity.create"},
        {"code": "activity.complete"},
        {"code": "communication.send"},
        {"code": "communication.view_any"},
        {"code": "report.view_any"},
    ],
}

#: Built and switched off: the matrix needs a disabled role, and the role
#: builder needs one with nobody on it that can be deleted in a walkthrough.
GUEST_LECTURER: dict[str, Any] = {
    "slug": "guest-lecturer",
    "name": "Guest lecturer",
    "kind": UserRole.TRAINER,
    "description": (
        "A visiting trainer: sees the batches and courses they are given, nothing more."
    ),
    "permissions": [
        {"code": "batch.view_any", "scope": "assigned"},
        {"code": "course.view_any", "scope": "assigned"},
    ],
}

#: Where the students live, per centre: (area, postal code) pairs a local
#: would recognise, and the city and state the address form wants.
AREAS: dict[str, tuple[str, str, list[tuple[str, str]]]] = {
    MAIN: (
        "Jaipur",
        "Rajasthan",
        [
            ("Malviya Nagar", "302017"),
            ("Vaishali Nagar", "302021"),
            ("Mansarovar", "302020"),
            ("Jhotwara", "302012"),
            ("Pratap Nagar", "302033"),
            ("Tonk Road", "302018"),
            ("Sanganer", "302029"),
            ("C-Scheme", "302001"),
            ("Jagatpura", "302025"),
            ("Vidhyadhar Nagar", "302039"),
        ],
    ),
    PUNE: (
        "Pune",
        "Maharashtra",
        [
            ("Kothrud", "411038"),
            ("Hinjewadi", "411057"),
            ("Wakad", "411057"),
            ("Baner", "411045"),
            ("Hadapsar", "411028"),
            ("Viman Nagar", "411014"),
            ("Aundh", "411007"),
            ("Kharadi", "411014"),
            ("Pimple Saudagar", "411027"),
            ("Katraj", "411046"),
        ],
    ),
}

#: SITP-style college names — the ones the workbook import brings in read
#: like these — and the employers a working professional names instead.
COLLEGES: dict[str, list[str]] = {
    MAIN: [
        "Poornima College of Engineering, Jaipur",
        "JECRC University, Jaipur",
        "Swami Keshvanand Institute of Technology, Jaipur",
        "Arya College of Engineering & IT, Jaipur",
        "Malaviya National Institute of Technology, Jaipur",
        "Vivekananda Global University, Jaipur",
        "Rajasthan Technical University, Kota",
        "Global Institute of Technology, Jaipur",
        "Kautilya Institute of Technology, Jaipur",
        "St. Wilfred's College, Jaipur",
    ],
    PUNE: [
        "MIT World Peace University, Pune",
        "Pune Institute of Computer Technology",
        "Sinhgad College of Engineering, Pune",
        "Vishwakarma Institute of Technology, Pune",
        "D. Y. Patil College of Engineering, Akurdi",
        "Symbiosis Institute of Technology, Pune",
        "Modern College of Engineering, Pune",
        "Bharati Vidyapeeth College of Engineering, Pune",
    ],
}
EMPLOYERS: dict[str, list[str]] = {
    MAIN: [
        "Metacube Software",
        "Celebal Technologies",
        "Girnar Software (CarDekho)",
        "Infosys BPM, Jaipur",
        "Genpact, Jaipur",
        "Appirio (Wipro)",
        "Habilelabs",
        "Dotsquares",
    ],
    PUNE: [
        "Infosys, Hinjewadi",
        "Tata Consultancy Services, Sahyadri Park",
        "Persistent Systems",
        "Wipro, Hinjewadi",
        "Tech Mahindra, Pune",
        "Capgemini, Talawade",
        "Cognizant, Kharadi",
        "Bajaj Finserv",
    ],
}
JOB_TITLES = [
    "Software Engineer",
    "Associate Software Engineer",
    "Technical Support Engineer",
    "System Administrator",
    "Data Analyst",
    "QA Engineer",
    "Network Engineer",
    "Process Associate",
    "Junior Developer",
    "IT Executive",
]
#: (qualification, weight). Mostly graduates, as an IT institute's intake is.
QUALIFICATIONS: list[tuple[str, int]] = [
    (Qualification.BACHELORS, 55),
    (Qualification.MASTERS, 15),
    (Qualification.DIPLOMA, 12),
    (Qualification.HIGHER_SECONDARY, 15),
    (Qualification.OTHER, 3),
]
GUARDIAN_RELATIONS = ["Father", "Mother"]
OTHER_RELATIONS = ["Spouse", "Brother", "Sister", "Friend"]

WHATSAPP_OPT_INS = 10
REFERRALS = 12
#: How many of the referrals the headline student gets credit for.
HEADLINE_REFERRALS = 3
#: The roster pins its special students to positions 3, 7 and 11 of MAIN's
#: list; referrals are drawn from after them so those rows stay plain.
FIRST_PLAIN_MAIN_STUDENT = 13
#: The Placement coordinator grant frozen in the matrix (states-needed: "a
#: locked permission"). A superadmin-only lock; the role holds the code.
LOCKED_CODE = "student.view_any"
#: The email the counsellor tries, and fails, to create a manager under.
DENIED_EMAIL = "placement.head@grras.com"
DENIED_TAG = "denied/create-manager"

# ---------------------------------------------------------------------------


@dataclass
class Plan:
    """Every random choice this stage makes, drawn before it touches the database."""

    #: Student local part → ``profile_fields`` for ``create_student``.
    student_fields: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: Student local parts who said yes to WhatsApp.
    whatsapp: list[str] = field(default_factory=list)
    #: (referred local part, referrer local part).
    referrals: list[tuple[str, str]] = field(default_factory=list)


def run(ctx: Context) -> None:
    if ctx.superadmin is None:
        raise RuntimeError("No superadmin yet: run the organisation stage first.")
    plan = _plan(ctx)

    _timed(ctx, "accounts", lambda: _ensure_accounts(ctx, plan))
    _timed(ctx, "roles", lambda: _ensure_roles(ctx))
    _timed(ctx, "scope grant", lambda: _ensure_scope_grant(ctx))
    _timed(ctx, "teaching manager", lambda: _ensure_teaching_manager(ctx))
    _timed(ctx, "preferences", lambda: _ensure_preferences(ctx, plan))
    _timed(ctx, "referrals", lambda: _ensure_referrals(ctx, plan))
    _timed(ctx, "denied audit", lambda: _ensure_denied_audit(ctx))


def _timed(ctx: Context, what: str, step: Callable[[], None]) -> None:
    started = time.perf_counter()
    step()
    ctx.out(f"people/{what}: {time.perf_counter() - started:.1f}s")


# ---------------------------------------------------------------------------
# The plan: every draw from ctx.rng, in one place, before any lookup
# ---------------------------------------------------------------------------


def _plan(ctx: Context) -> Plan:
    plan = Plan()
    students = [p for p in ctx.roster if p.role == UserRole.STUDENT]
    for person in students:
        plan.student_fields[person.local_part] = _student_fields(ctx, person)

    # The headline student stays out of the opt-in draw: his screens are the
    # walkthrough's, and a consent flag that appeared by lot is a distraction.
    others = [p.local_part for p in students if p.local_part != "student"]
    plan.whatsapp = sorted(ctx.rng.sample(others, WHATSAPP_OPT_INS))

    # Referrals: twelve MAIN students past the pinned positions, the first
    # three referred by the headline student, the rest by other MAIN students
    # from the same plain stretch who were not themselves referred. Same
    # centre only: a MAIN counsellor's Student 360 names the referrer, and a
    # Pune student is a name they cannot open. The pinned rows stay out of
    # the referrer pool too: stage 4 deactivates the inactive one, and a
    # Student 360 naming a deactivated (or never-enrolled, or unverified)
    # referrer reads as a data error rather than a story.
    main_students = [p.local_part for p in students if p.branch_code == MAIN]
    plain = main_students[FIRST_PLAIN_MAIN_STUDENT:]
    referred = ctx.rng.sample(plain, REFERRALS)
    pool = [lp for lp in plain if lp not in referred]
    for index, local_part in enumerate(referred):
        referrer = "student" if index < HEADLINE_REFERRALS else ctx.rng.choice(pool)
        plan.referrals.append((local_part, referrer))
    return plan


def _phone(ctx: Context) -> str:
    """An Indian mobile number that passes ``PHONE_RE``; a contact's, so it
    need not be unique the way a student's own must be."""
    return f"+91{ctx.rng.randint(6, 9)}{ctx.rng.randint(0, 10**9 - 1):09d}"


def _student_fields(ctx: Context, person: Person) -> dict[str, Any]:
    """One student's profile, as a counsellor would have typed it in.

    Drawn in a fixed order so the sequence is the same on every run. A
    college student is 19-23 with a guardian as the emergency contact; a
    working professional is 23-32, names an employer and a designation, and
    lists a spouse or sibling instead. Headline student excepted, a fifth of
    the profiles are left short of complete.
    """
    rng = ctx.rng
    code = person.branch_code or MAIN
    city, state, areas = AREAS[code]
    area, postal = rng.choice(areas)
    house = f"{rng.choice('ABCDEFGH')}-{rng.randint(1, 240)}"
    is_working = rng.random() < 0.35
    qualification = rng.choices([q for q, _ in QUALIFICATIONS], [w for _, w in QUALIFICATIONS])[0]
    age = rng.randint(23, 32) if is_working else rng.randint(19, 23)
    # A birthday somewhere in the year before today, `age` years back. The
    # day is pinned to 1-28 *before* the year is moved, so an anchor on the
    # 29th of February cannot land in a year that lacks it.
    anchor = ctx.today - timedelta(days=30 * rng.randint(1, 12))
    date_of_birth = _years_before(anchor.replace(day=rng.randint(1, 28)), age)
    guardian_first = rng.choice(FIRST_NAMES)
    guardian_relation = rng.choice(GUARDIAN_RELATIONS)
    guardian_phone = _phone(ctx)
    other_first = rng.choice(FIRST_NAMES)
    other_relation = rng.choice(OTHER_RELATIONS)
    other_phone = _phone(ctx)
    college = rng.choice(COLLEGES[code])
    employer = rng.choice(EMPLOYERS[code])
    job_title = rng.choice(JOB_TITLES)
    graduation_year = (
        ctx.today.year - rng.randint(2, 9) if is_working else ctx.today.year + rng.randint(0, 2)
    )
    incomplete = rng.random() < 0.2 and person.local_part != "student"
    drop_birthday = rng.random() < 0.5

    fields: dict[str, Any] = {
        "date_of_birth": date_of_birth,
        "address_line1": f"{house}, {area}",
        "city": city,
        "state": state,
        "country": "India",
        "postal_code": postal,
        "qualification": qualification,
        "graduation_year": graduation_year,
        "guardian_name": f"{guardian_first} {person.last_name}",
        "guardian_phone": guardian_phone,
    }
    if is_working:
        fields.update(
            institution=employer,
            institution_kind=InstitutionKind.EMPLOYER,
            job_title=job_title,
            emergency_contact_name=f"{other_first} {person.last_name}",
            emergency_contact_phone=other_phone,
            emergency_contact_relationship=other_relation,
        )
    else:
        fields.update(
            institution=college,
            institution_kind=InstitutionKind.COLLEGE,
            emergency_contact_name=fields["guardian_name"],
            emergency_contact_phone=guardian_phone,
            emergency_contact_relationship=guardian_relation,
        )
    if incomplete:
        # What a hurried registration leaves out: the paperwork, not the phone.
        for key in ("qualification", "institution", "institution_kind", "graduation_year"):
            fields.pop(key, None)
        if drop_birthday:
            fields.pop("date_of_birth")
    return fields


def _years_before(day: date, years: int) -> date:
    return day.replace(year=day.year - years)


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


def _ensure_accounts(ctx: Context, plan: Plan) -> None:
    """Walk the roster in order, find or create, and refill the slots.

    The slots are rebuilt from scratch rather than appended to: under
    ``--only`` :func:`~apps.common.showcase.context.hydrate` has already
    filled them, and appending would list every trainer twice. Rebuilding in
    roster order gives exactly what hydrate gives — first admin, manager and
    counsellor per centre, headline trainer and student first in their lists.
    """
    emails = [p.email for p in ctx.roster]
    users = {u.email: u for u in User.objects.filter(email__in=emails).select_related("branch")}
    trainer_profiles = {
        p.user_id: p
        for p in TrainerProfile.objects.filter(user__in=users.values()).select_related(
            "user", "branch"
        )
    }
    student_profiles = {
        p.user_id: p
        for p in StudentProfile.objects.filter(user__in=users.values()).select_related(
            "user", "branch"
        )
    }

    ctx.admins, ctx.managers, ctx.counsellors = {}, {}, {}
    ctx.trainers, ctx.students = {}, {}

    for person in ctx.roster:
        code = person.branch_code or MAIN
        if person.role == UserRole.SUPERADMIN:
            # Stage 1's. Only filed, never touched here.
            ctx.users[person.local_part] = ctx.superadmin
            continue

        user = users.get(person.email)
        if person.role == UserRole.TRAINER:
            profile = trainer_profiles.get(user.pk) if user is not None else None
            if user is not None and profile is None:
                raise RuntimeError(f"{person.email} exists without a trainer profile.")
            profile = ctx.ensure(
                "trainer",
                f"trainer {person.email}",
                profile,
                lambda person=person: _create_trainer(ctx, person),
            )
            user = profile.user
            ctx.trainers.setdefault(code, []).append(profile)
        elif person.role == UserRole.STUDENT:
            profile = student_profiles.get(user.pk) if user is not None else None
            if user is not None and profile is None:
                raise RuntimeError(f"{person.email} exists without a student profile.")
            profile = ctx.ensure(
                "student",
                f"student {person.email}",
                profile,
                lambda person=person: _create_student(
                    ctx, person, plan.student_fields[person.local_part]
                ),
            )
            user = profile.user
            ctx.students.setdefault(code, []).append(profile)
        else:
            user = ctx.ensure(
                "user",
                f"{person.role} {person.email}",
                user,
                lambda person=person: _create_staff(ctx, person),
            )
            if person.role == UserRole.ADMIN:
                ctx.admins.setdefault(code, user)
            elif person.role == UserRole.MANAGER:
                ctx.managers.setdefault(code, user)
            elif person.role == UserRole.COUNSELLOR:
                ctx.counsellors.setdefault(code, user)

        ctx.users[person.local_part] = user
        if person.email in users:
            ctx.ensure_password(user)
        _ensure_verified(user, person)


def _create_staff(ctx: Context, person: Person) -> User:
    user = create_user(
        email=person.email,
        password=ctx.password,
        first_name=person.first_name,
        last_name=person.last_name,
        role=person.role,
        phone=person.flags.get("phone", ""),
        actor=ctx.superadmin,
        branch=ctx.branch(person.branch_code),
        send_invitation=False,
    )
    if person.role == UserRole.ADMIN:
        # The Django admin is the one door `create_user` does not open; an
        # administrator gets it, as stage 1 gives it to the owner — through
        # `update_user`, which validates the row and writes the USER_UPDATED
        # audit entry a raw save would skip.
        user = update_user(user=user, actor=ctx.superadmin, is_staff=True)
    return user


def _create_trainer(ctx: Context, person: Person) -> TrainerProfile:
    flags = person.flags
    fields: dict[str, Any] = {
        "professional_title": flags.get("professional_title", ""),
        "skills": list(flags.get("skills", [])),
        **TRAINER_PROFILES.get(person.local_part, {}),
    }
    if flags.get("is_accepting_assignments") is False:
        fields["is_accepting_assignments"] = False
    return create_trainer(
        email=person.email,
        first_name=person.first_name,
        last_name=person.last_name,
        phone=flags.get("phone", ""),
        actor=ctx.actor_for(person.branch_code),
        branch=ctx.branch(person.branch_code),
        profile_fields=fields,
        password=ctx.password,
        send_invitation=False,
    )


def _create_student(ctx: Context, person: Person, fields: dict[str, Any]) -> StudentProfile:
    # Roster phones are unique among themselves, but the database this runs
    # on may already hold an account with the same number by chance. The
    # reason is read only if the duplicate check finds one; then it is audited
    # as an override and the registration proceeds, which is the right thing
    # for a showcase that must not stop on the seventy-third student.
    return create_student(
        email=person.email,
        first_name=person.first_name,
        last_name=person.last_name,
        phone=person.flags.get("phone", ""),
        actor=ctx.actor_for(person.branch_code),
        branch=ctx.branch(person.branch_code),
        profile_fields=fields,
        password=ctx.password,
        send_invitation=False,
        override_reason=ctx.note("Showcase roster account; a different person to any match."),
    )


def _ensure_verified(user: User, person: Person) -> None:
    """Pre-verify, as stage 1 verifies the owner — unless the roster says not to.

    A sign-in blocked behind a verification email is a showcase nobody can
    open, and the flag is not a parameter of any account service, so it is
    set the way ``seed_demo_data`` sets it. The two ``unverified`` rows are
    the unverified-account state and stay as ``create_user`` left them.
    """
    if person.flags.get("unverified") or user.is_email_verified:
        return
    user.is_email_verified = True
    user.email_verified_at = timezone.now()
    user.save(update_fields=["is_email_verified", "email_verified_at"])


# ---------------------------------------------------------------------------
# Roles and scope
# ---------------------------------------------------------------------------


def _ensure_roles(ctx: Context) -> None:
    """The two custom roles, the assignment on ``placement@`` and one lock.

    The lookup goes through ``Role.all_objects``: ``Role.objects`` is the
    soft-delete manager and hides a binned row, ``create_role``'s own slug
    check uses the same manager, and the slug's uniqueness is partial on
    ``deleted_at IS NULL`` — so once stage 8 has binned *Guest lecturer*, a
    live-only lookup would find nothing and ``create_role`` would happily
    make another one per run. A binned role is found, kept binned, and put
    in ``ctx.roles`` as it is.
    """
    owner = ctx.superadmin
    for spec, disabled in ((PLACEMENT_COORDINATOR, False), (GUEST_LECTURER, True)):
        slug = spec["slug"]

        def create(spec: dict[str, Any] = spec, disabled: bool = disabled) -> Role:
            role = create_role(actor=owner, **spec)
            if disabled:
                update_role(actor=owner, role=role, status=RoleStatus.DISABLED)
            return role

        existing = Role.all_objects.filter(slug=slug).order_by("created_at", "pk").first()
        role = ctx.ensure("role", f"role {slug}", existing, create)
        ctx.roles[slug] = role

    holder = ctx.users["placement"]
    role = ctx.roles[PLACEMENT_COORDINATOR["slug"]]
    # The slug also matches a role somebody made by hand under the same name.
    # `update_user` refuses a role of the wrong kind or one that is not live,
    # and that refusal would abort the stage; say what was found and move on.
    usable = (
        not role.is_deleted
        and role.kind == UserRole.COUNSELLOR
        and role.status == RoleStatus.ACTIVE
    )
    if not usable:
        ctx.out(
            f"custom role on {holder.email}: skipped ({role.slug} is "
            f"{'in the bin' if role.is_deleted else f'{role.kind}/{role.status}'}, not usable)"
        )
        return
    if holder.custom_role_id == role.pk:
        ctx.found_existing("custom_role_assignment")
        ctx.out(f"custom role on {holder.email}: found")
    else:
        # Through `update_user`, which checks the kind matches and audits the
        # privilege change; a raw save would do neither.
        update_user(user=holder, actor=owner, custom_role=role)
        ctx.created("custom_role_assignment")
        ctx.out(f"custom role on {holder.email}: created")

    # One locked grant, so the roles matrix shows the padlock. `set_grant_lock`
    # returns early when the flag is already what was asked, but it is checked
    # here first so the finish table says found, not created, on a re-run.
    grant = role.grants.filter(permission__code=LOCKED_CODE).first()
    if grant is None:
        ctx.out(f"permission lock on {role.slug}: skipped ({LOCKED_CODE} is not on the role)")
        return
    ctx.ensure(
        "permission_lock",
        f"permission lock on {role.slug}/{LOCKED_CODE}",
        grant if grant.is_locked else None,
        lambda: set_grant_lock(actor=owner, role=role, code=LOCKED_CODE, locked=True),
    )


def _ensure_scope_grant(ctx: Context) -> None:
    """A course grant on ``counsellor2``, on a course that already exists.

    Stage 2 runs before the catalogue stage, so on a fresh database there is
    no course to grant; on staging the SITP import's courses are there.

    The natural key is *any course grant on the holder*, not the pair
    (holder, chosen course): the choice is made from whatever courses exist,
    and by the second full run stage 3 has added its own, so a lookup keyed
    on this run's choice would miss the grant the first run made and grant a
    second course. The course is picked only when he holds none, and picked
    as the oldest non-archived course — a row stage 3's newer ones cannot
    displace — so a --only run on a database that has run everything makes
    the same choice as the first run did.
    """
    holder = ctx.users["counsellor2"]
    existing = (
        ScopeGrant.objects.filter(user=holder, course__isnull=False)
        .select_related("course")
        .order_by("created_at", "pk")
        .first()
    )
    if existing is not None:
        ctx.found_existing("scope_grant")
        ctx.out(f"scope grant for {holder.email} on {existing.course.slug}: found")
        return
    candidates = [c for c in ctx.courses.values() if c.status != PublishStatus.ARCHIVED]
    course = min(candidates, key=lambda c: (c.created_at, c.pk), default=None)
    if course is None:
        ctx.out(f"scope grant for {holder.email}: skipped (no course exists yet)")
        return
    ctx.ensure(
        "scope_grant",
        f"scope grant for {holder.email} on {course.slug}",
        None,
        lambda: grant_scope(actor=ctx.superadmin, user=holder, course=course),
    )


# ---------------------------------------------------------------------------
# The rest of the people screens
# ---------------------------------------------------------------------------


def _ensure_teaching_manager(ctx: Context) -> None:
    manager = ctx.users["manager"]
    ctx.ensure(
        "teaching_profile",
        f"teaching profile for {manager.email}",
        TrainerProfile.objects.filter(user=manager).first(),
        lambda: ensure_teaching_profile(user=manager, actor=ctx.superadmin),
    )


def _ensure_preferences(ctx: Context, plan: Plan) -> None:
    """The headline pair's saved choices, and the WhatsApp consents.

    The preference row is the natural key, not its contents: ``preferences_for``
    creates a row on first read and ``update_preferences`` saves whatever it is
    handed unconditionally, so calling either on a re-run would re-stamp
    ``updated_at`` and put back a switch somebody flipped on the settings
    screen during a walkthrough. The row is looked up with a plain filter,
    and only a missing one is written.
    """
    # The headline pair switch something off, so the preferences screen shows
    # a saved choice rather than the defaults it would show with no row.
    for local_part, fields in (
        ("trainer", {"email_announcements": False}),
        ("student", {"email_administrative": False}),
    ):
        user = ctx.users[local_part]
        ctx.ensure(
            "notification_preference",
            f"notification preferences for {user.email}",
            NotificationPreference.objects.filter(user=user).first(),
            lambda user=user, fields=fields: update_preferences(user=user, **fields),
        )

    for local_part in plan.whatsapp:
        user = ctx.users[local_part]
        if user.whatsapp_opt_in:
            ctx.found_existing("whatsapp_opt_in")
            continue
        person = ctx.person_for(user)
        update_user(user=user, actor=ctx.actor_for(person.branch_code), whatsapp_opt_in=True)
        ctx.created("whatsapp_opt_in")
    ctx.out(f"whatsapp opt-in on {len(plan.whatsapp)} students")


def _ensure_referrals(ctx: Context, plan: Plan) -> None:
    """The second pass the contract asks for: ``referred_by`` on twelve students.

    A referral already on a record is left alone whoever set it — the fact
    of a referral does not change because the seed ran again.
    """
    profiles = {
        profile.user.email: profile for profiles in ctx.students.values() for profile in profiles
    }
    counsellor = ctx.counsellors[MAIN]
    for referred_lp, referrer_lp in plan.referrals:
        referred = profiles[ctx.users[referred_lp].email]
        referrer = profiles[ctx.users[referrer_lp].email]
        if referred.referred_by_id is not None:
            ctx.found_existing("referral")
            continue
        update_student_profile(
            profile=referred,
            actor=counsellor,
            allowed_fields=("referred_by",),
            referred_by=referrer,
        )
        ctx.created("referral")
    ctx.out(f"referrals on {len(plan.referrals)} students")


def _ensure_denied_audit(ctx: Context) -> None:
    """One refused action on the audit trail, in the counsellor's name.

    ``create_user`` refuses before it writes anything, and it does not audit
    the refusal itself — for a request, the API layer's handler does. Outside
    a request the audit service's *durable* path queues the entry for
    middleware that never runs, so the row is written inline through
    ``record`` with ``durable=False``: this stage's transaction commits (the
    refusal was caught), so an inline row is safe here where in a request it
    would be rolled back with the failure it describes.
    """
    counsellor = ctx.counsellors[MAIN]
    key = ctx.tag(DENIED_TAG)
    existing = AuditLog.objects.filter(
        action=AuditAction.PERMISSION_DENIED, actor=counsellor, context__note=key
    ).first()

    def create() -> AuditLog | None:
        try:
            create_user(
                email=DENIED_EMAIL,
                password=ctx.password,
                first_name="Kunal",
                last_name="Bhatnagar",
                role=UserRole.MANAGER,
                actor=counsellor,
                branch=ctx.branch(MAIN),
                send_invitation=False,
            )
        except ApplicationError:
            return record(
                action=AuditAction.PERMISSION_DENIED,
                actor=counsellor,
                resource_type="user",
                result=AuditResult.DENIED,
                durable=False,
                context={"note": key, "attempted_role": UserRole.MANAGER, "email": DENIED_EMAIL},
            )
        # Reaching here means a counsellor was allowed to create a manager,
        # which is a bug in the ladder, not a state to seed. Abort the stage.
        raise RuntimeError("create_user let a counsellor create a manager; refusing to continue.")

    ctx.ensure("audit_denied", f"denied audit row for {counsellor.email}", existing, create)
