"use client";

/**
 * A list of form assignments — forms sent to someone to fill. Used by the
 * Forms inbox (`/forms`) and by a form's own Responses card in the builder.
 * Each row links to `/forms/<id>`, where the form is filled in or read.
 */

import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Table, TableWrapper, Td, Th } from "@/components/ui/table";
import { formatDateTime } from "@/lib/format";
import {
  FORM_ASSIGNMENT_STATUS_LABEL,
  FORM_ASSIGNMENT_STATUS_VARIANT,
} from "@/lib/labels";
import type { FormAssignment } from "@/types/api";

/** Who a form came from: the sender, or "Automation" when a rule sent it. */
export function assignmentSender(row: FormAssignment): string {
  if (row.from_automation) return "Automation";
  if (!row.requested_by) return "—";
  if (row.requested_by.id === row.assigned_to.id) return "Filled in directly";
  return row.requested_by.name;
}

export function FormAssignmentsTable({
  rows,
  showForm = true,
  showAssignee = false,
}: {
  rows: FormAssignment[];
  showForm?: boolean;
  /** Show who the form went to — for lists of forms other people fill. */
  showAssignee?: boolean;
}) {
  return (
    <TableWrapper>
      <Table>
        <thead>
          <tr>
            <Th>Form</Th>
            {showAssignee ? <Th>Filled by</Th> : null}
            <Th>From</Th>
            <Th>Student</Th>
            <Th>Due</Th>
            <Th>Status</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="hover:bg-sunken/40">
              <Td>
                <Link
                  href={`/forms/${row.id}`}
                  className="font-medium text-ink underline-offset-2 hover:underline"
                >
                  {row.title || row.form.name}
                </Link>
                {showForm && row.title && row.title !== row.form.name ? (
                  <span className="block text-2xs text-ink-faint">{row.form.name}</span>
                ) : null}
              </Td>
              {showAssignee ? <Td>{row.assigned_to.name}</Td> : null}
              <Td>{assignmentSender(row)}</Td>
              <Td>{row.student?.name ?? "—"}</Td>
              <Td className="whitespace-nowrap tabular-nums">
                {row.due_at ? formatDateTime(row.due_at) : "—"}
                {row.is_overdue ? (
                  <Badge variant="error" className="ml-2">
                    Overdue
                  </Badge>
                ) : null}
              </Td>
              <Td>
                <Badge variant={FORM_ASSIGNMENT_STATUS_VARIANT[row.status]}>
                  {FORM_ASSIGNMENT_STATUS_LABEL[row.status]}
                </Badge>
                {row.submitted_at ? (
                  <span className="mt-0.5 block text-2xs tabular-nums text-ink-faint">
                    {formatDateTime(row.submitted_at)}
                  </span>
                ) : null}
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </TableWrapper>
  );
}
