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

## Remaining UX work

The broader gap audit remains at `.lavish/lms-ux-functional-gap-audit.html`.
The items not listed as fixed above—including additional filters, consolidated
cross-source views, empty-state improvements, contextual help, and other
role-specific workflow refinements—remain proposals until individually
implemented and verified.
