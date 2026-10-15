'use client';

import { useState } from 'react';

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
import { fieldErrors } from '@/lib/api';
import { createTrainer } from '@/lib/people';

export function CreateTrainerDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
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
    try {
      await createTrainer({
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
      onCreated();
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSaving(false);
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
