# Communication catalog

Every event that talks to a person, on which channel, with which template,
to whom, whether it needs approval, and how delivery is tracked. Channels:
**in_app** (the `Notification` row, always), **email** (outbox → SMTP),
**whatsapp** (provider; only when configured and the template is approved).
Preferences: the four existing categories on `NotificationPreference` decide
email; WhatsApp needs an explicit opt-in flag (`whatsapp_opt_in`, new,
default false — regulation, not preference).

## Events

| Event (NotificationKind) | Channel(s) | Template key | Audience | Approval | Delivery record |
| --- | --- | --- | --- | --- | --- |
| student.created (new) | in_app, email | student_welcome | the student (credential link is separate and never queued, D-070) | none | Delivery per channel |
| batch.assigned (new) | in_app, email | batch_assigned | student; trainer | none | |
| activity.assigned (new) | in_app, email | activity_assigned | assignee | none | |
| activity.completed (new) | in_app | — | creator (if ≠ performer), reviewer (if review required) | none | |
| activity.visible (new) | in_app, email | activity_feedback | student, only when the type is student-visible | none | |
| activity.overdue (new) | in_app, email | activity_overdue | assignee, manager | none | |
| activity.review_requested (new) | in_app | — | reviewer | none | |
| activity.requires_action (new) | in_app | — | assignee | none | |
| assessment.result (existing result.published) | in_app, email | result_published | student | none | existing |
| assignment.overdue (new) | in_app, email | assignment_overdue | student, trainer | none | |
| project.overdue (new) | in_app, email | project_overdue | student, trainer | none | |
| attendance.warning (existing) | in_app, email, whatsapp | attendance_warning | student (+ guardian phone on WhatsApp when policy `communication.guardian_alerts` is on) | WhatsApp template approved by provider | |
| dsr.rejected (new) | in_app | — | trainer | none | |
| review.requested (new) | in_app, email | review_requested | reviewer | none | |
| review.shared (new) | in_app, email | review_shared | reviewee | none | |
| risk.changed (new) | in_app, email | risk_changed | manager, counsellor of the centre | none | |
| requirement.raised / replied (existing) | in_app, email | generic | see D-132 | none | existing |
| announcement (existing) | in_app, email | announcement | audience rule | none | existing |
| announcement (whatsapp) | whatsapp | announcement_wa | opted-in members of the audience | template.approve + provider approval | Delivery |
| export.ready / failed (existing) | in_app | — | requester | none | existing |
| warning.digest (existing) | in_app, email | digest | staff | none | existing |
| mfa.enrolled / disabled (new) | email | security_event | the user | none | always sent, ignores preferences |
| session.new_device (new) | email | security_event | the user | none | always sent |
| password.changed (existing flow, new notice) | email | security_event | the user | none | always sent |
| otp (new) | email | otp_code | the user | none | never logged; Delivery row stores no code |

## Templates

Code templates remain for `generic`, `assignment_due`, `result_published`,
`certificate_issued`, `attendance_warning` (D-051) and are the fallback.
A `MessageTemplate` row with a **published** version for the same key
overrides the code template for that channel.

| Key | Channel | Variables (allowlist) | Approval |
| --- | --- | --- | --- |
| student_welcome | email | student.name, institution.name, support.email, support.phone | none |
| batch_assigned | email | student.name, batch.code, batch.name, batch.start_date, trainer.name | none |
| activity_assigned | email | assignee.name, activity.title, activity.type, student.name, activity.due_at, link | none |
| activity_feedback | email | student.name, activity.type, activity.score, activity.summary, link | none |
| activity_overdue | email | assignee.name, activity.title, activity.days_overdue, link | none |
| assignment_overdue / project_overdue | email | student.name, item.title, item.due_at, link | none |
| review_requested / review_shared | email | reviewer.name, reviewee.name, review.type, link | none |
| risk_changed | email | student.name, risk.level, risk.triggered, link | none |
| attendance_warning | email, whatsapp | student.name, attendance.percent, threshold | WhatsApp: provider template id required |
| announcement_wa | whatsapp | title, body_excerpt, link | template.approve |
| security_event | email | user.name, event, when, ip, device | none; cannot be disabled |
| otp_code | email | code, expires_minutes | none; body_text only; never stored in Delivery.variables |

Rendering: `{{ path }}` substitution over the allowlist, HTML-escaped for
html bodies; unknown variables render empty and are reported by "Preview"
as a warning. No conditionals, loops or filters (ADR-12). Test send goes to
the signed-in user only.

## Delivery states and retries

`queued → processing → sent → delivered` (WhatsApp callback, or `sent` is
final for email) · `failed` (after 5 attempts with backoff 1, 5, 15, 60,
240 min; transient errors only) · `cancelled` (announcement cancelled before
send; user opted out; recipient deactivated). Permanent errors (bad address,
rejected template, 4xx from the provider) fail immediately.

The **Delivery log** screen lists deliveries with filters (channel, state,
recipient, date, template) and a retry button for `failed` rows
(`communication.send`, explicit confirmation).

## WhatsApp provider contract

```
class WhatsAppProvider(Protocol):
    name: str
    def send_template(self, *, to: str, template_id: str, language: str,
                      variables: list[str]) -> ProviderResult  # message_id or error, transient flag
    def parse_status_callback(self, payload: dict) -> list[StatusUpdate]
```

`NullProvider` (default): every send fails permanently with "No WhatsApp
provider configured"; the builder shows the channel as unavailable.
`MetaCloudProvider`: HTTPS with connect 5 s / read 10 s, credentials from
`WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`;
status webhook at `POST /api/v1/communication/whatsapp/webhook/` verified by
the token and HMAC signature.
