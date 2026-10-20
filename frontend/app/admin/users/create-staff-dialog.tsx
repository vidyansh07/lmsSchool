'use client';

/**
 * Adding an administrator, manager or counsellor — the one kind of account
 * that had no way in. Students are registered through Admissions and trainers
 * through Trainer onboarding, because each needs its own record created with
 * the account; this dialog says so and links there rather than offering roles
 * the server refuses (`AdminUserCreateSerializer.validate_role`).
 *
 * The new person receives an invitation and chooses their own password, so
 * nobody here ever handles it. Which roles are offered follows the caller's
 * own (you grant only what you hold); the server checks again regardless.
 */

import Link from 'next/link';
import { useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { Confirm } from '@/components/confirm';
import { BranchField } from '@/components/organisation/branch-field';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Field } from '@/components/ui/field';
import { Input, Select } from '@/components/ui/input';
import { useUnsavedChanges } from '@/hooks/use-unsaved-changes';
import { fieldErrors, unshownError } from '@/lib/api';
import { ROLE_LABEL, labelFor } from '@/lib/labels';
import { createUser } from '@/lib/people';
import type { AdminUser, UserRole } from '@/types/api';

type StaffRole = Exclude<UserRole, 'student' | 'trainer'>;

/** What each role may hand out, mirroring `can_grant_role` (containment). */
function grantableRoles(role: string | undefined): StaffRole[] {
  if (role === 'superadmin') return ['superadmin', 'admin', 'manager', 'counsellor'];
  if (role === 'admin') return ['admin', 'manager', 'counsellor'];
  return ['manager', 'counsellor'];
}

const SHOWN = ['email', 'first_name', 'last_name', 'phone', 'role', 'branch'] as const;

export function CreateStaffDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (user: AdminUser) => void;
}) {
  const { user: currentUser } = useAuth();
  const roles = grantableRoles(currentUser?.role);
  const [email, setEmail] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [phone, setPhone] = useState('');
  const [role, setRole] = useState<StaffRole | ''>('');
  const [branchId, setBranchId] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);
  const isDirty = Boolean(email || firstName || lastName || phone || role || branchId);
  const { isPrompting, guard, confirmDiscard, cancelDiscard } = useUnsavedChanges(
    open && isDirty,
  );

  function resetForm() {
    setEmail('');
    setFirstName('');
    setLastName('');
    setPhone('');
    setRole('');
    setBranchId('');
    setErrors({});
  }

  function requestClose() {
    if (isSaving) return;
    guard(() => {
      resetForm();
      onClose();
    });
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    const missing: Record<string, string> = {};
    if (!email.trim()) missing.email = 'Email is required.';
    if (!firstName.trim()) missing.first_name = 'First name is required.';
    if (!role) missing.role = 'Choose what they will do.';
    if (Object.keys(missing).length > 0 || !role) {
      setErrors(missing);
      return;
    }
    setIsSaving(true);
    setErrors({});
    try {
      const created = await createUser({
        email: email.trim(),
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        phone: phone.trim(),
        role,
        ...(branchId ? { branch: branchId } : {}),
      });
      resetForm();
      onCreated(created);
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSaving(false);
    }
  }

  const formError = unshownError(errors, SHOWN);

  return (
    <>
      <Dialog open={open} onOpenChange={(nextOpen) => (nextOpen ? null : requestClose())}>
        <DialogContent size="lg" hideCloseButton className="max-h-[calc(100vh-2rem)] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Add a staff account</DialogTitle>
            <DialogDescription>
              For an administrator, manager or counsellor. They receive an invitation and choose
              their own password.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            <Alert variant="info">
              Adding a trainer? Use{' '}
              <Link href="/manage/trainers" className="font-medium underline">
                Trainers → Add trainer
              </Link>
              . Registering a student? Use{' '}
              <Link href="/admissions/new" className="font-medium underline">
                Admissions
              </Link>
              . Both create the record that goes with the account.
            </Alert>
            {formError ? <Alert variant="error">{formError}</Alert> : null}

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Email" htmlFor="s-email" error={errors.email} required>
                <Input
                  id="s-email"
                  // The first thing to type, not the help link above it.
                  data-autofocus
                  type="email"
                  autoComplete="off"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </Field>
              <Field label="Phone" htmlFor="s-phone" error={errors.phone}>
                <Input
                  id="s-phone"
                  type="tel"
                  value={phone}
                  onChange={(event) => setPhone(event.target.value)}
                />
              </Field>
              <Field label="First name" htmlFor="s-first" error={errors.first_name} required>
                <Input
                  id="s-first"
                  value={firstName}
                  onChange={(event) => setFirstName(event.target.value)}
                />
              </Field>
              <Field label="Last name" htmlFor="s-last" error={errors.last_name}>
                <Input
                  id="s-last"
                  value={lastName}
                  onChange={(event) => setLastName(event.target.value)}
                />
              </Field>
              <Field label="Role" htmlFor="s-role" error={errors.role} required>
                <Select
                  id="s-role"
                  value={role}
                  onChange={(event) => setRole(event.target.value as StaffRole | '')}
                >
                  <option value="">Choose a role</option>
                  {roles.map((option) => (
                    <option key={option} value={option}>
                      {labelFor(ROLE_LABEL, option)}
                    </option>
                  ))}
                </Select>
              </Field>
              <BranchField
                value={branchId}
                onChange={setBranchId}
                error={errors.branch}
                idPrefix="s-branch"
              />
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={requestClose} disabled={isSaving}>
                Cancel
              </Button>
              <Button type="submit" disabled={isSaving}>
                {isSaving ? 'Adding…' : 'Add and send invitation'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
      <Confirm
        open={isPrompting}
        title="Discard this new account?"
        description="The details typed here have not been saved."
        confirmLabel="Discard"
        cancelLabel="Keep editing"
        onConfirm={confirmDiscard}
        onCancel={cancelDiscard}
      />
    </>
  );
}
