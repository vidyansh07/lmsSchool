/**
 * Who an activity is about, for a list cell. Kept out of `lib/work.ts` so
 * screens that mock the activity API in tests still get the real helper.
 */

import type { Activity } from "@/types/api";

/** Who an activity is about, for a list cell: the student's name and ID, or
 *  — for an activity about an enquiry — the enquiry's name and mobile. */
export function activitySubject(row: Pick<Activity, "student" | "enquiry">): {
  name: string;
  detail: string;
  enquiryId: string | null;
} {
  if (row.student) {
    return { name: row.student.name, detail: row.student.student_id, enquiryId: null };
  }
  if (row.enquiry) {
    return { name: row.enquiry.name, detail: `Enquiry · ${row.enquiry.mobile}`, enquiryId: row.enquiry.id };
  }
  return { name: "—", detail: "", enquiryId: null };
}
