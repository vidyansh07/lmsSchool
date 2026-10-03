# Form catalog

Seeded `FormDefinition`s with their version-1 fields. Every seeded form is
published as version 1 by the seed migration; an administrator edits by
creating version 2. Field types are from the 17 in `DATA_MODEL.md` §4.
"Student" = the field is shown to the student when the activity is visible.
`performance_key = score` marks the field that becomes the activity score.

Validation rules are written as the `validation` JSON the builder stores.

## Activity forms

### mock-interview (entity: activity)
| Key | Label | Type | Required | Validation | Student | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| technical | Technical (0–10) | decimal | yes | min 0, max 10 | yes | |
| communication | Communication (0–10) | decimal | yes | min 0, max 10 | yes | feeds `next_action` condition `form.communication` |
| confidence | Confidence (0–10) | decimal | yes | min 0, max 10 | yes | |
| score | Overall (0–10) | decimal | yes | min 0, max 10 | yes | performance_key |
| outcome | Outcome | select | yes | ready / needs_practice / not_ready | yes | |
| strengths | Strengths | textarea | no | max 2000 | yes | |
| improvements | Improve | textarea | yes | max 2000 | yes | |
| notes | Private notes | textarea | no | max 4000 | no | |

### technical-interview
technical (0–10), problem_solving (0–10), score (performance_key), outcome, topics_covered (multiselect: from the course's module titles — `relation` to Module, optional), improvements, notes (private).

### hr-interview
communication, attitude, score (performance_key), outcome, notes (private).

### mentoring-note
| topic | text | yes | max 160 | yes |
| summary | textarea | yes | max 4000 | yes |
| action_items | textarea | no | | yes |
| follow_up_on | date | no | not in the past | no |

### counselling-note (counselling, career-guidance, attendance-counselling)
| reason | select | yes | attendance / fees / academic / personal / placement / other | no |
| summary | textarea | yes | max 4000 | no |
| commitments | textarea | no | | no |
| next_follow_up | date | no | not in the past | no |
| guardian_informed | boolean | no | | no |

### doubt-session
| topic | text | yes | | yes |
| lesson | relation(Lesson) | no | within the batch's course | yes |
| resolved | boolean | yes | | yes |
| notes | textarea | no | | yes |

### code-review
| repository_url | url | no | https only | yes |
| score | decimal | yes | 0–10 | yes (performance_key) |
| readability, correctness, structure | decimal | no | 0–10 | yes |
| comments | richtext | yes | max 8000, sanitised | yes |

### resume-review
| resume | file | yes | pdf/docx, max 5 MB (policy `file_upload.max_mb`) | yes |
| score | decimal | yes | 0–10 | yes (performance_key) |
| outcome | select | yes | ready / revise | yes |
| suggestions | textarea | yes | | yes |

### project-review
| project | relation(StudentProject) | yes | the student's own | yes |
| score | decimal | yes | 0–10 | yes (performance_key) |
| outcome | select | yes | approved / revise / rejected | yes |
| feedback | richtext | yes | | yes |

### placement-call
| company | text | no | | no |
| outcome | select | yes | ready / not_ready / placed / declined | no |
| package | decimal | no | ≥ 0 | no |
| notes | textarea | no | | no |

### feedback-note
| body | textarea | yes | max 5000 | configurable |
| visible_to_student | boolean | yes | default true | — |

### parent-meeting
| attendee | text | yes | | no |
| mode | select | yes | in_person / phone / video | no |
| summary | textarea | yes | | no |
| commitments | textarea | no | | no |

### warning-note
| reason | select | yes | attendance / conduct / academic / fees | yes |
| details | textarea | yes | | yes |
| acknowledged_by_student | boolean | no | | yes |

### follow-up-note
| channel | select | yes | phone / whatsapp / email / in_person | no |
| outcome | select | yes | reached / no_answer / callback / closed | no |
| summary | textarea | no | | no |
| next_follow_up | datetime | no | not in the past | no |

### communication-practice
| topic | text | yes | | yes |
| score | decimal | yes | 0–10 | yes (performance_key) |
| notes | textarea | no | | yes |

## Entity forms

### student-custom (entity: student)
Empty at seed; an administrator adds custom student fields here. Rendered
on the registration wizard (step "More details") and the Student 360
profile tab. Values live in a `FormResponse` attached to the
`StudentProfile`. Core fields (name, contact, course, batch, fee) stay typed
columns and are not part of this form.

### registration-extra (entity: registration)
Alias of `student-custom` with `required` fields enforced at registration
time; same definition, flagged so the wizard knows which fields block
submission.

## Enquiry forms (entity: enquiry) — Meritto-style, `forms.0004`

### enquiry
Lead capture a counsellor fills in for a walk-in or phone enquiry, with the
fields a Meritto lead form carries.

| Key | Label | Type | Required | Notes |
| --- | --- | --- | --- | --- |
| contact_heading | Contact details | heading | — | |
| full_name | Full name | text | yes | max 120 |
| mobile | Mobile number | phone | yes | |
| whatsapp_same | WhatsApp on the same number | boolean | no | |
| whatsapp_number | WhatsApp number | phone | no | shown when whatsapp_same is not true |
| email | Email | email | no | |
| location_heading | Location | heading | — | |
| state | State | select | yes | 28 states, 8 union territories, outside India |
| city | City | dependent_select | yes | parent `state`; main cities for the states GRRAS draws from, "Other" for every state |
| course_heading | Course interest | heading | — | |
| course | Course | select | yes | Python, Data Analytics, Data Science, Cyber Security, Full Stack, DevOps, AWS, UI/UX, Red Hat, Salesforce, Other |
| track | Track | dependent_select | no | parent `course` |
| preferred_centre | Preferred centre | select | yes | Jaipur / Pune / Online only |
| mode | Mode of study | radio | no | classroom / online / hybrid |
| batch_timing | Preferred batch timing | select | no | |
| background_heading | Background | heading | — | |
| qualification | Highest qualification | select | no | |
| passing_year | Year of passing | number | no | 1980–2035; shown unless working professional |
| company | Current company | text | no | shown for working professionals |
| source | How did they hear about GRRAS? | select | yes | walk-in, phone, website, Google, Facebook/Instagram, LinkedIn, WhatsApp, referral, college seminar, other |
| referred_by | Referred by | text | no | shown for referrals |
| utm_source, utm_medium, utm_campaign | UTM values | hidden | no | |
| remarks | Remarks | textarea | no | max 2000 |
| consent | Agrees to be contacted by phone, WhatsApp, SMS and email | consent | yes | |

### enquiry-follow-up
The lead status update recorded after each call.

| Key | Label | Type | Required | Shown when |
| --- | --- | --- | --- | --- |
| call_status | Call outcome | select | yes | always |
| lead_stage | Lead stage | select | yes | call_status = connected |
| lost_reason | Why not? | select | yes | lead_stage = not_interested (fees, competitor, timing, online preference, location, went silent, chose nothing, other) |
| competitor | Which institute? | text | no | lost_reason = competitor |
| demo_at | Demo class date and time | datetime | yes | lead_stage = demo_booked |
| next_follow_up | Next follow-up | datetime | yes | call_status in not_answered, busy, switched_off, call_back_later |
| lead_quality | Lead quality | rating (max 5) | no | call_status = connected |
| notes | Notes | textarea | no | always |

## Sending a form to someone (`FormAssignment`)

A published, non-activity form can be sent to one person to fill — by a
`form.assign` holder, or by an automation rule's `assign_form` action — or
filled in directly (an assignment to oneself, submitted at once). The version
is pinned when the form is sent and stays answerable after a newer version is
published. Statuses: pending → submitted, or pending → cancelled. The
assignee is notified when it is sent; the sender when it is submitted. Each
submission is a `FORM_SUBMITTED` automation occurrence.

## Validation rules (engine)

| Type | Stored as | Checks |
| --- | --- | --- |
| text, textarea, richtext | string | min_length, max_length, pattern; richtext is sanitised (allowlist tags) |
| number, decimal | number / string decimal | min, max, step; decimals kept as strings to avoid float drift |
| date, datetime | ISO string | not_past / not_future flags, min/max |
| boolean | bool | |
| select, radio | option value | value ∈ options |
| multiselect, checkbox | list of option values | subset of options, min_items, max_items |
| email, phone, url | string | format (E.164 for phone; https for url) |
| file, image | upload id | accept list, max_mb, scanned by the existing upload pipeline |
| relation | uuid | must resolve through the caller's `visible_*` for that model |
| time | `HH:MM` string | min/max |
| rating | integer | 1 to `validation.max` (default 5) |
| consent | bool | a required consent must be `true` |
| hidden | string | max 500; `validation.default` fills it when nothing is sent |
| heading | — | display only; a value is refused |
| dependent_select | option value | must be in `options.choices[<answer of options.parent>]`; the parent must be an earlier select, radio or dependent select |

**Conditional fields.** `show_if: {field, op, value}` (op `eq`, `ne`, `in`,
`not_in`, `filled`, `empty`) shows a field only while an earlier field's
answer matches, and only while that earlier field is itself shown. A hidden
field is never required, and a value sent for it is dropped.

**Uploads.** A `file`/`image` answer is the id of an upload made through
`POST /forms/uploads/`, checked against the field's `accept`/`max_mb` using
the stored metadata; only the uploader can attach it.

A response that fails validation is refused with the field errors in the
standard envelope (`details: {field: [...]}`); nothing is stored.

## Versioning and visibility

- Publishing computes `schema_hash`; two versions with the same hash are
  refused ("nothing changed").
- A historical record renders with the version it was written against,
  even after the definition moved on.
- Field-level `visible_to_student` is the only student filter; the rest of
  the record is staff-only.
