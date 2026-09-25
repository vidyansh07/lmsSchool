"""The showcase data set: a coherent, live-looking institution for demos.

``seed_demo_data`` and its siblings each seed one app and stop; a reviewer
opening the result sees twenty placeholder students and a handful of batches.
A *showcase* is the opposite: one management command (``seed_showcase``) that
walks the whole product in dependency order — centres and settings, then
people, then the catalogue, then batches and enrolments, fees, academic
delivery, work, communication — and leaves every screen, filter and chart with
something real-looking on it. Dates are relative to today, so every re-run
keeps the dashboards live rather than showing a demo that stopped in September.

The set is built as ten *stages* (:mod:`apps.common.showcase.stages`), each a
function that receives one :class:`~apps.common.showcase.context.Context` and
creates its slice through the same services the API uses, so audit rows,
notifications, identifiers and cascades all happen the way they do in
production.

Four safety properties, in order of importance
----------------------------------------------

1. **Additive.** Nothing is ever deleted. The showcase is layered on top of
   whatever the database already holds — on staging that is the ``seed_demo_data``
   roster and ~1,700 imported SITP accounts — and it only *changes* an existing
   row where a stage deliberately upgrades it (renaming the default centre,
   publishing the imported courses). Every other row it did not create is
   left exactly as found.
2. **Idempotent.** Re-running creates no duplicates. Each stage finds its own
   rows before creating them: people by their roster email, branches by code,
   calendar entries by (name, date), free-text rows by the ``[showcase]`` marker
   every note, reason and description carries. The second run reports
   "found" where the first reported "created".
3. **Gated.** Seeding runs only where ``settings.ALLOW_DEMO_SEED`` is true
   (local, development, test, staging). Production refuses before touching
   anything, exactly as ``seed_demo_data`` does.
4. **No password on disk.** Every showcase account shares the password in the
   ``DEMO_USER_PASSWORD`` environment variable. It is validated against the
   project's password policy, used once per account, and written to no file,
   no log and no stdout — the sign-in table printed at the end names the
   variable, never its value.

Why the accounts look real
--------------------------
The roster lives on ``grras.com``, the owner's own domain, because a showcase
whose every address ends in ``.invalid`` reads as a fixture rather than as an
institution. That is safe only while nothing addressed to those accounts is
delivered: the command refuses to run when ``EMAIL_BACKEND`` is SMTP (staging
uses the console backend; ``--allow-real-mail`` is the one way past that
refusal), and ``scripts/verify_demo.sh`` accepts that one domain by explicit
allow-list (``VERIFY_ALLOWED_EMAIL_DOMAINS``) while still failing on any other
real domain.
"""
