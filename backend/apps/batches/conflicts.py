"""Schedule conflict detection.

Two rules, both about *relationships between rows*, so neither can be a column
constraint and neither may be left to the interface:

* A trainer cannot teach two classes at once.
* A batch cannot hold two classes at once.

Overlap is three-dimensional. Two weekly slots clash only when all three hold:

1. **Same weekday.** Monday 09:00 and Tuesday 09:00 never clash.
2. **Overlapping times.** ``start_a < end_b and start_b < end_a`` — the standard
   half-open comparison, so a class ending at 11:00 and one starting at 11:00 do
   *not* clash. Back-to-back classes are normal and must stay allowed.
3. **Overlapping batch date ranges.** Two Monday-morning slots in batches that
   run in different months never meet, so they do not clash.

Comparison happens in each slot's own time zone. Two slots in different zones
are compared by converting both to a common reference day, because 09:00 in
Kolkata and 09:00 in London are different moments and must not be treated as a
clash.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django.db.models import Q, QuerySet

from .models import Batch, BatchSchedule

#: An arbitrary fixed date used only to turn two wall-clock times into
#: comparable instants. Any date works; what matters is that both sides use the
#: same one.
_REFERENCE_DATE = date(2000, 1, 3)  # a Monday


@dataclass(frozen=True)
class Conflict:
    """One clash, described well enough to show a person what went wrong."""

    kind: str  # "trainer" or "batch"
    schedule_id: str
    batch_code: str
    batch_name: str
    weekday: int
    detail: str

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "schedule_id": str(self.schedule_id),
            "batch_code": self.batch_code,
            "batch_name": self.batch_name,
            "weekday": self.weekday,
            "detail": self.detail,
        }


def _instant(moment: time, timezone_name: str) -> datetime:
    """Turn a wall-clock time in a zone into a comparable instant."""
    try:
        zone = ZoneInfo(timezone_name or "UTC")
    except Exception:
        zone = ZoneInfo("UTC")
    return datetime.combine(_REFERENCE_DATE, moment, tzinfo=zone)


def times_overlap(
    start_a: time, end_a: time, zone_a: str, start_b: time, end_b: time, zone_b: str
) -> bool:
    """Half-open overlap, zone-aware. Back-to-back slots do not overlap."""
    return _instant(start_a, zone_a) < _instant(end_b, zone_b) and _instant(
        start_b, zone_b
    ) < _instant(end_a, zone_a)


def date_ranges_overlap(batch_a: Batch, batch_b: Batch) -> bool:
    return batch_a.start_date <= batch_b.end_date and batch_b.start_date <= batch_a.end_date


def _candidate_schedules(schedule: BatchSchedule, batch: Batch) -> QuerySet[BatchSchedule]:
    """Every slot that could possibly clash with this one.

    Narrowed in the database — same weekday, active, in a batch that is not
    cancelled and whose dates overlap — so the Python comparison below runs over
    a handful of rows rather than the whole timetable.
    """
    from .models import BatchStatus

    trainer_id = schedule.trainer_id or batch.trainer_id

    candidates = (
        BatchSchedule.objects.select_related("batch", "batch__trainer")
        .filter(weekday=schedule.weekday, is_active=True)
        .exclude(batch__status=BatchStatus.CANCELLED)
        .filter(batch__start_date__lte=batch.end_date, batch__end_date__gte=batch.start_date)
    )
    if schedule.pk:
        candidates = candidates.exclude(pk=schedule.pk)

    # Only two things can clash: the same batch, or the same trainer.
    scope = Q(batch_id=batch.pk)
    if trainer_id:
        scope |= Q(trainer_id=trainer_id) | Q(trainer__isnull=True, batch__trainer_id=trainer_id)
    return candidates.filter(scope)


def find_conflicts(schedule: BatchSchedule, *, batch: Batch | None = None) -> list[Conflict]:
    """Every clash this slot would cause. Empty means it is safe to save."""
    batch = batch or schedule.batch
    trainer_id = schedule.trainer_id or batch.trainer_id
    conflicts: list[Conflict] = []

    for other in _candidate_schedules(schedule, batch):
        if not times_overlap(
            schedule.start_time,
            schedule.end_time,
            schedule.timezone_name,
            other.start_time,
            other.end_time,
            other.timezone_name,
        ):
            continue
        if not date_ranges_overlap(batch, other.batch):
            continue

        window = (
            f"{other.get_weekday_display()} "
            f"{other.start_time:%H:%M}-{other.end_time:%H:%M} {other.timezone_name}"
        )
        if other.batch_id == batch.pk:
            conflicts.append(
                Conflict(
                    kind="batch",
                    schedule_id=other.pk,
                    batch_code=other.batch.code,
                    batch_name=other.batch.name,
                    weekday=other.weekday,
                    detail=f"This batch already has a class at {window}.",
                )
            )
        elif trainer_id and other.effective_trainer_id == trainer_id:
            conflicts.append(
                Conflict(
                    kind="trainer",
                    schedule_id=other.pk,
                    batch_code=other.batch.code,
                    batch_name=other.batch.name,
                    weekday=other.weekday,
                    detail=(
                        f"The trainer already teaches {other.batch.code} "
                        f"({other.batch.name}) at {window}."
                    ),
                )
            )
    return conflicts


def trainer_conflicts_for_batch(batch: Batch, trainer) -> list[Conflict]:
    """Clashes that assigning ``trainer`` to ``batch`` would create.

    Used before a trainer assignment, so the refusal names the class they are
    already teaching rather than failing on the next schedule edit.
    """
    conflicts: list[Conflict] = []
    for schedule in batch.schedules.filter(is_active=True, trainer__isnull=True):
        probe = BatchSchedule(
            pk=schedule.pk,
            batch=batch,
            weekday=schedule.weekday,
            start_time=schedule.start_time,
            end_time=schedule.end_time,
            timezone_name=schedule.timezone_name,
            trainer=trainer,
        )
        conflicts.extend(
            conflict
            for conflict in find_conflicts(probe, batch=batch)
            if conflict.kind == "trainer"
        )
    return conflicts
