"""The after-class sweep, on a beat (`config/settings/base.py`)."""

from __future__ import annotations

from celery import shared_task


@shared_task(name="dsr.sweep", ignore_result=True)
def sweep() -> dict[str, int]:
    from .services import sweep_after_class

    return sweep_after_class()
