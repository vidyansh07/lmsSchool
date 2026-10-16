# Role workspaces and Classpro comparison

**Reviewed:** 16 October 2026
**Scope:** current Grras LMS frontend, role/capability contracts, and Classpro's public product and tour pages.

## Outcome

Grras already has deeper teaching, assessment, project, role-policy, recovery, audit, and analytics workflows than its old navigation exposed. The largest usability problem was information architecture: manager and counsellor received essentially the same long staff menu, fees had no staff workspace, and every successful login first visited an obsolete generic welcome page.

This pass makes the existing product legible by job:

- superadmins see platform governance near the top;
- admins see staff activity, institution health, operations, then configuration;
- managers start with academic operations, trainer and batch oversight;
- counsellors start with the admissions pipeline, enquiries, fees, and student care;
- trainers start with today's class and work waiting for review;
- students see learning, tasks, progress, fees, and communication as distinct groups;
- configured roles still use their explicit capability set; removed permissions do not reappear through role defaults;
- signed-out visitors no longer see private application navigation.

## What Classpro gets right

The public Classpro UI and product tour consistently organise the product around daily institute jobs rather than backend entities:

| Job | Classpro's public emphasis | Grras state after this pass |
| --- | --- | --- |
| Admissions | Central enquiry list, ownership, stages, next follow-up, conversion | First-class counsellor workspace, enquiry pipeline, registrations, activities, batch placement |
| Fees | Paid/pending/overdue visibility, instalments, receipts, reminders | Dedicated fee desk with current position, ageing, due-soon work, collections trend, and payment-ledger drill-down |
| Teaching | Lecture schedule, assignments, tests, attendance | Today's-class flow, schedule, registers, assignments, weekly tests, projects, exams, question bank, DSR |
| Learner progress | Scorecards, attendance and trend visibility | Student progress dashboard, results, attendance, course progress, feedback, certificates |
| Management | Consolidated operational and branch reporting | Admin and manager dashboards, centre-scoped analytics, activity/review queues, exports |
| Communication | Timely reminders and role-specific portals | Announcements, notification inbox, discussions, forms, templates and automation; external channels depend on provider setup |

Sources: [Classpro overview](https://www.classpro.in/), [enquiries tour](https://www.classpro.in/tour/enquiries), [fee management](https://www.classpro.in/tour), [reports](https://www.classpro.in/tour/reports), [student performance](https://www.classpro.in/tour/student_performance), and [student/parent app](https://www.classpro.in/tour/android).

## Problems found and disposition

| Finding | Impact | Disposition |
| --- | --- | --- |
| Manager and counsellor shared one oversized staff tree | Daily tasks were buried and both jobs looked identical | Fixed with separate, job-ranked trees |
| Login and `/` opened an obsolete phase-one welcome screen | Extra click and a misleading "features later" message | Fixed with direct, permission-safe workspace routing |
| Fee APIs and fee panels had no named staff destination | A core daily task was only discoverable through a student record | Fixed with `/fees` and role-appropriate navigation |
| Trainer DSR link required a global capability despite a scoped trainer page | Assigned trainers could miss their own report workflow | Fixed with the same assignment-scoped fallback used by teaching pages |
| Public shell exposed private link names | Visual clutter and unnecessary disclosure | Fixed; signed-out shell is brand plus sign-in only |
| Long sidebars could not be reduced by task group | High scanning cost on repeat visits | Fixed with accessible, role-persisted collapsible sections and icon rail |
| Custom roles could be sent to a removed built-in dashboard | First page could be a permission error | Fixed with capability-aware custom-role landing selection |

## Deliberately not faked

Classpro publicly advertises capabilities that need domain, provider, hardware, privacy, or reconciliation work—not a decorative page. They remain roadmap items until the supporting contract exists:

- parent/guardian accounts and multi-child switching;
- online payment gateway settlement and reconciliation;
- biometric-device ingestion and offline sync;
- automated SMS/WhatsApp delivery in production;
- expenses, payroll and tax invoicing;
- a user-configurable report builder and PDF export;
- native mobile applications.

Grras should not present these as working merely to match a competitor's feature list. The next highest-value product slice is parent/guardian access, followed by payment-provider reconciliation; both connect several existing workflows without duplicating the current UI.

## Role-page coverage

| Role | Default workspace | High-value pages exposed |
| --- | --- | --- |
| Superadmin | Institution overview | governance, roles/policies, centres, branding, audit, recovery, analytics |
| Admin | Institution overview | people, admissions, fees, batches, courses, reports, teaching, settings |
| Manager | Operations overview | batch/trainer health, reviews, DSR, requirements, analytics, fees |
| Counsellor | Admissions pipeline | enquiries, follow-ups, registration, fee desk, placement, transfers, student care |
| Trainer | Trainer dashboard | today's class, work queue, schedule, learning work, questions, DSR |
| Student | Student dashboard | learning continuation, tasks, results, attendance, progress, fees, calendar |

The navigation is an offer, not an authorization boundary. Every destination continues to depend on server-side capability and record-scope enforcement.
