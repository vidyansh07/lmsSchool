# Trainer and user-administration UX hardening

**Implemented:** 15 October 2026  
**Scope:** trainer onboarding and discovery, safe role changes, and role/profile consistency

## Outcome

This change closes the highest-risk findings from the wider LMS UX audit:

- managers and administrators now have one obvious place to find and add trainers;
- a trainer account and its trainer profile are created in one transaction;
- student and trainer identities can no longer be produced as incomplete generic accounts;
- role changes are a deliberate, audited action instead of an ordinary profile edit; and
- stale student or trainer profiles no longer grant access after an account's role changes.

The wider audit contains 28 findings. This change does **not** claim that all 28
have been implemented. The remaining findings stay in the UX backlog for
prioritisation and user testing.

## Fixed user journeys

### Add and manage a trainer

The canonical trainer hub is `/manage/trainers` for both managers and
administrators. The previous `/admin/trainers` address redirects there so old
bookmarks continue to work without maintaining two competing screens.

The hub now provides:

- search by trainer ID, name, email, or professional title;
- skill and assignment-availability filters;
- workload, at-risk-student, availability, and account-state columns;
- an export action;
- row navigation to the trainer's detailed review; and
- capability-gated controls for adding trainers and changing their availability.

`Add trainer` opens a scroll-safe dialog that collects the account and trainer
profile together. It includes phone, professional title, skills, experience,
and centre selection where applicable. The form warns before discarding
unsaved work. A successful submission uses `POST /api/v1/trainers/`, so the
account and profile either both exist or neither exists.

### Create a user

`POST /api/v1/users/` remains the generic staff-account route. It now rejects:

- `student` — students must be registered through Admissions; and
- `trainer` — trainers must be created through Trainer onboarding.

This prevents accounts that have a role but no required domain profile.

### Change a role

The user detail screen separates contact details from authorization. A role
change now uses `POST /api/v1/users/<id>/role-transition/` with:

```json
{
  "role": "counsellor",
  "custom_role": null,
  "reason": "Moved to admissions."
}
```

The server returns `allowed_role_transitions` for the selected account; the UI
does not invent role options locally. Before submission, the screen shows the
old and new role, explains the access/session impact, and requires an audit
reason. API errors remain visible in the confirmation dialog.

An ordinary `PATCH /api/v1/users/<id>/` now changes contact fields only:
`email`, `first_name`, `last_name`, and `phone`.

## Enforced edge cases

| Situation | Enforced behaviour |
| --- | --- |
| Administrator edits their own role | Refused; another authorized administrator is required. |
| Role change has no reason | Refused before any data changes. |
| Actor tries to grant a role above their authority | Refused by the service layer. |
| Staff role changes among superadmin, administrator, manager, and counsellor | Allowed when the actor has authority and can grant the destination role. |
| Student or trainer is changed directly into another persona | Refused with `409`; a dedicated conversion workflow is required. |
| Custom role does not belong to the selected system-role kind | Refused. |
| Teaching manager has an active or upcoming batch | Manager-role removal is refused until those batches are reassigned. |
| Last active superadmin is demoted or deactivated | Refused under a database lock, including concurrent attempts. |
| Role or custom role changes successfully | The change and reason are audited, and existing sessions are revoked. |
| A stale student profile remains after the user stops being a student | Ignored by authorization and omitted from the current-user profile pointer. |
| A stale trainer profile remains on a non-teaching role | Ignored by authorization and trainer announcement targeting. |
| A manager also teaches | Their trainer profile remains valid; teaching access continues until assignments are reassigned. |

## Interface safeguards

- The role selector contains only server-approved transitions.
- Student and trainer records link to their domain-specific profile instead of
  encouraging role edits on the generic account screen.
- Unsaved contact edits and an unsubmitted role selection are guarded during
  navigation and browser unload.
- Trainer availability controls use explicit `Pause assignments` and
  `Accept assignments` labels, including accessible names.
- Add, update, and export controls remain capability-gated in the interface;
  every write is independently authorized again by the backend.

## Main implementation locations

| Area | Files |
| --- | --- |
| Role rules and governed transition | `backend/apps/accounts/roles.py`, `backend/apps/accounts/services.py` |
| User API contract | `backend/apps/accounts/serializers.py`, `backend/apps/accounts/user_views.py`, `backend/apps/accounts/user_urls.py` |
| Role/profile access checks | `backend/apps/batches/access.py`, `backend/apps/courses/access.py`, `backend/apps/authorization/scopes.py`, `backend/apps/announcements/services.py` |
| Trainer hub and onboarding | `frontend/app/manage/trainers/page.tsx`, `frontend/app/admin/trainers/create-trainer-dialog.tsx` |
| User administration | `frontend/app/admin/users/[userId]/page.tsx`, `frontend/lib/people.ts` |
| Navigation compatibility | `frontend/components/navigation.ts`, `frontend/app/admin/trainers/page.tsx` |

## Verification

- Frontend full suite: **1,476 passed** across 159 test files.
- Frontend focused rerun after final changes: **13 passed** across 3 test files.
- Frontend ESLint and TypeScript checks: passed.
- Directly affected backend suites: **122 passed**.
- Showcase regression suites affected by the new required audit reason:
  **86 passed**.
- Django migration check: no model changes detected.
- Ruff and `git diff --check`: passed.

The first broad backend run found 16 showcase-seeding failures because an
internal custom-role assignment did not yet provide the newly required audit
reason. That caller was corrected and its 86 affected tests passed. A subsequent
broad rerun reached 2,942 passed and 4 skipped with no failures before becoming
stuck in a long PostgreSQL-bound showcase section; it was interrupted. A clean,
uninterrupted full backend regression and a live browser walkthrough therefore
remain release-verification tasks. The connected Chrome automation bridge also
failed to initialize during this pass, so visual browser QA was not recorded as
complete.

Django's built-in admin is a break-glass maintenance surface and writes user
models directly instead of calling the account service. Routine user and role
administration must use the product UI/API described above. Protecting or
removing the direct Django-admin role fields remains a separate hardening item.

## Follow-up loop (15 October 2026, later the same day)

A second pass re-read the audit, added a security review of the change above
and a separate audit of the daily counsellor, trainer and student flows, and
then fixed the findings one at a time, each with its own tests.

### Security

| Finding | Fix |
| --- | --- |
| An administrator could move their **own** sign-in email through `PATCH /users/<id>/` with no re-verification, session reset or audit entry | Refused in `accounts.services.update_user`; another administrator must do it |
| A role change needed no step-up, unlike ending a session or locking a permission | `role-transition/` answers `403 step_up_required`; the role dialog opens the step-up dialog and retries |
| Omitting `custom_role` on a transition silently removed it and ended the person's sessions | Omitted means unchanged (dropped only with a change of kind); `null` clears |
| A leftover trainer profile on a non-teaching role stayed in the directory and could be given batches; a timetable slot's trainer was not checked at all, even across centres; a manager could edit a peer manager's teaching profile | One gate (`batches.services._check_assignable_trainer`, row-locked against a racing role change) for batch and slot trainers; the directory lists teaching roles only; trainer edits follow the authority ladder |
| Session list/revoke, scope grants and profile-image removal checked the capability and centre but not the ladder; scope grants could be granted to oneself; the credential-link route looked accounts up across centres | `accounts.services.ensure_may_administer` on each; self-grants refused; scoped lookups |
| A superadmin demoted to a centre-bound role kept no centre and saw nothing | Refused until the account is placed; those roles are not offered for a centreless account |
| Two first requests for a manager's teaching profile could race into a 500 | Creation serialised on the account row |

### Daily flows

- **Errors that vanished.** `fieldErrors` now maps `non_field_errors`, nested
  serializer errors (`{"profile": {...}}`), row lists and throttles (`429`)
  onto what forms render, and `unshownError` puts any other refusal above the
  form. Fee, payment, next-due, follow-up, requirement, policy, role-builder,
  review, registration, class-report and trainer-onboarding forms use it.
- **Payments after a timeout.** A timed-out "Record a payment" says the
  payment may already be saved and refreshes the ledger instead of inviting a
  second receipt.
- **Landing.** Everyone used to land on a placeholder home page. Sign-in now
  goes to the person's own first navigation entry (a manager to `/manage`),
  and back to the page that sent them there (`?next=`, same-site only).
- **Expired sessions.** Any `authentication_required` answer while signed in
  forgets the user, so the page sends them to sign-in, which says the session
  ended — instead of "Authentication is required." with a Retry that could
  never work.
- **Irreversible one-click actions now ask first:** withdrawing or
  suspending an enrolment (withdraw needs a reason, stored as the status
  note), deactivating an account (reason required and audited), moving an
  account to another centre, removing a weekly timetable slot, and submitting
  an exam paper (with the unanswered count). At zero the exam paper locks,
  saves what was mid-typing and reads the result back from the server.
- **Finish class.** Unmarked students are no longer silently recorded absent:
  Finish and Save ask first and then mark them explicitly, so the report's
  counts match the register. A report the autosave had just started no longer
  fails Finish with a hidden 409, and any refusal is shown.
- **Links that went nowhere.** `/activities/<id>` and `/dsr/<id>` — the links
  notifications carry — now forward to the drawer, the review sheet, the
  trainer's class or the student's own page. The timeline's attendance entry
  links to the student's Enrolment tab.
- **Students' activities.** `/my-activities` lists what trainers shared,
  read-only, showing only the answers marked visible to students.
- **Dashboards** show a failed chart as an error with Try again, not as
  "Nothing is waiting on you".
- **Dates** use the viewer's own calendar day (`localIsoDate`): "This month"
  no longer starts on the last day of the previous month in India, and
  "today" is right between midnight and 05:30.
- **Registration wizard.** A failed duplicate check is said, not treated as
  "no duplicates"; a duplicate the server finds brings the matches back up;
  once the student record exists its fields are locked with an explanation
  rather than edits being silently ignored.
- **User accounts.** Centre column and filter for those who see every
  centre; "Add staff account" for administrators, managers and counsellors
  (trainers and students are pointed at their own onboarding). Scope grants
  are chosen by searching batches, a failed load is an error with retry, and
  a failed centre move keeps what was typed. A manager who also teaches is
  marked as such here and in the trainer directory.
- **Lists keep their state in the address bar** (search, sort, page and
  filters) on users, students, batches, courses, admissions and the manager
  hubs, so refresh, Back and shared links return to the same rows. The
  trainer hub's export now carries its filters, and its skill filter applies
  as you type.

Verification for the loop: frontend 166 files / 1,524 tests (also green under
`TZ=Asia/Kolkata`), ESLint and TypeScript clean, production build clean; the
affected backend suites and a full backend run are recorded in the change
summary that accompanies this branch.

## Remaining UX work

The broader gap audit remains at `.lavish/lms-ux-functional-gap-audit.html`.
The items not listed as fixed above—including additional filters, consolidated
cross-source views, empty-state improvements, contextual help, and other
role-specific workflow refinements—remain proposals until individually
implemented and verified.
