"""The ten stages, in the only order they can run.

Each stage is a module exposing ``run(ctx: Context) -> None`` and a docstring
that is its contract: what it creates, through which services, and what it
leaves in ``ctx`` for the stages after it. The order is the dependency order
from the model brief — people need centres, batches need courses and
trainers, fees need enrolments, work needs students and batches — and the
``seed_showcase`` command runs each stage in its own transaction so a failure
in stage six keeps stages one to five.

Keys are what ``--only`` and ``--from`` accept. They are part of the command's
interface, so they do not change.
"""

from __future__ import annotations

from collections.abc import Callable

from ..context import Context
from . import (
    s01_organisation,
    s02_people,
    s03_courses,
    s04_batches,
    s05_fees,
    s06_academics,
    s07_teaching_ops,
    s08_work,
    s09_comms,
    s10_finish,
)

STAGES: list[tuple[str, Callable[[Context], None]]] = [
    ("organisation", s01_organisation.run),
    ("people", s02_people.run),
    ("courses", s03_courses.run),
    ("batches", s04_batches.run),
    ("fees", s05_fees.run),
    ("academics", s06_academics.run),
    ("teaching_ops", s07_teaching_ops.run),
    ("work", s08_work.run),
    ("comms", s09_comms.run),
    ("finish", s10_finish.run),
]

STAGE_KEYS: list[str] = [key for key, _ in STAGES]

__all__ = ["STAGES", "STAGE_KEYS"]
