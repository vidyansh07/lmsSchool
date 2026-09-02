"""Abstract model bases shared by every domain app.

Two decisions worth stating once, because every future LMS table inherits them:

* **UUID primary keys.** LMS identifiers appear in URLs, certificates and
  exports. Sequential integers leak enrolment counts and invite enumeration of
  other people's records; UUIDv4 does not.
* **Created/updated timestamps on everything.** Required for audit
  reconstruction and for incremental reporting later.
"""

from __future__ import annotations

import uuid

from django.db import models


class UUIDPrimaryKeyModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BaseModel(UUIDPrimaryKeyModel, TimeStampedModel):
    """The default base for domain models."""

    class Meta:
        abstract = True
        ordering = ("-created_at",)
