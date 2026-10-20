'use client';

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
import { Input } from '@/components/ui/input';
import { TagInput } from '@/components/ui/tag-input';
import { useUnsavedChanges } from '@/hooks/use-unsaved-changes';
import { errorMessage, fieldErrors } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import { ROLE_LABEL, labelFor } from '@/lib/labels';
import { createTrainer, ensureTeachingProfile, listUsers } from '@/lib/people';
import type { AdminUser, TrainerProfile } from '@/types/api';

export function CreateTrainerDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  /** The new trainer; `undefined` when an existing account was set up to teach. */
  onCreated: (created?: TrainerProfile) => void;
}) {
  const [email, setEmail] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [phone, setPhone] = useState('');
  const [title, setTitle] = useState('');
  const [skills, setSkills] = useState<string[]>([]);
  const [years, setYears] = useState('');
  const [branchId, setBranchId] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);
  const { can } = useAuth();
  // When the address already has an account: who it is, so the next step is
  // obvious — open their trainer profile, let a manager teach, or reactivate —
  // instead of a bare "already exists".
  const [existing, setExisting] = useState<AdminUser | null>(null);
  const [existingError, setExistingError] = useState('');
  const [isAttaching, setIsAttaching] = useState(false);
  const isDirty = Boolean(
    email || firstName || lastName || phone || title || skills.length || years || branchId,
  );
  const { isPrompting, guard, confirmDiscard, cancelDiscard } = useUnsavedChanges(
    open && isDirty,
  );

  function resetForm() {
    setEmail('');
    setFirstName('');
    setLastName('');
    setPhone('');
    setTitle('');
    setSkills([]);
    setYears('');
    setBranchId('');
    setErrors({});
    setExisting(null);
    setExistingError('');
  }

  function closeAndReset() {
    resetForm();
    onClose();
  }

  function requestClose() {
    if (isSaving) return;
    guard(closeAndReset);
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setIsSaving(true);
    setErrors({});
    setExisting(null);
    setExistingError('');
    try {
      const created = await createTrainer({
        email: email.trim(),
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        phone: phone.trim(),
        profile: {
          professional_title: title.trim(),
          skills,
          years_of_experience: years === '' ? null : Number(years),
        },
        ...(branchId ? { branch: branchId } : {}),
      });
      resetForm();
      onCreated(created);
    } catch (cause) {
      const fields = fieldErrors(cause);
      setErrors(fields);
      if (fields.email && /already exists/i.test(fields.email) && can(Capability.userViewAny)) {
        void findExisting(email.trim());
      }
    } finally {
      setIsSaving(false);
    }
  }

  async function findExisting(address: string) {
    try {
      const page = await listUsers({ search: address, page_size: 5 });
      setExisting(
        page.results.find((row) => row.email.toLowerCase() === address.toLowerCase()) ?? null,
      );
    } catch {
      // The plain "already exists" message still stands on its own.
    }
  }

  async function letManagerTeach(account: AdminUser) {
    setIsAttaching(true);
    setExistingError('');
    try {
      await ensureTeachingProfile(account.id);
      resetForm();
      onCreated();
    } catch (cause) {
      setExistingError(errorMessage(cause, 'Could not set them up to teach.'));
    } finally {
      setIsAttaching(false);
    }
  }

  return (
    <>
      <Dialog open={open} onOpenChange={(nextOpen) => (nextOpen ? null : requestClose())}>
        <DialogContent
          size="lg"
          hideCloseButton
          className="max-h-[calc(100vh-2rem)] overflow-y-auto"
        >
          <DialogHeader>
            <DialogTitle>Add a trainer</DialogTitle>
            <DialogDescription>
              Creates the account and trainer profile together. The trainer receives an invitation
              and chooses their own password.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}
            {existing ? (
              <Alert variant="info" className="space-y-2">
                <p>
                  <strong>{existing.full_name || existing.email}</strong> already has an account
                  ({labelFor(ROLE_LABEL, existing.role)}
                  {existing.is_active ? '' : ', inactive'}).{' '}
                  {existing.role === 'trainer'
                    ? 'They are already a trainer.'
                    : existing.role === 'manager'
                      ? 'A manager can teach without changing role.'
                      : 'One account cannot be two people; use a different address, or ask an administrator.'}
                  {existing.is_active ? '' : ' Reactivate the account before giving them classes.'}
                </p>
                {existingError ? <p className="text-danger">{existingError}</p> : null}
                <div className="flex flex-wrap gap-2">
                  {existing.profile_type === 'trainer' && existing.profile_id ? (
                    <Button asChild size="sm" variant="outline">
                      <Link href={`/manage/trainers/${existing.profile_id}`}>Open trainer profile</Link>
                    </Button>
                  ) : null}
                  {existing.role === 'manager' &&
                  existing.profile_type !== 'trainer' &&
                  existing.is_active ? (
                    <Button
                      type="button"
                      size="sm"
                      disabled={isAttaching}
                      onClick={() => void letManagerTeach(existing)}
                    >
                      {isAttaching ? 'Setting up…' : 'Let this manager teach'}
                    </Button>
                  ) : null}
                  <Button asChild size="sm" variant="ghost">
                    <Link href={`/admin/users/${existing.id}`}>Open account</Link>
                  </Button>
                </div>
              </Alert>
            ) : null}

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Email" htmlFor="t-email" error={errors.email} required>
                <Input
                  id="t-email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </Field>
              <Field label="Phone" htmlFor="t-phone" error={errors.phone}>
                <Input
                  id="t-phone"
                  type="tel"
                  autoComplete="tel"
                  value={phone}
                  onChange={(event) => setPhone(event.target.value)}
                />
              </Field>
              <Field label="First name" htmlFor="t-first" error={errors.first_name} required>
                <Input
                  id="t-first"
                  autoComplete="given-name"
                  value={firstName}
                  onChange={(event) => setFirstName(event.target.value)}
                />
              </Field>
              <Field label="Last name" htmlFor="t-last" error={errors.last_name}>
                <Input
                  id="t-last"
                  autoComplete="family-name"
                  value={lastName}
                  onChange={(event) => setLastName(event.target.value)}
                />
              </Field>
              <Field
                label="Professional title"
                htmlFor="t-title"
                error={errors.professional_title}
              >
                <Input
                  id="t-title"
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                />
              </Field>
              <Field
                label="Skills"
                htmlFor="t-skills"
                error={errors.skills}
                hint="Type a skill and press Enter, e.g. Linux"
              >
                <TagInput
                  id="t-skills"
                  value={skills}
                  onChange={setSkills}
                  aria-describedby="t-skills-hint"
                />
              </Field>
              <Field
                label="Years of experience"
                htmlFor="t-years"
                error={errors.years_of_experience}
              >
                <Input
                  id="t-years"
                  type="number"
                  inputMode="numeric"
                  min={0}
                  max={70}
                  value={years}
                  onChange={(event) => setYears(event.target.value)}
                />
              </Field>
              <BranchField
                idPrefix="t-branch"
                value={branchId}
                onChange={setBranchId}
                error={errors.branch}
              />
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={requestClose} disabled={isSaving}>
                Cancel
              </Button>
              <Button type="submit" disabled={isSaving}>
                {isSaving ? 'Creating…' : 'Create trainer'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
      <Confirm
        open={isPrompting}
        title="Discard this trainer?"
        description="The details entered in this form have not been saved."
        confirmLabel="Discard changes"
        cancelLabel="Keep editing"
        isConfirming={false}
        onConfirm={confirmDiscard}
        onCancel={cancelDiscard}
      />
    </>
  );
}
