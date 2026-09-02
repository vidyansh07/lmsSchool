"""The background worker.

What belongs here
-----------------
One thing, today: sending email. It qualifies on the only test that matters —
the work is slow, it is not needed to answer the request, and it fails in ways
the caller cannot act on. A trainer grading twenty submissions should not wait
on twenty SMTP handshakes, and should not see grading fail because a mail
provider is down.

What deliberately does not
--------------------------
The brief lists heavy reports and large imports as candidates. Both were
measured against the actual system rather than the general principle:

* **Exports** already stream. `apps.reporting.exports` yields rows through a
  generator into a `StreamingHttpResponse`, so an export of the whole
  institution holds one row in memory at a time and starts sending bytes
  immediately. Moving that to a worker would add a job, a poll and a temporary
  file to something that already works in constant memory.
* **Imports** are bounded to 2,000 rows and 2 MB (`MAX_IMPORT_ROWS`,
  `MAX_IMPORT_BYTES`), and confirmation must be all-or-nothing inside one
  transaction. Backgrounding it would buy nothing and would turn a synchronous
  answer — "these 14 rows are wrong, here they are" — into a job the operator
  has to come back for.

Both decisions have a trigger for revisiting written into `docs/DECISIONS.md`.
Every queued job is a thing that can be lost, retried twice or silently
backlogged, so the queue stays small on purpose.

Reliability posture
-------------------
``task_acks_late`` with a prefetch of 1: a task is acknowledged after it
finishes, so a worker killed mid-send has its task redelivered rather than
dropped. That makes duplicate delivery possible, which is why
`send_email_message` is driven by a database row whose status is checked before
sending — the duplicate finds the row already sent and does nothing.

With no broker configured, ``task_always_eager`` runs tasks inline. That is the
local-development default, and `config.settings.hardened` refuses it in a
deployed environment: silently running "background" work inside the request is
exactly the failure this module exists to prevent.
"""

from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("grras_lms")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self) -> str:  # pragma: no cover - operational smoke check
    """Prove a worker is consuming the queue. Used by `make worker-check`."""
    return f"ok from {self.request.hostname}"
