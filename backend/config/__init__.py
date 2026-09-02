"""Django project package.

The Celery app is imported here so that `@shared_task` decorators resolve to it
no matter which module Django imports first. Guarded because settings modules
are also loaded by tooling (schema generation, checks) where a missing Celery
install should not be fatal.
"""

from __future__ import annotations

try:
    from .celery import app as celery_app
except ImportError:  # pragma: no cover - celery is a declared dependency
    celery_app = None

__all__ = ("celery_app",)
