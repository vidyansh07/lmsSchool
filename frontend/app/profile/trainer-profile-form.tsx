'use client';

import { useEffect, useState } from 'react';

import { ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Textarea } from '@/components/ui/input';
import { ApiError, fieldErrors } from '@/lib/api';
import { getOwnTrainerProfile, updateOwnTrainerProfile } from '@/lib/people';
import type { TrainerProfile } from '@/types/api';

const LINK_KEYS = ['linkedin', 'github', 'website'] as const;

export function TrainerProfileForm() {
  const [profile, setProfile] = useState<TrainerProfile | null>(null);
  const [title, setTitle] = useState('');
  const [bio, setBio] = useState('');
  const [skills, setSkills] = useState('');
  const [expertise, setExpertise] = useState('');
  const [qualifications, setQualifications] = useState('');
  const [years, setYears] = useState('');
  const [links, setLinks] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getOwnTrainerProfile()
      .then((loaded) => {
        if (cancelled) return;
        setProfile(loaded);
        setTitle(loaded.professional_title);
        setBio(loaded.bio);
        setSkills(loaded.skills.join(', '));
        setExpertise(loaded.expertise);
        setQualifications(loaded.qualifications);
        setYears(loaded.years_of_experience === null ? '' : String(loaded.years_of_experience));
        setLinks(loaded.professional_links ?? {});
      })
      .catch((cause: unknown) => {
        if (!cancelled) setLoadError(cause instanceof ApiError ? cause : null);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setIsSaving(true);
    setErrors({});
    setSaved(false);
    try {
      const cleanedLinks = Object.fromEntries(
        Object.entries(links).filter(([, value]) => value.trim() !== ''),
      );
      setProfile(
        await updateOwnTrainerProfile({
          professional_title: title,
          bio,
          skills: skills
            .split(',')
            .map((entry) => entry.trim())
            .filter(Boolean),
          expertise,
          qualifications,
          years_of_experience: years === '' ? null : Number(years),
          professional_links: cleanedLinks,
        }),
      );
      setSaved(true);
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) return <LoadingState label="Loading your trainer profile…" rows={5} />;
  if (loadError) {
    return (
      <ErrorState
        title="Could not load your profile"
        message={loadError.message}
        requestId={loadError.requestId || undefined}
      />
    );
  }
  if (!profile) return null;

  return (
    <Card className="animate-rise-in">
      <CardHeader>
        <CardTitle>Trainer profile</CardTitle>
        <CardDescription>
          <span className="font-mono">{profile.trainer_id}</span> · {profile.completion_percent}%
          complete
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted-foreground">Assignment availability:</span>
          <Badge variant={profile.is_accepting_assignments ? 'success' : 'neutral'}>
            {profile.is_accepting_assignments ? 'Accepting assignments' : 'Not accepting'}
          </Badge>
          {/* Set by an administrator: trainers do not assign themselves work. */}
          <span className="text-xs text-muted-foreground">Set by an administrator.</span>
        </div>

        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}
          {saved ? <Alert variant="success">Your profile was saved.</Alert> : null}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Professional title" htmlFor="title" error={errors.professional_title}>
              <Input value={title} onChange={(event) => setTitle(event.target.value)} />
            </Field>
            <Field
              label="Years of experience"
              htmlFor="years"
              error={errors.years_of_experience}
            >
              <Input
                type="number"
                min={0}
                max={70}
                value={years}
                onChange={(event) => setYears(event.target.value)}
              />
            </Field>
          </div>

          <Field
            label="Skills"
            htmlFor="skills"
            error={errors.skills}
            hint="Comma separated, e.g. Linux, Python, Networking. Up to 30."
          >
            <Input value={skills} onChange={(event) => setSkills(event.target.value)} />
          </Field>

          <Field label="Biography" htmlFor="bio" error={errors.bio}>
            <Textarea rows={4} value={bio} onChange={(event) => setBio(event.target.value)} />
          </Field>

          <Field label="Areas of expertise" htmlFor="expertise" error={errors.expertise}>
            <Textarea
              rows={3}
              value={expertise}
              onChange={(event) => setExpertise(event.target.value)}
            />
          </Field>

          <Field
            label="Qualifications and certifications"
            htmlFor="qualifications"
            error={errors.qualifications}
          >
            <Textarea
              rows={3}
              value={qualifications}
              onChange={(event) => setQualifications(event.target.value)}
            />
          </Field>

          <fieldset className="space-y-4">
            <legend className="text-sm font-medium">Professional links</legend>
            {errors.professional_links ? (
              <Alert variant="error">{errors.professional_links}</Alert>
            ) : null}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              {LINK_KEYS.map((key) => (
                <Field
                  key={key}
                  label={key[0]!.toUpperCase() + key.slice(1)}
                  htmlFor={`link-${key}`}
                  hint="Must be an https:// URL"
                >
                  <Input
                    type="url"
                    value={links[key] ?? ''}
                    onChange={(event) =>
                      setLinks((current) => ({ ...current, [key]: event.target.value }))
                    }
                  />
                </Field>
              ))}
            </div>
          </fieldset>

          <Button type="submit" disabled={isSaving}>
            {isSaving ? 'Saving…' : 'Save profile'}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
