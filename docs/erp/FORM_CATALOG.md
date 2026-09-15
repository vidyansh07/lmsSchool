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

A response that fails validation is refused with the field errors in the
standard envelope (`details: {field: [...]}`); nothing is stored.

## Versioning and visibility

- Publishing computes `schema_hash`; two versions with the same hash are
  refused ("nothing changed").
- A historical record renders with the version it was written against,
  even after the definition moved on.
- Field-level `visible_to_student` is the only student filter; the rest of
  the record is staff-only.
