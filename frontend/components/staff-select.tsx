'use client';

/**
 * Choose a member of staff by name — "Neha Gupta · Counsellor" — instead of
 * typing an account id. Lists the active staff the caller can see (the
 * accounts list's own centre scope): counsellors, managers and
 * administrators by default — who can own a lead — and trainers too where
 * work can be handed to them.
 */

import { useEffect, useState } from 'react';

import { Select } from '@/components/ui/input';
import { ROLE_LABEL, labelFor } from '@/lib/labels';
import { listUsers } from '@/lib/people';
import type { AdminUser } from '@/types/api';

const LEAD_OWNER_ROLES = ['counsellor', 'manager', 'admin'] as const;

export function useStaff(
  enabled = true,
  roles: readonly string[] = LEAD_OWNER_ROLES,
): { staff: AdminUser[]; failed: boolean } {
  const [staff, setStaff] = useState<AdminUser[]>([]);
  const [failed, setFailed] = useState(false);
  // The roles' contents, not the array's identity, decide a reload.
  const roleKey = roles.join(',');

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    Promise.all(
      roleKey.split(',').map((role) =>
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
  }, [enabled, roleKey]);

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
  roles,
  ariaLabel,
  className,
  current,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  emptyLabel?: string;
  /** Offer "nobody" as a real choice (its value is the string `none`). */
  allowNone?: boolean;
  noneLabel?: string;
  autoFocus?: boolean;
  roles?: readonly string[];
  /** When there is no visible label (a filter bar). */
  ariaLabel?: string;
  className?: string;
  /** Whoever holds it now, kept as a choice even if they are not listed
   *  (another centre, a role outside `roles`), so saving never drops them. */
  current?: { id: string; name: string } | null;
}) {
  const { staff, failed } = useStaff(true, roles);
  const keepCurrent = current && !staff.some((person) => person.id === current.id);
  return (
    <Select
      id={id}
      aria-label={ariaLabel}
      className={className}
      value={value}
      data-autofocus={autoFocus || undefined}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">{failed ? 'Could not load staff' : emptyLabel}</option>
      {allowNone ? <option value="none">{noneLabel}</option> : null}
      {keepCurrent ? <option value={current.id}>{current.name}</option> : null}
      {staff.map((person) => (
        <option key={person.id} value={person.id}>
          {person.full_name || person.email} · {labelFor(ROLE_LABEL, person.role)}
          {person.branch_code ? ` · ${person.branch_code}` : ''}
        </option>
      ))}
    </Select>
  );
}
