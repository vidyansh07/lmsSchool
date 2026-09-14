'use client';

/**
 * "Which centre does this belong to?" — asked only of the people it applies to.
 *
 * A bounded account (a manager, a counsellor, an administrator at one centre)
 * never sees this field: the server forces their own centre onto anything
 * they create and ignores a submitted one. A superadmin is bounded to no
 * centre, so for them the server *requires* the answer, and refusing the
 * request with "Choose the centre" after the rest of the form was filled in
 * is a worse experience than asking up front. The field therefore renders
 * only for an unbounded caller, and the form treats it as required.
 */

import { useEffect, useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { Field } from '@/components/ui/field';
import { Select } from '@/components/ui/input';
import { listBranches } from '@/lib/organisation';
import type { Branch, User } from '@/types/api';

/** True for an account that sees every centre and must name one on create. */
export function isUnbounded(user: User | null | undefined): boolean {
  return Boolean(user && user.role === 'superadmin' && !user.branch_id);
}

export function useBranches(enabled: boolean): { branches: Branch[]; failed: boolean } {
  const [branches, setBranches] = useState<Branch[]>([]);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    listBranches({ page_size: 100 })
      .then((page) => {
        if (!cancelled) setBranches(page.results.filter((branch) => branch.is_active));
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled]);
  return { branches, failed };
}

export function BranchField({
  value,
  onChange,
  error,
  idPrefix = 'branch',
  label = 'Centre',
}: {
  value: string;
  onChange: (id: string) => void;
  error?: string;
  idPrefix?: string;
  label?: string;
}) {
  const { user } = useAuth();
  const unbounded = isUnbounded(user);
  const { branches, failed } = useBranches(unbounded);

  if (!unbounded) return null;

  return (
    <Field
      label={label}
      htmlFor={`${idPrefix}-select`}
      error={error ?? (failed ? 'Could not load the centres.' : undefined)}
      required
      hint="You belong to every centre, so say which one this record is for."
    >
      <Select
        id={`${idPrefix}-select`}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">Choose a centre</option>
        {branches.map((branch) => (
          <option key={branch.id} value={branch.id}>
            {branch.name} ({branch.code}){branch.city ? ` · ${branch.city}` : ''}
          </option>
        ))}
      </Select>
    </Field>
  );
}
