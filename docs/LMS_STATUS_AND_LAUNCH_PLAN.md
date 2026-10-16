# GRRAS LMS: Status and Launch Plan

**Date:** 15 October 2026 | **Prepared for:** Management | **Working pace:** 2 hours per day

## 1. Summary

The LMS is built and running on our AWS test server (staging). It covers the whole student journey, from enquiry to certificate. Security was tightened and deployed to staging on 14 October. On 15 October, trainer onboarding and user-role administration were hardened: the complete frontend suite passed 1,476 tests, and the directly affected backend and showcase suites passed 208 tests. One uninterrupted full backend rerun and a live browser walkthrough remain part of release verification.

What is left is **testing with real people, fixing what they find, and going live on our own web address**. The plan below needs **9 working days of 2 hours (18 hours)**. Waiting time for AWS approval and domain setup runs alongside the work.

## 2. What is done

| Area | What works today |
| --- | --- |
| Sign-in and roles | Secure login, password reset, email verification. Roles: administrator, manager, counsellor, trainer, student. Each person sees only what their role allows, per centre. |
| Admissions | Enquiries, student registration, enrolment, fee records with instalments and payment references, follow-up reminders, online/offline leads. |
| Teaching | Courses, batches, class schedule, attendance, a class report filled after each class, assignments, tests, projects, exams, certificates. |
| People administration | One trainer hub for managers and administrators, with search, skill and availability filters, export, workload context and trainer onboarding. Student and trainer accounts are created with their required profile rather than as incomplete generic users. |
| Role safety | Role changes are confirmed, reasoned and audited. Unsafe student/trainer conversions, self-role changes, removal of the last superadmin and changes that would orphan active teaching work are blocked. Existing sessions end after a role change. |
| Tracking | One full record per student, performance and risk warnings, dashboards, analytics, reports and exports. |
| Communication | Announcements, notifications, emails, forms, and an automation builder for repeated tasks. |
| Security and safety | Two-step login option, record of who did what, virus scan on every upload, restricted database access, daily backups with a tested restore. |
| Server | Live on AWS staging, healthy after the 14 October update. |

## 3. Not finished yet

- **Not yet tested by real users.** The automated tests pass, but nobody has walked through each role on the live server.
- **The wider UX backlog is not all implemented.** The audit records 28 findings. The trainer and role-administration risks are fixed; remaining filters, combined views, help text, empty states and role-specific refinements still need prioritisation.
- **Final regression evidence is incomplete.** The affected suites pass, but the latest full backend rerun stalled after 2,942 passing tests in a long database-bound showcase section. The connected browser automation bridge also did not start, so the live visual walkthrough remains open.
- **Email only reaches approved addresses.** AWS limits new accounts until we ask for full sending access.
- **No domain name.** Browsers show a security warning until we have one with a proper HTTPS certificate.
- **Backups stay on the same server.** We need a safe copy elsewhere.
- **Student "My activities" page is missing.**
- **Counsellor and manager have almost the same access.** Management should decide whether to separate them.
- **Automatic checks on GitHub are failing to start.** This looks like a setup fault, not a code fault, and needs a look.

<div style="page-break-after: always"></div>

## 4. Plan: 9 working days, 2 hours each

### Phase 1: Trial launch (Days 1 to 5)

Internal team only, on staging, with dummy data. No real students.

| Day | Work | Result |
| --- | --- | --- |
| 1 | Confirm admin sign-in works. Ask AWS for full email sending access. Create a test account for each role. Prepare a test checklist. | Trial ready to start |
| 2 | Test administrator and counsellor work: register a student, enrol, record fees, follow-ups, forms, and make one governed staff-role change. Write down every problem. | Problem list, part 1 |
| 3 | Test manager and trainer work: add a trainer, filter the trainer hub, change assignment availability, then test batches, class, attendance, class report, assignments and tests. Check the student view. | Problem list, part 2 |
| 4 | Fix the most important problems. Decide the counsellor/manager split. Add the student "My activities" page if time allows. Bring the tested work into the main code line. | Fixes done |
| 5 | Re-test the fixes. Practise restoring a backup. Set up a safe off-server backup copy. | **Trial sign-off** |

### Phase 2: Production launch (Days 6 to 9)

| Day | Work | Result |
| --- | --- | --- |
| 6 | Choose and register a domain. Point it at the server. Install a trusted HTTPS certificate. | No browser warning |
| 7 | Build the live setup with its own passwords and database. Send email from our domain. Turn on scheduled backups. | Live system ready |
| 8 | Enter real centres, courses and staff accounts. Do a final check of every role on the live system. | Ready for go-live |
| 9 | **Go live.** Watch closely, keep a rollback ready, hand over notes and logins. | **Production launch** |

## 5. Risks and waits

- **AWS email approval** can take 1 to 2 days. We ask on Day 1 so it is ready by Day 6.
- **Domain and HTTPS** can take a few hours to start working after setup. Day 6 allows for it.
- **Trial problems** could be larger than expected. Each extra 2-hour day is added to the plan. Items that do not block launch move to after launch.
- **Student data** goes in only on Day 8, after the trial and the backup test.

## 6. Decisions needed from management

1. **Counsellor and manager access:** keep them overlapping, or give each its own job (recommended).
2. **Domain name** for the live site.
3. **Who joins the trial:** the people who test each role, 1 to 2 per role.
4. **Go-live date** once Day 5 sign-off is done.
