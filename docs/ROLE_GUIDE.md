# Role capability guide

This guide tells you what each role in the GRRAS LMS/ERP can do. It names the screens each
role sees, and it gives the exact number of capabilities each role holds. Every statement
in this guide comes from the code. The code files are named beside each claim, so you can
check the claim yourself. Where a feature does not exist, this guide says "Not built yet"
and names the file that was checked.

## How permission works here

The base role is the first part. There are six base roles: superadmin, admin, manager,
counsellor, trainer and student. The file `backend/apps/accounts/roles.py` holds these
roles in the `UserRole` class. A base role fixes a person's place on the ladder. The
ladder is strict: superadmin holds more than admin, admin more than manager, and manager
more than counsellor.

The capability is the second part. A capability is one named thing a person may do, for
example `fee.manage_any` or `dsr.review`. The `Capability` class in
`backend/apps/accounts/roles.py` holds 97 capabilities. The `ROLE_CAPABILITIES` table in
the same file maps each base role to its capabilities. A view asks for a capability; it
never asks for a role name.

The custom role is the third part. An administrator builds a custom role from rows in the
`authorization` app. `backend/apps/authorization/models.py` holds the `Role`, `Permission`
and `RolePermission` models. A custom role is always built from one base role, which the
`kind` field names. A custom role changes the set of permissions; it never changes the
kind. A superadmin kind is refused, as `backend/apps/authorization/services.py` shows.

The scope is the fourth part. The scope says how far a permission reaches. There are four
scopes in `PermissionScope`: `all` (every centre), `branch` (own centre), `assigned`
(assigned batches and courses) and `own` (own records). Each base role has a scope floor in
`backend/apps/authorization/scopes.py`. A superadmin and an administrator floor at `all`, a
manager and a counsellor at `branch`, a trainer at `assigned`, and a student at `own`. A
grant on a role can make the scope narrower; it can never make the scope wider.

### Who can administer whom

Three functions in `backend/apps/accounts/roles.py` answer this question. `capabilities_for`
gives the capability set for a role. `can_grant_role` lets you give a role only when you
already hold everything that role holds. `can_administer` lets you touch another person's
account only when that person holds strictly less than you.

Read the result as four plain statements. You can never administer your own account through
the staff screens. A superadmin can administer anybody, and this includes another
superadmin. An administrator can administer a manager, a counsellor, a trainer and a
student, but not another administrator. A manager can administer a counsellor, a trainer
and a student. Two people with the same role can never edit each other.

---

## Administrator

The administrator runs the institution. The administrator holds authority over people,
accounts, roles, policies and certificates.

### What the administrator can do

- Create a user account, update it, and activate or deactivate it.
- Change another person's role, within the limits of `can_grant_role`.
- Create a centre, change a centre, and move a person between centres.
- See every centre. `backend/apps/organisation/scoping.py` makes the administrator unbounded.
- Create a custom role, edit it, and assign permissions to it.
- Grant a named batch or a named course to a person through a `ScopeGrant`.
- Change the institution settings, the academic rules and the policy settings.
- Read the audit trail.
- Approve a course completion, and issue, reissue or revoke a certificate.
- See deleted records and restore them.
- See any person's sessions and revoke them.
- Build a form, publish it and unpublish it.
- Build the activity catalog and the automation rules.
- Create a message template and approve a template version.
- Do everything a manager can do. The administrator set contains the manager set.

### What the administrator cannot do

- Change platform-wide settings. The capability `platform.configure` stays with the superadmin.
- Destroy a record permanently. The capability `record.purge` stays with the superadmin.
- Lock or unlock a permission grant. The capability `permission.lock` stays with the superadmin.
- Administer another administrator or a superadmin. See `can_administer`.
- Build a custom role of the superadmin kind. `services.py` refuses this.

### The screens the administrator sees

The sidebar is `ADMIN_NAV` in `frontend/components/navigation.ts`.

- First group, with no heading: Staff activity, Institution overview, Analytics.
- Academic operations: Activities, Class reports, Batch review, Reviews due, Trainer requirements.
- Trainers: Trainers.
- Admissions: Admissions pipeline, Fees & collections, Enquiries, Registrations, Register a
  student, Batch planning, Transfers.
- Student records: Students, Data import.
- Batches and courses: Batches, Courses, Course catalogue.
- Results and reports: Reports, Completions, Certificates.
- Calendar: Calendar.
- Teaching: Today's class, Class schedule, Assignments, Weekly tests, Projects, Exams,
  Question bank.
- Institution: User accounts, Roles, Rules and policies, Form builder, Activity types,
  Automation, Message templates, Centres, Settings, Academic rules, Branding, Deleted records.
- My work: Announcements, Form inbox, Notifications, My profile.

### Capability count

The administrator holds **94** of the 97 capabilities.

### A note on the superadmin

The superadmin is a separate base role. The superadmin holds **97** capabilities, which is
every capability in the enum. The superadmin sidebar is `SUPERADMIN_NAV`. It shows the same
screens as the administrator sidebar, but it moves the "Institution" group to the top and
renames that group to "Platform and governance".

---

## Manager

The manager runs the academic operations from day to day. The manager looks after the
trainers, the classes, the batches and the course content.

### What the manager can do

- Create a trainer record and update it. This is the one thing a counsellor cannot do.
- Raise a trainer requirement and close it.
- Read the policy settings.
- Create a student, update a student, and change a student's fee status.
- See the fees, set the fees and the discounts, and record a payment.
- Create a course, edit it, publish it and assign authors to it.
- Manage the course categories.
- Create a batch, edit it, manage its schedule, and enrol students.
- Manage any class session, and correct the attendance on any class.
- See any class report, correct one, and approve, reject or return one.
- See the performance of any student or trainer, and record a performance review.
- Create and grade any assignment, assessment, project, exam and question.
- See any student's completion status.
- Announce to any audience, and moderate any discussion.
- Read the reports across the institution, export data and import data in bulk.
- See and manage the enquiries at the centre.
- Create, assign, complete, review and delete an activity.
- Send a notification, an email or a WhatsApp message, and read the delivery log.
- Fill in a form directly, or send a form to somebody.

### What the manager cannot do

- Create a user account, update one, or activate or deactivate one.
- Change another person's role.
- Create or change a centre, and move a person between centres.
- See every centre. The manager floors at the `branch` scope.
- Change the institution settings, the academic rules or the policy settings.
- Read the audit trail.
- Approve a course completion, and issue or revoke a certificate.
- See deleted records or restore them.
- Create or edit a custom role, and assign permissions to a role.
- Build a form, an activity type, an automation rule or a message template.
- See or revoke another person's sessions.

### The screens the manager sees

The sidebar is `MANAGER_NAV` in `frontend/components/navigation.ts`.

- First group, with no heading: Operations overview, Analytics.
- Academic operations: Activities, Batch review, Reviews due, Class reports, Trainer requirements.
- People: Trainers, Students, User accounts.
- Admissions and fees: Dashboard, Enquiries, Registrations, Register a student,
  Fees & collections, Batch planning, Transfers.
- Teaching and content: Today's class, Class schedule, Assignments, Weekly tests, Projects,
  Exams, Question bank, Course management, Batches, Course catalogue.
- Reports and tools: Reports, Data import, Rules and policies, Calendar.
- My work: Announcements, Discussions, Form inbox, Notifications, My profile.

The link "User accounts" needs the capability `user.view_any`, which the manager holds. The
screens behind it still refuse an account the manager may not administer.

### Capability count

The manager holds **69** of the 97 capabilities.

---

## Counsellor

The counsellor runs the admissions desk. The counsellor brings a student in, picks the
course, opens or chooses the batch, and takes the fees.

The owner decided on 14 September 2026 that the manager and the counsellor sit side by side.
The comment above `_COUNSELLOR_CAPABILITIES` in `backend/apps/accounts/roles.py` records this
decision as D-130. The sidebar is what differs most; the capability sets differ by four
entries only.

### What the counsellor can do

- Create an enquiry, change its stage, change its owner and set its follow-up date.
- Create a student, update a student, and change a student's fee status.
- See the fees, set the fees and the discounts, and record a payment.
- Enrol a student on a batch, and change an enrolment's status.
- Create a batch, edit it and manage its schedule.
- Fill in a form directly, or send a form to somebody.
- Create, assign, complete, review and delete an activity.
- Send a notification, an email or a WhatsApp message, and read the delivery log.
- Read the reports across the institution, export data and import data in bulk.
- Do the academic work a manager does: courses, class sessions, attendance, class reports,
  assignments, assessments, projects, exams and questions.

### What the counsellor cannot do

- Create a trainer record. The capability `trainer.create` stays with the manager.
- Update a trainer record. The capability `trainer.update_any` stays with the manager.
- Raise or close a trainer requirement. The capability `requirement.manage` stays with the manager.
- Read the policy settings. The capability `policy.view` stays with the manager.
- Everything an administrator alone holds. See the manager list above.

These four exclusions are the whole difference between the manager and the counsellor.
The test `tests/test_counsellor_rbac.py::test_a_counsellor_holds_everything_a_manager_does`
holds the difference to exactly these four.

### The enquiry pipeline

`backend/apps/enquiries/models.py` gives the stages. There are eight stages, in this order:
New, Contacted, Interested, Counselling booked, Demo class booked, Registered, Not interested,
Not eligible. Three of these stages close the pipeline: Registered, Not interested and
Not eligible.

An enquiry also records the channel, which is Online or Offline. The channel follows the
source unless somebody sets it by hand. The ten sources are Walk-in, Phone call, Website,
Google, Facebook / Instagram, LinkedIn, WhatsApp, Referral, College seminar and Other. Five
of these sources count as online: Website, Google, Facebook / Instagram, LinkedIn and WhatsApp.

The enquiry record also holds the lead quality, the lost reason, the next follow-up date, the
last contacted date, the owner, the centre and the UTM fields. The owner of an enquiry can
always work that enquiry, as `backend/apps/enquiries/access.py` shows.

### The fee ledger

`backend/apps/fees/models.py` gives the fee records. A `FeePlan` belongs to exactly one
enrolment. The plan holds the agreed amount, the discount amount, the discount reason, the
next due amount and the next due date.

A fee plan gets six instalments by default, with a gap of 30 days. The maximum is 36
instalments. The first payment must be at least 1000. The plan status and the instalment
status are always derived from the numbers; the system never stores them.

A `FeePayment` records the receipt number, the amount, the date paid, the method, the
reference and who recorded it. There are six payment methods: Cash, UPI, Card, Bank transfer,
Cheque and Other. A payment can be voided, and the record keeps the void date, the person who
voided it and the reason.

Warning: a person needs the capability `fee.manage_any` to set a fee, to record a payment or
to void one. `backend/apps/fees/views.py` declares this capability on each of those views. The
capability `fee.view_any` only lets a person read the fees.

### The counsellor dashboard

`_counsellor_dashboard` in `backend/apps/dashboards/views.py` builds this screen. It shows ten
figures and a warnings list. The figures are: students registered today, students registered in
the last seven days, enrolments awaiting confirmation, open online leads, open offline leads,
open leads in total, follow-ups due, follow-ups overdue, registered students with no batch, and
upcoming or active batches with no trainer.

Each figure travels with its own definition text. The dictionary
`COUNSELLOR_FIGURE_DEFINITIONS` in the same file holds that text. The screen shows the
definition under each number.

### The screens the counsellor sees

The sidebar is `COUNSELLOR_NAV` in `frontend/components/navigation.ts`.

- First group, with no heading: Dashboard, Enquiries, Fees & collections.
- Admissions: Registrations, Register a student, Batch planning, Transfers.
- Student care: Activities, Students, User accounts, Calendar.
- Academic support: Batch review, Class reports, Class schedule, Assignments, Weekly tests,
  Projects, Exams, Question bank, Course management, Batches, Course catalogue, Trainers.
- Reports and data: Analytics, Reports, Data import.
- Communication and my work: Announcements, Discussions, Form inbox, Notifications, My profile.

The "Trainers" link needs `trainer.view_any`, which the counsellor holds. The counsellor can
read a trainer record but cannot change it.

### Capability count

The counsellor holds **65** of the 97 capabilities.

---

## Trainer

The trainer teaches the batches that somebody assigns to them. The trainer writes the class
report after each class.

The trainer holds no global management capability. The trainer's reach comes from the
assignment instead. `ROLE_CAPABILITIES` gives the trainer the three base capabilities only,
and each `access.py` file then resolves the trainer's authority for each record.

### What the trainer can do

- See and update their own profile, and use the global search. These are the three base capabilities.
- See the batches they teach. `backend/apps/batches/access.py` filters the batches by trainer.
- See the roster of a batch they teach.
- Mark the attendance for a class on their own batch. `backend/apps/sessions/access.py`
  resolves this for each session.
- Start, write and submit the class report for a class they took.
- Read every class report on the batches they teach, and not only the reports they wrote.
- Create and grade an assignment, an assessment, a project or an exam on their own batch,
  or on a course they author.
- Edit a course that somebody assigned to them through a `CourseAssignment`.
- Announce to the batches they teach.
- See, create and complete the activities for their own students.
- Answer a trainer requirement. The trainer is its audience and needs no capability.
- Fill in a form that somebody sent them. Being the assignee is the authority.

### What the trainer cannot do

- See a batch, a course, a student or a report outside their assignment.
- Approve, reject or return a class report, including their own. The capability `dsr.review`
  belongs to the manager rung, and `can_review_dsr` also refuses a holder their own report.
- Correct the attendance on somebody else's class.
- See or manage any fee, any enquiry or any enrolment across the institution.
- Create a user, a student or a trainer record.
- Export data or import data in bulk.
- Read the reports across the institution.
- Assign, review or delete an activity.
- Send a notification, an email or a WhatsApp message.
- Read the policy settings or change any setting.

### The class report

`backend/apps/dsr/models.py` gives the class report. There is one report for each class
session. The report records the date, the start time, the end time, the module, the planned
topic and the actual topic.

The report also records five counts: the students on the roster, the present students, the
absent students, the students who joined online and the students who joined in person. The
first three counts come from the attendance register when the trainer starts the report. The
system copies these counts instead of computing them again, because a report is an account
of one point in time.

The report then asks for the teaching notes, the issues, the student concerns, the lessons
covered, the topic status and the homework. The topic status is `completed`, `in_progress` or
`skipped`. The institution can add its own questions through the `dsr-extra` form.

A report has six statuses: Draft, Submitted, Under review, Approved, Rejected and Revision
required. A trainer can change their own report while it is a draft or needs a revision. Once
the trainer submits the report, the report is the record a manager reads, and the trainer can
no longer change it.

A class has its report once the trainer submits it. A manager's approval is a courtesy, not a
step. Only the Approved status is final. A rejected report goes back to the trainer as a draft
to write again.

The report has a due time. The due time is the end of the class plus the hours in the
`notification.dsr_due_hours` policy. After the due time, the system tells the managers of that
centre once that the report is overdue.

### The trainer dashboard

`_trainer_dashboard` in `backend/apps/dashboards/views.py` builds this screen. It shows the
trainer's batches with the seat counts, and it leaves out the archived batches. It shows
today's classes and the classes of the next few days.

The screen also shows the number of distinct students on the trainer's active and pending
enrolments. It shows the courses behind those batches. Last, it shows two work counts: the
pending activities and the overdue activities.

### The screens the trainer sees

The sidebar is `TRAINER_NAV` in `frontend/components/navigation.ts`.

- First group, with no heading: Dashboard, Today's class, Work to review.
- Teaching: Class schedule, Assignments, Weekly tests, Projects, Exams, Question bank.
- Learners and content: Activities, Batches, Course management, Course catalogue,
  Class reports, Trainer requirements.
- Planning and communication: Calendar, Announcements, Discussions, Form inbox.
- My account: Notifications, My profile.

Each of these links reaches the trainer through the `scopedRoles` hint, not through a
capability. The screen behind the link still limits the trainer to their own batches.

### Capability count

The trainer holds **3** of the 97 capabilities. The three are `profile.view_own`,
`profile.update_own` and `search.global`.

---

## Placement officer

Warning: read this section before you look for a placement screen. There is no built-in
`placement` role in the GRRAS LMS/ERP today. The `UserRole` class in
`backend/apps/accounts/roles.py` holds six roles only: superadmin, admin, manager, counsellor,
trainer and student. No seventh role exists in that file, and no `placement` capability exists
in the `Capability` enum.

An administrator must compose this role from the permissions in the `authorization` app.
`backend/apps/authorization/models.py` holds the models this needs. The administrator creates a
`Role` row, picks a `kind` to build it from, and adds a `RolePermission` row for each
permission. The counsellor kind is the natural choice, because a placement officer works with
students, batches and activities.

This role is not part of the product's own seed. `backend/apps/authorization/sync.py` seeds six
system roles only, one for each base role. No migration creates a placement role. So on a fresh
install, and on the current staging host, this role does not exist.

One example of this role does exist, and it is a demonstration, not a product feature. The
showcase seed builds a custom role named "Placement coordinator". The definition is
`PLACEMENT_COORDINATOR` in `backend/apps/common/showcase/stages/s02_people.py`. The role has the
counsellor kind and 12 permissions: `student.view_any`, `student.create`, `student.update_any`,
`batch.view_any`, `enrolment.view_any`, `attendance.view_any` at the `assigned` scope,
`activity.view_any`, `activity.create`, `activity.complete`, `communication.send`,
`communication.view_any` and `report.view_any`. The seed also gives this role to one showcase
account, `placement@`, in `backend/apps/common/showcase/roster.py`.

The description on that role says what it covers and what it leaves out. It covers mock
interviews, placement calls and resume reviews. It shows students, batches and enrolments. It
does not show fees, trainers or academic delivery.

### The screens a composed role sees

`navFor` in `frontend/components/navigation.ts` handles this case. A role name that `navFor`
does not know falls through to the default branch, and the default branch returns
`SUPERADMIN_NAV`. The function then trims that tree with `isVisible`, which keeps only the
links whose capability the person holds. The comment above `navFor` names the placement officer
as the reason for this behaviour.

Warning: a custom role loses the `scopedRoles` fallback. `isVisible` returns a role fallback
only when `user.custom_role` is empty. So a custom role's permission list is the whole answer,
and removing a permission also removes its link.

### Capability count

Not built yet. There is no fixed number, because no placement role exists in
`backend/apps/accounts/roles.py`. The showcase example holds 12 permissions plus the 3 base
capabilities, which gives 15. That number describes one seeded demonstration, not the product.

---

## Student

The student studies at the institution. The student sees their own learning, their own records
and the public course catalogue.

### What the student can do

- See and update their own profile, and use the global search. These are the three base capabilities.
- See the courses they are enrolled on, with the progress on each one.
- Continue the last lesson they opened.
- See the batches they hold a place on, which includes the cancelled and completed ones.
- See their own fees, their own attendance, their own results and their own progress.
- Open an assignment, a project and an exam on their own enrolment, and submit work.
- Read the announcements that reach them, and post in the discussions on their own batch.
- Fill in a form that somebody sent them.
- See their own calendar and their own notifications.

### What the student cannot do

- See another student's records of any kind.
- See the roster of their own batch. `can_view_roster` in `backend/apps/batches/access.py`
  refuses a classmate.
- See any class report. `visible_dsrs` returns nothing to a student, and `can_read_dsrs`
  refuses the endpoint with a 403.
- See any enquiry, any fee other than their own, or any staff screen.
- Change their own fee status, their own attendance or their own results.

### The student dashboard

`_student_dashboard` in `backend/apps/dashboards/views.py` builds this screen. It shows the
student's courses with the progress percent, the completed lessons and the total lessons. It
shows the batches with the dates and the enrolment status.

The screen also shows the upcoming classes and a "continue learning" entry. The entry names the
last lesson the student opened. Last, it shows a short recent activity list of the student's
enrolments.

### The screens the student sees

The sidebar is `STUDENT_NAV_GROUPS` in `frontend/components/navigation.ts`.

- First group, with no heading: Dashboard, My learning.
- To do: My assignments, My projects, Exams, Form inbox.
- My progress: My results, My attendance, My progress, My fees, My batches.
- Explore and connect: Courses, Calendar, Announcements, Discussions.
- My account: Notifications, My profile.

### Capability count

The student holds **3** of the 97 capabilities. The three are `profile.view_own`,
`profile.update_own` and `search.global`.

---

## The manager permission on a trainer

An administrator can give a trainer more permissions than the trainer role holds. The
administrator does this with a custom role of the trainer kind. The trainer keeps the trainer
base role, because the `kind` field on the `Role` model fixes that. A custom role adjusts the
set of permissions; it never changes the kind.

Follow these steps to do this. First, create a `Role` row with `kind` set to `trainer`. Second,
add a `RolePermission` row for each extra permission, for example `dsr.review` or
`performance.view_any`. Third, assign that custom role to the trainer's account. The function
`check_custom_role_assignment` in `backend/apps/authorization/services.py` then checks the
assignment.

Warning: two rules limit what you can grant. You cannot grant a permission that you do not hold
yourself; `_check_grants` refuses this with a 403. You also cannot assign a role that holds more
than your own set.

The scope floor keeps the trainer inside their own batches. `SCOPE_FLOOR` in
`backend/apps/authorization/scopes.py` sets the trainer floor to `assigned`. The function
`effective_scope` takes the narrower of the floor and the configured scope. So every permission
on a trainer-kind role floors at `assigned`, whatever the role row says. A grant can make the
scope narrower, to `own`. A grant can never make the scope wider, to `branch` or `all`;
`_check_grants` refuses that with a 400.

`ScopeGrant` then decides which batches count as assigned. `backend/apps/authorization/models.py`
holds this model. Each row names one person and exactly one target, which is either a batch or a
course. A check constraint enforces the "exactly one" rule.

The function `assigned_batch_ids` in `scopes.py` builds the final list. The list holds the
batches the person teaches as the batch trainer. It also holds every batch named in a
`ScopeGrant` for that person. It also holds every batch of every course named in a `ScopeGrant`
for that person. So a trainer with extra permissions still reaches their own batches, plus the
batches an administrator named, and nothing else.

Each grant and each revoke is audited. `grant_scope` and `revoke_scope` in `services.py` write
a `SCOPE_GRANTED` or a `SCOPE_REVOKED` audit record.

---

## Features that are not built

Read this list before you plan work around these areas.

- **Placement tracking.** Not built yet. There is no placement app, no placement model and no
  placement capability. The checked files are `backend/apps/accounts/roles.py` and the app list
  under `backend/apps/`. Only a showcase custom role and a "Placement call" form template exist;
  see `backend/apps/common/showcase/stages/s02_people.py` and
  `backend/apps/forms/migrations/0002_seed_catalog.py`.
- **College records.** Not built yet as a record of its own. There is no college model and no
  partner institution model. `backend/apps/students/models.py` holds a free-text "college or
  employer" field, a roll number field and an institution kind with a `college` label. The SITP
  college spreadsheets load into those student fields; see `backend/apps/reporting/sitp.py`.
- **Vendor examination tracking.** Not built yet. There is no vendor model, no voucher model and
  no external certification model. The checked files are `backend/apps/exams/models.py` and
  `backend/apps/certificates/models.py`. The `Exam` model covers the institution's own
  examinations, and the `Certificate` model covers the institution's own certificates.

---

## Task table

The columns are the six roles in this guide. "Own batches only" means the person reaches the
record through an assignment, not through a global capability.

| Task | Administrator | Manager | Counsellor | Trainer | Placement officer | Student |
| --- | --- | --- | --- | --- | --- | --- |
| Create a user account | Yes | No | No | No | Not built yet | No |
| Change another person's role | Yes | No | No | No | Not built yet | No |
| Create or change a centre | Yes | No | No | No | Not built yet | No |
| See every centre | Yes | No | No | No | Not built yet | No |
| Create a custom role | Yes | No | No | No | Not built yet | No |
| Read the audit trail | Yes | No | No | No | Not built yet | No |
| See deleted records | Yes | No | No | No | Not built yet | No |
| Destroy a record permanently | No | No | No | No | Not built yet | No |
| Change platform-wide settings | No | No | No | No | Not built yet | No |
| Create a trainer record | Yes | Yes | No | No | Not built yet | No |
| Raise a trainer requirement | Yes | Yes | No | No | Not built yet | No |
| Read the policy settings | Yes | Yes | No | No | Not built yet | No |
| Create a student | Yes | Yes | Yes | No | Not built yet | No |
| Create an enquiry | Yes | Yes | Yes | No | Not built yet | No |
| Change an enquiry stage | Yes | Yes | Yes | No | Not built yet | No |
| See any student's fees | Yes | Yes | Yes | No | Not built yet | No |
| Record a fee payment | Yes | Yes | Yes | No | Not built yet | No |
| Void a fee payment | Yes | Yes | Yes | No | Not built yet | No |
| Enrol a student on a batch | Yes | Yes | Yes | No | Not built yet | No |
| Create a batch | Yes | Yes | Yes | No | Not built yet | No |
| Create a course | Yes | Yes | Yes | No | Not built yet | No |
| Edit a course | Yes | Yes | Yes | Own batches only | Not built yet | No |
| See a batch | Yes | Yes | Yes | Own batches only | Not built yet | Own batches only |
| See a batch roster | Yes | Yes | Yes | Own batches only | Not built yet | No |
| Mark the attendance | Yes | Yes | Yes | Own batches only | Not built yet | No |
| Correct the attendance | Yes | Yes | Yes | No | Not built yet | No |
| Write a class report | Yes | Yes | Yes | Own batches only | Not built yet | No |
| See a class report | Yes | Yes | Yes | Own batches only | Not built yet | No |
| Approve a class report | Yes | Yes | Yes | No | Not built yet | No |
| Create an assignment | Yes | Yes | Yes | Own batches only | Not built yet | No |
| Grade an assignment | Yes | Yes | Yes | Own batches only | Not built yet | No |
| Create an exam | Yes | Yes | Yes | Own batches only | Not built yet | No |
| Record a performance review | Yes | Yes | Yes | No | Not built yet | No |
| Approve a course completion | Yes | No | No | No | Not built yet | No |
| Issue a certificate | Yes | No | No | No | Not built yet | No |
| Announce to any audience | Yes | Yes | Yes | Own batches only | Not built yet | No |
| Send a notification or an email | Yes | Yes | Yes | No | Not built yet | No |
| Read the institution reports | Yes | Yes | Yes | No | Not built yet | No |
| Export data | Yes | Yes | Yes | No | Not built yet | No |
| Import data in bulk | Yes | Yes | Yes | No | Not built yet | No |
| Build a form | Yes | No | No | No | Not built yet | No |
| Fill in a form sent to them | Yes | Yes | Yes | Yes | Not built yet | Yes |
| Build an automation rule | Yes | No | No | No | Not built yet | No |
| Create a message template | Yes | No | No | No | Not built yet | No |
| Create an activity | Yes | Yes | Yes | Own batches only | Not built yet | No |
| Delete an activity | Yes | Yes | Yes | No | Not built yet | No |
| See their own records | Yes | Yes | Yes | Yes | Not built yet | Yes |
| Use the global search | Yes | Yes | Yes | Yes | Not built yet | Yes |
