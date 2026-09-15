# Design decisions — ERP screens

The product and UI decisions behind the ERP screens. They extend, never
replace, the LMS design system (`frontend/app/globals.css` tokens, 25
primitives in `components/ui`, `data-table`, `states`, D-101 light only,
D-102 two layouts). Speed of operation beats visual novelty (brief §56).

## Screen contract

Every ERP screen declares, in its file header comment: purpose, user,
primary action, secondary actions, API on load / on action / on save,
state model (loading, empty, error, denied, not found, success),
permissions, mobile behaviour, confirmation requirements. The unit test
for the screen covers the six states.

## Dashboards

- One summary endpoint per dashboard; tiles are links, never widgets that
  fetch on their own. Refresh is a button, not a timer (the exception is
  the export panel's 5-second poll while a job is in flight, which exists).
- Tile order is the owner's priority (14 September): admin = activity
  review → manager's work → trainers → counsellor's work → students and
  fees; manager = risk → trainer work → DSR → overdue → attendance →
  reviews; trainer = today's classes; counsellor = new → pending →
  follow-ups; student = progress → next actions.
- Numbers on tiles use `formatCount`; a null is "No data", never 0.

## Navigation

- Sidebars stay as they are (`navigation.ts`), with new entries: admin
  "Configuration" group (Roles, Policies, Forms, Activity types,
  Automations, Templates) and "Communication" group (Delivery log,
  Announcements); staff "Work" group (My work, Activities); student "My
  activities". Trainers keep `STAFF_NAV`.
- Command palette (`mod+k`): jump to a screen by name, search records,
  run "quick create" (activity, follow-up, student). Results come from
  `/search/`; navigation items are local. Keyboard only; no mouse-hover
  fetches.
- Breadcrumb on Student 360 and builders: `Students › Rahul Verma ›
  Activities`.

## Student 360

- One page, `/students/[id]`, for every staff role; what differs is the
  data the server returns. The counsellor record (`/admissions/[id]`)
  keeps the fee ledger and links to the 360; the manager enrolment page
  (`/manage/students/[enrollmentId]`) redirects to the 360 with the
  Enrolment tab open (D-128: no dead links).
- Header answers the four questions at a glance: who, where (batch,
  trainer, counsellor), how (overall score with a "why" popover listing
  components), and how worried (risk badge with the triggered rules).
- Tabs load on open; the URL carries the tab (`?tab=activities`) so Back
  and sharing work.

## Activity timeline

- Vertical, newest first, day-grouped, cursor-paginated ("Show earlier").
  Each entry: icon by kind, title, one-line summary, actor, time, link.
- Filters are chips (kinds) plus a date range; they live in the URL.
- Student-visible filtering happens on the server; the UI never hides
  by role.

## Activity drawer

- A right-hand `Sheet`, 560 px on desktop, full-screen on mobile. Header:
  type, student, status badge, assignee, due. Body: the form (read-only
  after completion), history, next action. Footer: the one primary verb
  for the current status (Start / Complete / Approve) and secondary verbs
  in an overflow menu (Reassign, Cancel, Reopen).
- Drafts of form answers are kept locally (same as the DSR panel) until
  Complete succeeds.
- Closing with unsaved answers asks Stay / Discard.

## Role builder and permission matrix

- Builder is a three-step page (name → permissions → review), not a
  dialog; Back is safe (state kept until Create).
- Matrix cells are one of five states with distinct glyphs and text, not
  colour alone: explicit (filled check), inherited (outlined check),
  locked (padlock), denied (dash), system (grey check, no control).
- Scope picker appears only when the row is on; options limited to the
  kind's floor.

## Policy builder

- Category list left, keys right; each key shows value, default,
  "changed by / when", and a History link. Critical keys carry a red
  "critical" tag and the typed-confirmation + step-up flow.

## Form builder

- Field list with drag handles (keyboard: Alt+↑/↓), field editor in a
  drawer, live preview on the right. Publish is a dialog naming the
  version and how many records will keep the old one.

## Activity builder, automation builder, template builder

- Same page skeleton: settings form left, preview/test right, Save draft
  and Activate/Publish as separate verbs with their own confirmations.
- Automation builder's condition editor is a form (path picker, operator,
  value), never a text expression.

## Communication center

- `/admin/communication`: tabs Notifications (kinds and who gets what),
  Email templates, WhatsApp templates, Announcements, Delivery log,
  History (per student, from the 360's Communication tab). Sending is
  always a two-step: pick → "Preview recipients (N)" → confirm.

## Tables

- `data-table` everywhere: sortable columns, sticky first column, roving
  focus, shift-click range selection for bulk actions, density toggle.
  Bulk actions appear as a bar above the table showing the count and the
  operation; significant ones confirm with count and scope.
- Row click opens; a checkbox selects. Neither writes.

## Confirmation behaviour

`ConfirmDialog intent="mutation" | "destructive" | "expensive"`:
- mutation: title, one sentence, Cancel / verb.
- destructive: plus a reason field (required) and, for purge, the typed
  label; the verb is red.
- expensive: plus the count and destination ("Export 4,812 rows to
  Excel; you will be notified").
Step-up, when required by the server, is a nested dialog and the original
request is retried once after success.

## Empty, loading, error states

- `LoadingState` skeletons sized like the content (rows for lists, tiles
  for dashboards).
- `EmptyState` always has a sentence and, when the person can act, one
  button.
- `ErrorState` shows the message, the request id and Retry; a 403 renders
  the denied page; a 404 renders "Not found" with a back link.

## Mobile

- Staff screens are desktop-first; on narrow screens the sidebar becomes
  the existing `Sheet`, tables scroll horizontally inside their wrapper,
  drawers go full-screen, dashboards stack tiles.
- Manager quick review (360 header + Risk tab) and trainer quick work
  (Today, drawer) are tested at 400 px in the unit suite.

## Accessibility

- Every control labelled; focus visible; dialogs and sheets trap focus
  and restore it; live regions for toasts and form errors; contrast
  asserted by `theme-contrast.test.ts`; keyboard paths for drag (Alt+↑/↓)
  and range select (Shift+Space).

## Search and saved filters

- Search box in the top bar opens the palette; results grouped by type
  with counts; Enter opens the first.
- Saved filters move to the server (per user, per screen) and appear as
  chips above lists; localStorage remains a cache.

## Caching UX and optimistic UI

- The UI never shows a stale number as fresh: dashboards show "as of
  10:42" from the response and a Refresh button.
- Optimistic updates only for safe, reversible toggles (mark
  notification read, save a filter). Every other write waits for the
  server and re-reads.

## Unsaved-changes guard

- `useUnsavedChanges(isDirty)` registers `beforeunload` and intercepts
  in-app navigation with the Stay / Discard dialog. Used by every builder,
  the activity drawer, the registration wizard.
