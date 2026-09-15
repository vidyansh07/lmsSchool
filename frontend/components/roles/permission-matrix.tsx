"use client";

/**
 * Every role by every permission, in the five states the server names:
 * granted, inherited (from the kind's seeded set), locked, not granted,
 * system. Read-only here; the builder is where a role changes. Glyph plus
 * text, never colour alone.
 */

import { useMemo, useState } from "react";
import { Check, CircleCheck, Lock, Minus, ShieldCheck } from "lucide-react";

import { ErrorState, LoadingState } from "@/components/states";
import { Field } from "@/components/ui/field";
import { Select } from "@/components/ui/input";
import { Table, TableWrapper, Td, Th } from "@/components/ui/table";
import { useApi } from "@/hooks/use-api";
import { MATRIX_CELL_LABEL, PERMISSION_CATEGORY_LABEL } from "@/lib/labels";
import type { MatrixCell, PermissionCategory, RoleMatrix } from "@/types/api";

const ICON: Record<
  MatrixCell,
  React.ComponentType<React.SVGProps<SVGSVGElement>>
> = {
  explicit: CircleCheck,
  inherited: Check,
  locked: Lock,
  denied: Minus,
  system: ShieldCheck,
};

const TONE: Record<MatrixCell, string> = {
  explicit: "text-green",
  inherited: "text-foreground",
  locked: "text-amber",
  denied: "text-muted-foreground",
  system: "text-muted-foreground",
};

export function PermissionMatrix() {
  const { data, error, isLoading, reload } = useApi<RoleMatrix>(
    "/api/v1/roles/matrix/",
  );
  const [category, setCategory] = useState<PermissionCategory | "">("");

  const permissions = useMemo(
    () =>
      (data?.permissions ?? []).filter(
        (row) => !category || row.category === category,
      ),
    [data, category],
  );

  if (isLoading) return <LoadingState label="Loading the matrix…" rows={6} />;
  if (error || !data) {
    return (
      <ErrorState
        title="Could not load the matrix"
        message={error?.message ?? "No data."}
        requestId={error?.requestId || undefined}
        onRetry={reload}
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Category" htmlFor="matrix-category" className="min-w-56">
          <Select
            id="matrix-category"
            value={category}
            onChange={(event) =>
              setCategory(event.target.value as PermissionCategory | "")
            }
          >
            <option value="">Every category</option>
            {(
              Object.keys(PERMISSION_CATEGORY_LABEL) as PermissionCategory[]
            ).map((value) => (
              <option key={value} value={value}>
                {PERMISSION_CATEGORY_LABEL[value]}
              </option>
            ))}
          </Select>
        </Field>
        <ul
          className="flex flex-wrap gap-3 text-xs text-muted-foreground"
          aria-label="Legend"
        >
          {(Object.keys(MATRIX_CELL_LABEL) as MatrixCell[]).map((cell) => {
            const Icon = ICON[cell];
            return (
              <li key={cell} className="flex items-center gap-1">
                <Icon className={`size-3.5 ${TONE[cell]}`} aria-hidden="true" />
                {MATRIX_CELL_LABEL[cell]}
              </li>
            );
          })}
        </ul>
      </div>
      <TableWrapper className="max-h-[70vh] overflow-auto">
        <Table>
          <thead>
            <tr>
              <Th className="sticky left-0 top-0 z-30 bg-muted">Permission</Th>
              {data.roles.map((role) => (
                <Th
                  key={role.slug}
                  className="sticky top-0 z-20 bg-muted text-center"
                >
                  {role.name}
                </Th>
              ))}
            </tr>
          </thead>
          <tbody>
            {permissions.map((permission) => (
              <tr key={permission.code}>
                <Td className="sticky left-0 z-10 bg-surface">
                  <span className="block text-sm">
                    {permission.description || permission.code}
                  </span>
                  <span className="font-mono text-xs text-muted-foreground">
                    {permission.code}
                  </span>
                </Td>
                {data.roles.map((role) => {
                  const cell =
                    data.cells[role.slug]?.[permission.code] ?? "denied";
                  const Icon = ICON[cell];
                  return (
                    <Td key={role.slug} className="text-center">
                      <span
                        className={`inline-flex items-center gap-1 ${TONE[cell]}`}
                      >
                        <Icon className="size-4" aria-hidden="true" />
                        <span className="sr-only">
                          {MATRIX_CELL_LABEL[cell]}
                        </span>
                      </span>
                    </Td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </Table>
      </TableWrapper>
    </div>
  );
}
