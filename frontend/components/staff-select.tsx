'use client';

/**
 * Choose a member of staff by name — "Neha Gupta · Counsellor" — instead of
 * typing an account id. Lists the active counsellors, managers and
 * administrators the caller can see (the accounts list's own centre scope),
 * which is who can own a lead or be handed work.
 */

import { useEffect, useState } from 'react';

import { Select } from '@/components/ui/input';
import { ROLE_LABEL, labelFor } from '@/lib/labels';
import { listUsers } from '@/lib/people';
import type { AdminUser } from '@/types/api';

const STAFF_ROLES = ['counsellor', 'manager', 'admin'] as const;

export function useStaff(enabled = true): { staff: AdminUser[]; failed: boolean } {
  const [staff, setStaff] = useState<AdminUser[]>([]);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    Promise.all(
      STAFF_ROLES.map((role) =>
        listUsers(
          { role, is_active: 'true', page_size: 100, ordering: 'first_name' },
          controller.signal,
        ),
      ),
    )
      .then((pages) => {
        setStaff(pages.flatMap((page) => page.results));
        setFailed(false);
      })
      .catch((cause: unknown) => {
        if ((cause as { name?: string })?.name !== 'AbortError') setFailed(true);
      });
    return () => controller.abort();
  }, [enabled]);

  return { staff, failed };
}

export function StaffSelect({
  id,
  value,
  onChange,
  emptyLabel = 'Choose a person',
  allowNone = false,
  noneLabel = 'Nobody (unassigned)',
  autoFocus = false,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  emptyLabel?: string;
  /** Offer "nobody" as a real choice (its value is the string `none`). */
  allowNone?: boolean;
  noneLabel?: string;
  autoFocus?: boolean;
}) {
  const { staff, failed } = useStaff();
  return (
    <Select
      id={id}
      value={value}
      data-autofocus={autoFocus || undefined}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">{failed ? 'Could not load staff' : emptyLabel}</option>
      {allowNone ? <option value="none">{noneLabel}</option> : null}
      {staff.map((person) => (
        <option key={person.id} value={person.id}>
          {person.full_name || person.email} · {labelFor(ROLE_LABEL, person.role)}
          {person.branch_code ? ` · ${person.branch_code}` : ''}
        </option>
      ))}
    </Select>
  );
}
