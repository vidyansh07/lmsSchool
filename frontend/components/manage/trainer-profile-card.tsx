'use client';

/**
 * Who a trainer is, on the trainer's own page — and the one place to change it.
 *
 * The review page answered "how is this trainer doing" but not "what do they
 * teach, are they taking work, did they ever accept the invitation", and the
 * only way to correct a title or a skill was the trainer editing it
 * themselves. A manager or administrator holding `trainer.update_any` edits the
 * profile here (the server also checks the authority ladder), sees whether the
 * account was ever set up, resends the invitation if not, and opens the
 * account record for anything else.
 */

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { Confirm } from '@/components/confirm';
import { ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Field } from '@/components/ui/field';
import { Input, Textarea } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { TagInput } from '@/components/ui/tag-input';
import { useUnsavedChanges } from '@/hooks/use-unsaved-changes';
import { ApiError, errorMessage, fieldErrors, unshownError } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import { fallback, NO_DATA } from '@/lib/format';
import { bulkTrainers } from '@/lib/bulk';
import { getTrainer, updateTrainer } from '@/lib/people';
import type { TrainerProfile } from '@/types/api';

const EDIT_FIELDS = ['professional_title', 'skills', 'years_of_experience', 'expertise', 'is_accepting_assignments'] as const;

function EditProfileDialog({
  profile,
  open,
  onClose,
  onSaved,
}: {
  profile: TrainerProfile;
  open: boolean;
  onClose: () => void;
  onSaved: (next: TrainerProfile) => void;
}) {
  const [title, setTitle] = useState(profile.professional_title);
  const [skills, setSkills] = useState<string[]>(profile.skills);
  const [years, setYears] = useState(
    profile.years_of_experience === null ? '' : String(profile.years_of_experience),
  );
  const [expertise, setExpertise] = useState(profile.expertise);
  const [accepting, setAccepting] = useState(profile.is_accepting_assignments);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const dirty =
    title !== profile.professional_title ||
    skills.join('|') !== profile.skills.join('|') ||
    years !== (profile.years_of_experience === null ? '' : String(profile.years_of_experience)) ||
    expertise !== profile.expertise ||
    accepting !== profile.is_accepting_assignments;
  const { isPrompting, guard, confirmDiscard, cancelDiscard } = useUnsavedChanges(open && dirty);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setErrors({});
    try {
      const next = await updateTrainer(profile.id, {
        professional_title: title.trim(),
        skills,
        years_of_experience: years.trim() === '' ? null : Number(years),
        expertise: expertise.trim(),
        is_accepting_assignments: accepting,
      });
      onSaved(next);
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setSaving(false);
    }
  }

  const formError = unshownError(errors, EDIT_FIELDS);

  return (
    <>
      <Dialog open={open} onOpenChange={(next) => (next || saving ? null : guard(onClose))}>
        <DialogContent size="lg" hideCloseButton className="max-h-[calc(100vh-2rem)] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Edit trainer profile</DialogTitle>
            <DialogDescription>
              What the trainer teaches and whether they take new batches. Their name, email and
              phone are on their account.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={(event) => void save(event)} className="space-y-4" noValidate>
            {formError ? <Alert variant="error">{formError}</Alert> : null}
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Professional title" htmlFor="tp-title" error={errors.professional_title}>
                <Input
                  id="tp-title"
                  value={title}
                  maxLength={150}
                  onChange={(event) => setTitle(event.target.value)}
                />
              </Field>
              <Field label="Years of experience" htmlFor="tp-years" error={errors.years_of_experience}>
                <Input
                  id="tp-years"
                  type="number"
                  min={0}
                  max={70}
                  step={1}
                  value={years}
                  onChange={(event) => setYears(event.target.value)}
                />
              </Field>
            </div>
            <Field
              label="Skills"
              htmlFor="tp-skills"
              error={errors.skills}
              hint="Type a skill and press Enter. Up to 30."
            >
              <TagInput
                id="tp-skills"
                value={skills}
                onChange={setSkills}
                placeholder="e.g. Linux"
                aria-describedby="tp-skills-hint"
              />
            </Field>
            <Field label="Expertise" htmlFor="tp-expertise" error={errors.expertise}>
              <Textarea
                id="tp-expertise"
                rows={3}
                value={expertise}
                onChange={(event) => setExpertise(event.target.value)}
              />
            </Field>
            <div className="flex items-center justify-between gap-3 rounded-control border border-line px-3 py-2">
              <div>
                <p id="tp-accepting-label" className="text-sm font-medium">
                  Accepting new batches
                </p>
                <p className="text-xs text-ink-muted">Off keeps them out of the batch trainer picker.</p>
              </div>
              <Switch
                checked={accepting}
                onCheckedChange={setAccepting}
                aria-labelledby="tp-accepting-label"
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" disabled={saving} onClick={() => guard(onClose)}>
                Cancel
              </Button>
              <Button type="submit" disabled={saving || !dirty}>
                {saving ? 'Saving…' : 'Save profile'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
      <Confirm
        open={isPrompting}
        title="Discard the changes to this profile?"
        description="They have not been saved."
        confirmLabel="Discard"
        cancelLabel="Keep editing"
        onConfirm={confirmDiscard}
        onCancel={cancelDiscard}
      />
    </>
  );
}

export function TrainerProfileCard({ trainerId }: { trainerId: string }) {
  const { can } = useAuth();
  const [profile, setProfile] = useState<TrainerProfile | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [editing, setEditing] = useState(false);
  const [notice, setNotice] = useState('');
  const [actionError, setActionError] = useState('');
  const [sending, setSending] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getTrainer(trainerId)
      .then((row) => {
        if (!cancelled) {
          setProfile(row);
          setError(null);
        }
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(
            cause instanceof ApiError
              ? cause
              : new ApiError(0, 'error', 'Could not load this trainer profile.', ''),
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [trainerId, attempt]);

  const retry = useCallback(() => setAttempt((value) => value + 1), []);

  async function resendInvitation() {
    if (!profile) return;
    setSending(true);
    setNotice('');
    setActionError('');
    try {
      // Through the trainers hub, so a manager who brought the trainer in may
      // send it too; the answer says whether the email actually went.
      const done = await bulkTrainers({ action: 'resend_invitation', ids: [profile.id] });
      const skipped = done.skipped[0]?.reason;
      if (done.done > 0) {
        setNotice(`A new invitation to set a password went to ${profile.user.email}.`);
      } else {
        setActionError(skipped ?? 'The invitation was not sent.');
      }
    } catch (cause) {
      setActionError(errorMessage(cause, 'The invitation could not be sent.'));
    } finally {
      setSending(false);
    }
  }

  if (error && !profile) {
    return (
      <ErrorState
        title="Could not load the trainer profile"
        message={error.message}
        requestId={error.requestId || undefined}
        onRetry={retry}
      />
    );
  }
  if (!profile) return <LoadingState label="Loading profile…" rows={3} />;

  const invitationPending = !profile.user.invitation_accepted;

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <CardTitle as="h2">Profile</CardTitle>
          <CardDescription>What they teach and whether they take new batches.</CardDescription>
        </div>
        <div className="flex flex-wrap gap-2">
          {can(Capability.userViewAny) ? (
            <Button asChild variant="outline" size="sm">
              <Link href={`/admin/users/${profile.user.id}`}>Account</Link>
            </Button>
          ) : null}
          {can(Capability.trainerUpdateAny) ? (
            <Button type="button" size="sm" onClick={() => setEditing(true)}>
              Edit profile
            </Button>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {notice ? (
          <Alert variant="success" role="status">
            {notice}
          </Alert>
        ) : null}
        {actionError ? <Alert variant="error">{actionError}</Alert> : null}
        <div className="flex flex-wrap gap-2">
          <Badge variant={profile.user.is_active ? 'success' : 'error'}>
            {profile.user.is_active ? 'Account active' : 'Account inactive'}
          </Badge>
          <Badge variant={invitationPending ? 'warning' : 'success'}>
            {invitationPending ? 'Invitation not accepted' : 'Signed up'}
          </Badge>
          <Badge variant={profile.is_accepting_assignments ? 'success' : 'neutral'}>
            {profile.is_accepting_assignments ? 'Accepting new batches' : 'Not accepting new batches'}
          </Badge>
        </div>
        {invitationPending &&
        profile.user.is_active &&
        (can(Capability.userUpdateAny) || can(Capability.trainerUpdateAny)) ? (
          <div className="flex flex-wrap items-center gap-3 rounded-control border border-line px-3 py-2 text-sm">
            <span className="text-ink-muted">
              They have not set a password yet, so they cannot sign in.
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={sending}
              onClick={() => void resendInvitation()}
            >
              {sending ? 'Sending…' : 'Resend invitation'}
            </Button>
          </div>
        ) : null}
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-ink-muted">Title</dt>
            <dd>{fallback(profile.professional_title, NO_DATA)}</dd>
          </div>
          <div>
            <dt className="text-ink-muted">Experience</dt>
            <dd>
              {profile.years_of_experience === null
                ? NO_DATA
                : `${profile.years_of_experience} year${profile.years_of_experience === 1 ? '' : 's'}`}
            </dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-ink-muted">Skills</dt>
            <dd className="mt-1 flex flex-wrap gap-1">
              {profile.skills.length === 0
                ? NO_DATA
                : profile.skills.map((skill) => <Badge key={skill}>{skill}</Badge>)}
            </dd>
          </div>
          {profile.expertise ? (
            <div className="sm:col-span-2">
              <dt className="text-ink-muted">Expertise</dt>
              <dd className="whitespace-pre-line">{profile.expertise}</dd>
            </div>
          ) : null}
        </dl>
      </CardContent>
      {editing ? (
        <EditProfileDialog
          profile={profile}
          open={editing}
          onClose={() => setEditing(false)}
          onSaved={(next) => {
            setProfile(next);
            setEditing(false);
            setNotice('Profile saved.');
          }}
        />
      ) : null}
    </Card>
  );
}
