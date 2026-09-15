# User journeys

Written for a person who does not read code. Each journey says what the
person sees, what they are trying to do, what happens when they click, what
the system remembers, who can see it later, and what happens next. Screens
are named by their address; every address either exists today or is
delivered in the phase named.

Every journey has the same eight paths at the end: happy, empty, error,
unauthorized, timeout, duplicate, conflict, cancelled. Where a path is the
same for every journey it is written once in §0.

## 0. Paths every journey shares

| Path | What the person sees | What the system does |
| --- | --- | --- |
| Empty | A calm empty state with one sentence and, where it makes sense, the one button that fills it ("No activities today. Plan one.") | Reads only |
| Error | A card: "Could not load …", the reason in plain words, a Retry button and the request id in small print | Logs with the request id; nothing saved |
| Unauthorized | Either the link is not shown (the sidebar is built from the person's permissions) or, if typed by hand, a "You do not have access to this" page with a link back | The server refused (403), audited |
| Timeout | After 20 s: "This is taking too long" with Retry; nothing partial is shown | The browser abandoned the request; the server may still finish a read, never a write without the person retrying |
| Duplicate submit | The second click is ignored while the first is in flight (button disabled, spinner); a retry after a network failure returns the same record, not a second one | `client_key` idempotency on creates |
| Conflict | "Someone changed this while you were editing" with what changed and Reload | 409 with `details.allowed` or the current state |
| Cancelled | Closing a dialog or drawer asks only if there are unsaved changes: "Unsaved changes will be lost — Stay / Discard" | Nothing saved |
| Accidental click | Opening a record, a tab, a menu or a drawer never changes anything. Only a button whose label is a verb writes, and dangerous verbs open a confirmation first | GET never mutates |

## 1. Admin

**Who.** Runs the institution's configuration and watches the system.
Signs in at `/login`; MFA is required for admins once Phase 5 is live.

### 1.1 Morning
Dashboard `/admin/overview`: "Good morning, Asha." Tiles: active users,
active students, active batches, trainer workload, pending approvals
(completions awaiting approval, reviews awaiting acknowledgement,
templates awaiting approval), system alerts (failed deliveries, failed
exports, automation failures, last backup and last verified restore), and
the activity review (`/admin/activity`) below. One request loads the
tiles; nothing else fires until a tile is clicked. Clicking a tile opens
the list already filtered.

### 1.2 Create a role (Phase 1)
Goal: a "Placement coordinator" who can run placement activities but not
touch fees.

1. `/admin/roles` — a table of roles: system roles at the top with a lock
   icon, custom ones below, each with how many people hold it.
2. "New role" opens the Role Builder as a full page (`/admin/roles/new`),
   not a dialog: it is long.
3. Step 1 — Name "Placement coordinator", built from "Manager". The
   description explains: "Built-from decides what this role can never
   exceed and how far it sees (its own centre)."
4. Step 2 — Permissions: the matrix grouped by category, each row a
   switch and, when on, a scope picker limited to what the base allows.
   Pre-filled from Manager. Asha switches off "Fees: manage" and "Daily
   reports: review". Locked rows show a padlock and cannot be changed.
5. Step 3 — Review: a diff against Manager ("2 removed, 0 added") and
   who will be affected (nobody yet).
6. "Create role" — the only write in the journey.

After the click: the role and its grants exist; the roles cache is
cleared; an audit row "Role created: placement-coordinator by Asha" is
written; the screen shows "Role created" and the role is now offered in
the user form. Nothing else was called.

Failure: a slug already used → the name field shows "A role with this
name exists"; a permission wider than Asha's own → "You cannot grant
'Audit: view' because you do not hold it" (403 rendered on the row).

Next: `/admin/users/{id}` → Role: Manager → Custom role: Placement
coordinator → Save. The user's next request uses the new set.

### 1.3 Lock a permission (Phase 2)
`/admin/roles/matrix` — the full matrix. Asha, a superadmin, clicks the
cell "Admin × Export data" → a popover: state "Explicit", buttons Lock /
Deny. Lock opens a confirmation: "Lock 'Export data' for Admin? Only a
superadmin can change it afterwards." Step-up dialog appears if her
last step-up is older than 10 minutes (password or code). Confirm → the
cell shows a padlock; audit "Permission locked".

### 1.4 Change a policy (Phase 3)
`/admin/policies` — categories down the left (Authentication, Password,
MFA, Session, Attendance, DSR, Assessment, Assignment, Activity,
Performance, Communication, Export, Deletion, Approval, File upload,
Notification); keys on the right with the current value, the default and
"changed by Asha on 3 Sep". Editing "MFA required for roles" (critical)
shows a red banner: "This changes how people sign in", asks for a reason,
a typed confirmation of the key, and a step-up. Saved → next login for
those roles asks for a code (after the grace period). History tab shows
every prior value.

### 1.5 Build a form (Phase 8)
`/admin/forms` → "Mock interview" → "New version" (from the published one)
→ drag fields, add "Body language (0–10)", mark it visible to students →
Preview (renders the form and validates a sample answer) → Publish →
confirmation "Version 2 becomes the form for new mock interviews; the 41
completed ones keep version 1." Audit; cache cleared.

### 1.6 Create an activity type (Phase 9)
`/admin/activity-types` → "New type": name, category, who may create, who
may be assigned, student visibility, default duration, form, requires
review, performance weight, risk effect, reminder, next action (a small
guided editor: "When score is below [6], create [Communication practice],
assign to [the same trainer], notify [manager]"). Save. It appears in the
trainer's "Plan an activity" list immediately.

### 1.7 Create a template (Phase 19)
`/admin/templates` → "Activity feedback (email)" → Draft version → editor
with the variable list on the right (click to insert `{{ student.name }}`)
→ Preview with sample data → Test send to myself → Approve → Publish.
WhatsApp templates additionally need a provider template id and approval
with step-up.

### 1.8 Recover a deleted record
`/admin/recovery` (exists) now lists Activities, Roles, Forms, Policies,
Templates, Automations too. Restore is one click with confirmation;
Purge (superadmin) needs the record's label typed and a step-up.

## 2. Manager

**Who.** Runs one centre's operations; may also teach (D-130).

### 2.1 "Which students need attention today?"
`/manage` — tiles in this order: High-risk students, Trainer work
(pending / overdue activities), Pending daily reports, Overdue
activities, Attendance alerts, Pending reviews. One request. Each tile is
a link to a list already filtered to the tile's rows.

### 2.2 Open a student (Phase 11)
Click "High-risk students" → `/admin/students?risk=critical` → click a
row → `/students/{id}` — Student 360.

Top: name, student id, batch, trainer, counsellor, fee status, risk badge,
overall score with "why?". Tabs: Overview · Profile · Enrolment ·
Progress · Attendance · Assessments · Assignments · Projects ·
Activities · Timeline · Performance · Risk · Feedback · Communication ·
Documents · Certificates. The Overview loads in one request; each tab
loads its own list only when opened; opening a tab is a read.

The manager clicks Activities → the list → "Mock Interview · 15 Sep ·
7.2/10 · Rahul" → the drawer opens on the right with the form as it was
filled: Technical 8, Communication 6, Confidence 7, Outcome
"needs_practice", Improve: "Practise structuring answers." Below: the
history (planned by Mira, completed by Rahul), and "Next action created:
Communication practice, assigned to Rahul, due 22 Sep" with a link.

### 2.3 Create a next action by hand
In the drawer: "Create follow-up" → a draft form pre-filled with the
student and the trainer; type "Communication practice", due in 7 days,
priority high, note. "Review" shows exactly what will be created and who
will be told. "Create" is the write. After: the activity exists as
ASSIGNED, Rahul is notified, the timeline gains an entry, audit "Activity
created". The drawer stays on the new activity.

### 2.4 Review a trainer's work
`/manage/trainers/{id}` (exists) gains a "Work" tab: assigned, completed,
pending, overdue, by type, median completion time — every number is a
link to the list it counts. "Record a review" opens the review form
(type, score, rating, strengths, weaknesses, recommendations, next
review); Save as draft → Share (the trainer is told and acknowledges).

### 2.5 Review an activity that requires it
Notification "Project review by Rahul awaits your decision" → drawer →
Approve or "Requires action" with a note → Rahul is told; audit.

### 2.6 Announce to trainers / raise a requirement
Exists (D-132): `/requirements`.

## 3. Trainer

### 3.1 Today's work
`/teaching/today` (exists) — one card per class today:

```
09:00  MERN Batch (MERN-03)   Attendance: pending   DSR: pending   Assessment: none   Activities: 2 pending
```

One request loads the day. Clicking a class opens the workspace in
place: roster with attendance marks, topic, DSR panel, and a new
Activities panel listing the activities due for this batch's students,
with "Plan an activity".

### 3.2 Conduct a mock interview
Activities panel → "Mock Interview · Priya · due today" → drawer → "Start"
(status IN_PROGRESS, timestamp) → the form: Technical, Communication,
Confidence, Overall, Outcome, Strengths, Improve, Private notes → "Complete".

What the system does, in order: validates every field against the form
version pinned when the activity was planned; saves the activity and the
answers; writes the history line; recalculates Priya's performance
components and risk (the drawer shows the new overall score and a "risk:
warning → none" chip if it changed); because Communication was 5 the
"Communication practice after a weak mock" rule creates a Communication
practice activity assigned to the same trainer, due in 7 days, and the
manager is notified; Priya, since mock interviews are student-visible,
gets a notification "Feedback from your mock interview"; audit "Activity
completed". The drawer now shows the next action with a link.

Failure: a required field empty → the field shows the error, nothing
saved. Network drop on Complete → the draft answers stay in the drawer
(local draft, same as the DSR panel) and Complete can be retried; the
server refuses a second completion with "Already completed" and the
drawer reloads.

### 3.3 Mark attendance / submit DSR
Exist; unchanged. Bulk changes on a register already show a count and a
confirmation.

### 3.4 My work
`/teaching/work` (Phase 16) — my activities across batches: Pending,
Overdue, Under review, Done this week. Each row opens the drawer.

## 4. Counsellor

### 4.1 Today's work
`/admissions/dashboard` (exists) — reordered as: New students (today),
Pending registrations (no batch yet), Follow-ups due, Overdue follow-ups,
Batch assignments waiting, Trainer assignments waiting (batches with no
trainer). One request.

### 4.2 Register a student (with duplicate detection, Phase 17)
"New student" → `/admissions/new` (exists). Step 1 name and contact. As
soon as email or phone is complete, the wizard asks the server "does
anyone match?" (a read) and, if so, shows "Possible existing student
found: Rahul Verma, GRS-S-00042, MERN-02, registered 3 Aug" with "Open
that record" and "This is a different person" (a reason is required and
recorded). Nothing is created until the last step's "Register".

Then, unchanged: course, batch, fee, first payment. After Register: the
student and enrolment exist, the batch seat is taken, the trainer is the
batch's trainer, the timeline starts with "Registered by Priya", audit,
welcome email queued; the counsellor lands on the student's record.

### 4.3 Schedule a follow-up
On the student record → "Plan a follow-up" → type Follow-up, due date,
channel → Create. Appears under "Follow-ups due" on the right day. When
done: Complete with the outcome (reached / no answer / callback) and,
if callback, the next follow-up is offered pre-filled.

## 5. Student

### 5.1 Dashboard
`/dashboard` (exists): progress, attendance, upcoming classes and
deadlines; new: "Your next actions" (student-visible activities that are
planned) and "Recent feedback".

### 5.2 My progress
`/my-progress` (exists) gains "Where I am / What I completed / What I
need to do / What I should improve" — the last from the improvements
field of visible activities.

### 5.3 My activities (Phase 10)
`/my-activities` — the timeline filtered to what is visible: Mock
interview (score and feedback), Assignment review, Project review,
Mentoring summary, Feedback. Never counselling, placement calls, parent
meetings, follow-ups or private notes. Opening one is a read; there is
nothing to write except "I have read this" on a warning.

## 6. Dashboards — loading contract (§67)

| Dashboard | Initial request | Then | Permissions | Cache | Refresh | Drill-down |
| --- | --- | --- | --- | --- | --- | --- |
| Admin `/admin/overview` | `GET /dashboards/admin/` | warnings strip `GET /warnings/` | report.view_any | 1 min | manual button; no polling | tile → filtered list |
| Manager `/manage` | `GET /dashboards/manager/` | `GET /warnings/` | performance.view_any | 1 min | manual | tile → list |
| Trainer `/teaching/today` | `GET /dashboards/trainer/` | per class on open: roster, DSR, activities | assignment | none | manual | class card → workspace |
| Counsellor `/admissions/dashboard` | `GET /dashboards/counsellor/` | `GET /warnings/` | student.create | 1 min | manual | tile → list |
| Student `/dashboard` | `GET /dashboard/student/` | — | own | none | manual | card → page |

Empty: every tile shows "0" with its label and stays a link. Error: the
tile grid is replaced by the error card with Retry. Back navigation:
lists keep their filters in the address bar so Back returns to the same
view. Opening a dashboard never issues a write; the query count of each
endpoint is asserted flat by `tests/test_performance.py`.

## 7. Student 360 — the chain the brief asks for (§103)

Trainer completes a mock interview → activity and answers saved → appears
in Student 360 (Activities, Timeline) → performance components update and
the overall score shows its provenance → risk recomputed, change recorded
→ next action created by the rule and linked as a child → manager notified
→ manager opens the student, sees the activity, approves or asks for
action → audit shows every step with who and when → the student sees the
visible fields → all of it stays after the form gets a version 2, after
the trainer leaves, after the batch ends. Each arrow is one automated test
in `tests/test_erp_journey.py` (Phase 25) and one e2e run.
