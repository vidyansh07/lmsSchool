"""The people in the showcase, decided once and the same on every run.

A roster that is *generated* rather than *listed* would be different every
time somebody touched the generator, and a demo whose headline student changes
name between deploys is a demo nobody can write a walkthrough for. So the named
accounts are written out, and the hundred anonymous students are drawn from a
private ``random.Random`` seeded with a constant — the same hundred every run,
on every database, in the same order.

Everything a later stage needs to know about a person that is *about the
person* (their specialisation, that they never enrolled, that their email is
unverified) travels on ``Person.flags``. What a stage does with a flag is that
stage's business; the roster only states the facts.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from apps.accounts.models import UserRole

#: The owner's own domain. See the package docstring for why a real-looking
#: domain is used and how ``verify_demo.sh`` is told to accept it.
DOMAIN = "grras.com"

#: Seeds the roster's own generator. Changing it changes every anonymous
#: student's name and phone number, which on an already-seeded database means
#: a hundred *new* students next run — so it is a constant, not a knob.
ROSTER_SEED = 20260925

MAIN = "MAIN"
PUNE = "PUNE"

#: The order accounts are listed in the sign-in table: most powerful first,
#: which is also the order a reviewer walks through them.
ROLE_RANK: dict[str, int] = {
    UserRole.SUPERADMIN: 0,
    UserRole.ADMIN: 1,
    UserRole.MANAGER: 2,
    UserRole.COUNSELLOR: 3,
    UserRole.TRAINER: 4,
    UserRole.STUDENT: 5,
}

#: Names a stage will give the junk batches and course found on staging. Keyed
#: by the *existing* name, lower-cased; stage 4 (batches) and stage 3 (courses)
#: do the renaming, this module only decides what they become.
BATCH_RENAMES: dict[str, str] = {
    "sjggqjkgs": "DevOps Evening — Sep 2026",
    "temp batch": "RHCSA Weekend — Aug 2026",
    "new first batch": "Python Full Stack Morning — Jul 2026",
    "java dsa": "Java & DSA Placement Track — Sep 2026",
}
COURSE_RENAMES: dict[str, str] = {
    "python pro progamming": "Python Pro Programming",
}

# Realistic and varied, so a roster of a hundred does not read as five names on
# repeat. Letters only: a local part is built from these and must stay
# [a-z0-9.], and `validate_person_name` refuses anything that does not start
# with a letter.
FIRST_NAMES = [
    "Aarav", "Aditi", "Aditya", "Akash", "Amit", "Ananya", "Anjali", "Ankit", "Arjun",
    "Ayaan", "Bhavya", "Chirag", "Deepak", "Devika", "Dhruv", "Diya", "Gaurav", "Harsh",
    "Ishaan", "Ishita", "Jatin", "Kabir", "Karan", "Kavya", "Kirti", "Krishna", "Lakshmi",
    "Manish", "Meera", "Mohit", "Nandini", "Naveen", "Neha", "Nikhil", "Nisha", "Nitin",
    "Pallavi", "Pankaj", "Parth", "Pooja", "Prachi", "Pranav", "Priya", "Rahul", "Rajat",
    "Rakesh", "Ravi", "Reyansh", "Rhea", "Riya", "Rohan", "Rohit", "Ruchi", "Saanvi",
    "Sachin", "Sahil", "Sakshi", "Sameer", "Sanjay", "Shivani", "Shreya", "Siddharth",
    "Simran", "Sneha", "Sonali", "Suraj", "Tanvi", "Tarun", "Tushar", "Uday", "Vaishali",
    "Varun", "Vedant", "Vikram", "Vishal", "Vivek", "Yash", "Yashika", "Zoya",
]  # fmt: skip
LAST_NAMES = [
    "Agarwal", "Bhatt", "Bhatnagar", "Chauhan", "Choudhary", "Dixit", "Gehlot", "Goyal",
    "Gupta", "Jain", "Joshi", "Kulkarni", "Kumar", "Kumawat", "Malhotra", "Meena", "Mehta",
    "Mishra", "Nair", "Pandey", "Patel", "Purohit", "Rathore", "Saini", "Saxena", "Sharma",
    "Shekhawat", "Singh", "Soni", "Tiwari", "Trivedi", "Verma", "Vyas", "Yadav",
]  # fmt: skip

#: What the named MAIN trainers teach. The first is the headline account a
#: walkthrough signs in as; the rest give the trainer directory and the batch
#: wizard a spread of specialisations to pick from.
MAIN_TRAINERS: list[tuple[str, str, str, str, list[str], dict[str, Any]]] = [
    (
        "trainer", "Vikram", "Shekhawat", "Senior Linux & DevOps Trainer",
        ["Linux", "RHCSA", "Docker", "Kubernetes", "Ansible"], {},
    ),
    (
        "neha.saxena", "Neha", "Saxena", "Python & Django Trainer",
        ["Python", "Django", "REST", "PostgreSQL"], {},
    ),
    (
        "rohit.kumawat", "Rohit", "Kumawat", "Cloud & AWS Trainer",
        ["AWS", "Terraform", "Linux", "Networking"], {},
    ),
    (
        "priya.malhotra", "Priya", "Malhotra", "Data Science Trainer",
        ["Python", "Pandas", "Machine Learning", "SQL"], {},
    ),
    (
        "sameer.bhatt", "Sameer", "Bhatt", "Cyber Security Trainer",
        ["Ethical Hacking", "Networking", "Linux", "SIEM"],
        # Fully booked: the batch wizard should show him as unavailable.
        {"is_accepting_assignments": False},
    ),
    (
        "deepak.purohit", "Deepak", "Purohit", "Networking Trainer",
        ["CCNA", "Routing", "Switching"],
        # Left the institute: the inactive-trainer filter needs a row.
        {"inactive": True},
    ),
]  # fmt: skip
PUNE_TRAINERS: list[tuple[str, str, str, str, list[str], dict[str, Any]]] = [
    (
        "ankit.kulkarni", "Ankit", "Kulkarni", "Full Stack MERN Trainer",
        ["MongoDB", "Express", "React", "Node.js"], {},
    ),
    (
        "shivani.nair", "Shivani", "Nair", "Azure Cloud Trainer",
        ["Azure", "DevOps", "PowerShell"], {},
    ),
    (
        "tushar.patel", "Tushar", "Patel", "Power BI & Analytics Trainer",
        ["Power BI", "SQL", "Excel", "DAX"], {},
    ),
]  # fmt: skip

MAIN_STUDENT_COUNT = 60
PUNE_STUDENT_COUNT = 40


@dataclass
class Person:
    """One account on the roster.

    ``branch_code`` is ``None`` only for the superadmin, who belongs to every
    centre by belonging to none. ``flags`` carries the facts later stages act
    on — see the module docstring.
    """

    local_part: str
    first_name: str
    last_name: str
    role: str
    branch_code: str | None
    flags: dict[str, Any] = field(default_factory=dict)

    @property
    def email(self) -> str:
        return f"{self.local_part}@{DOMAIN}"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class _Allocator:
    """Hands out unique local parts and phone numbers from one seeded generator.

    Kept private to :func:`build_roster` so that nothing else can advance the
    generator and shift every name after it.
    """

    def __init__(self) -> None:
        self.rng = random.Random(ROSTER_SEED)  # noqa: S311 — determinism, not secrecy
        self.local_parts: set[str] = set()
        self.phones: set[str] = set()

    def local_part(self, wanted: str) -> str:
        """``wanted`` if free, else ``wanted2``, ``wanted3``… — never a collision."""
        candidate = wanted
        suffix = 2
        while candidate in self.local_parts:
            candidate = f"{wanted}{suffix}"
            suffix += 1
        self.local_parts.add(candidate)
        return candidate

    def phone(self) -> str:
        """``+91`` and ten digits starting 6-9, as an Indian mobile number does.

        Matches ``PHONE_RE`` (``^\\+?[0-9]{8,15}$``) and is unique across the
        roster, because ``create_student`` treats a shared phone as a duplicate
        registration.
        """
        while True:
            number = f"+91{self.rng.randint(6, 9)}{self.rng.randint(0, 10**9 - 1):09d}"
            if number not in self.phones:
                self.phones.add(number)
                return number

    def name(self) -> tuple[str, str]:
        return self.rng.choice(FIRST_NAMES), self.rng.choice(LAST_NAMES)


def build_roster() -> list[Person]:
    """Every showcase account, in the order stages create them.

    The order matters twice over: ``create_user`` checks that the actor may
    grant the role, so the superadmin comes first and the admins next; and
    :func:`apps.common.showcase.context.hydrate` takes the *first* admin,
    manager and counsellor it meets per centre as that centre's default actor.
    """
    alloc = _Allocator()

    def person(local_part: str, first: str, last: str, role: str, branch: str | None, **flags):
        return Person(
            local_part=alloc.local_part(local_part),
            first_name=first,
            last_name=last,
            role=role,
            branch_code=branch,
            flags={"phone": alloc.phone(), **flags},
        )

    roster: list[Person] = [
        # The boss. No centre: a superadmin sees every centre by belonging to none.
        person("owner", "Rajesh", "Sharma", UserRole.SUPERADMIN, None),
        person("admin", "Anjali", "Mehta", UserRole.ADMIN, MAIN),
        person("admin.pune", "Nikhil", "Joshi", UserRole.ADMIN, PUNE),
        person("manager", "Kavita", "Rathore", UserRole.MANAGER, MAIN),
        person("manager.pune", "Sanjay", "Deshmukh", UserRole.MANAGER, PUNE),
        # Staff whose email bounced: the unverified-account state, on a staff row.
        person("manager2", "Manish", "Gehlot", UserRole.MANAGER, MAIN, unverified=True),
        person("counsellor", "Pooja", "Agarwal", UserRole.COUNSELLOR, MAIN),
        person("counsellor2", "Rahul", "Verma", UserRole.COUNSELLOR, MAIN),
        person("counsellor.pune", "Sneha", "Kulkarni", UserRole.COUNSELLOR, PUNE),
        # A configured role of the counsellor kind, so the roles matrix has a
        # custom role with a user on it (stage 2 creates the Role first).
        person(
            "placement",
            "Ravi",
            "Choudhary",
            UserRole.COUNSELLOR,
            MAIN,
            custom_role="placement-coordinator",
        ),
    ]

    for branch, trainers in ((MAIN, MAIN_TRAINERS), (PUNE, PUNE_TRAINERS)):
        for local_part, first, last, title, skills, extra in trainers:
            roster.append(
                person(
                    local_part,
                    first,
                    last,
                    UserRole.TRAINER,
                    branch,
                    professional_title=title,
                    skills=skills,
                    **extra,
                )
            )

    # The headline student: the account every walkthrough opens first.
    roster.append(person("student", "Aarav", "Mehta", UserRole.STUDENT, MAIN))

    # The anonymous hundred. Drawn from the seeded generator, so the same
    # people every run; the special cases are pinned to fixed positions so a
    # walkthrough can name them.
    special_main = {
        3: {"inactive": True},
        7: {"never_enrolled": True},
        11: {"unverified": True},
    }
    for branch, count, specials in (
        (MAIN, MAIN_STUDENT_COUNT, special_main),
        (PUNE, PUNE_STUDENT_COUNT, {}),
    ):
        for index in range(count):
            first, last = alloc.name()
            roster.append(
                person(
                    f"{first}.{last}".lower(),
                    first,
                    last,
                    UserRole.STUDENT,
                    branch,
                    **specials.get(index, {}),
                )
            )

    return roster


def by_role(roster: list[Person], role: str) -> list[Person]:
    return [person for person in roster if person.role == role]


def sorted_for_sign_in(roster: list[Person]) -> list[Person]:
    """Role rank, then centre, then email — the order of the sign-in table."""
    return sorted(roster, key=lambda p: (ROLE_RANK.get(p.role, 99), p.branch_code or "", p.email))


__all__ = [
    "BATCH_RENAMES",
    "COURSE_RENAMES",
    "DOMAIN",
    "MAIN",
    "PUNE",
    "ROLE_RANK",
    "Person",
    "build_roster",
    "by_role",
    "sorted_for_sign_in",
]
