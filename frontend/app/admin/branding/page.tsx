'use client';

/**
 * Where an institution chooses how the product looks.
 *
 * One colour, not two. The interface needs a legible sibling for buttons and
 * links — the brand orange is 2.96:1 against white and would make a button
 * label unreadable — but asking for both would mean somebody has to understand
 * contrast ratios to fill in a form. It is derived instead, so the person picks
 * the colour their institution is known by and cannot produce an interface
 * nobody can read.
 *
 * The preview applies the colour to the live document rather than to a swatch,
 * because a colour in a small square tells you almost nothing about what a
 * screen full of it looks like. Navigating away without saving reverts it —
 * the preview is a preview, not a quiet edit.
 */

import { useEffect, useState } from 'react';

import { useApi } from '@/hooks/use-api';

import { RequireAuth } from '@/components/require-auth';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { ErrorState, LoadingState } from '@/components/states';
import { useToast } from '@/components/ui/toast';
import { fieldErrors } from '@/lib/api';
import { applyBrandColor } from '@/lib/brand';
import { updateBranding, type Branding } from '@/lib/branding';
import { Capability } from '@/lib/capabilities';

/** Grras's own, and a few that read clearly at the derived lightness. */
const SUGGESTIONS: { value: string; label: string }[] = [
  { value: '#EF7220', label: 'Grras orange' },
  { value: '#B91C1C', label: 'Red' },
  { value: '#1D4ED8', label: 'Blue' },
  { value: '#047857', label: 'Green' },
  { value: '#6D28D9', label: 'Violet' },
  { value: '#0F766E', label: 'Teal' },
];

const HEX = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

function BrandingSettings() {
  // `useApi` rather than a hand-rolled fetch: it already resets its state
  // during render instead of from inside an effect, which is what stops the
  // cascading re-render React warns about.
  const { data: saved, error: loadError, isLoading, reload } = useApi<Branding>('/api/v1/branding/');

  const [draft, setDraft] = useState<{ color: string; name: string } | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);
  const { toast } = useToast();

  // The saved values are the starting point; `draft` holds edits from then on.
  // Deriving rather than copying into state on load means there is no effect
  // syncing two sources of the same truth.
  const color = draft?.color ?? saved?.brand_color ?? '';
  const name = draft?.name ?? saved?.display_name ?? '';
  const setColor = (value: string) => setDraft({ color: value, name });
  const setName = (value: string) => setDraft({ color, name: value });

  // Preview on the live document. Reverted on unmount so leaving the screen
  // without saving does not silently repaint the product.
  useEffect(() => {
    if (!isLoading) applyBrandColor(HEX.test(color) ? color : null);
    return () => applyBrandColor(saved?.brand_color ?? null);
  }, [color, isLoading, saved?.brand_color]);

  async function onSave(event: React.FormEvent) {
    event.preventDefault();
    setIsSaving(true);
    setErrors({});
    try {
      const branding = await updateBranding({ brand_color: color, display_name: name });
      setDraft(null);
      reload();
      try {
        if (branding.brand_color) {
          window.localStorage.setItem('grras.brand-color', branding.brand_color);
        } else {
          window.localStorage.removeItem('grras.brand-color');
        }
      } catch {
        // Not being able to cache it does not stop it being saved.
      }
      toast({ title: 'Branding saved', description: 'Everyone sees this from their next page load.' });
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) return <LoadingState label="Loading branding…" rows={3} />;
  if (loadError || !saved) {
    return (
      <ErrorState
        title="Could not load branding"
        message="The settings could not be fetched. The product is using its built-in palette meanwhile."
        onRetry={reload}
      />
    );
  }

  const isValid = color === '' || HEX.test(color);

  return (
    <div className="max-w-2xl space-y-6 animate-rise-in">
      <div>
        <h1 className="text-2xl">Branding</h1>
        <p className="text-muted-foreground">
          How this institution&rsquo;s copy of the product looks, for everyone who signs in.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Brand colour</CardTitle>
          <CardDescription>
            Used for buttons, links and highlights. A darker shade is worked out automatically for
            anything with text on it, so whatever you pick stays readable.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSave} className="space-y-5" noValidate>
            {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}

            <div className="flex flex-wrap items-end gap-3">
              <Field label="Colour" htmlFor="brand-color" error={errors.brand_color}>
                <Input
                  value={color}
                  onChange={(event) => setColor(event.target.value)}
                  placeholder="#EF7220"
                  spellCheck={false}
                  aria-describedby="brand-color-help"
                />
              </Field>
              <label className="flex flex-col gap-1.5 text-sm font-medium">
                Pick
                <input
                  type="color"
                  aria-label="Choose a brand colour"
                  value={HEX.test(color) ? color : '#EF7220'}
                  onChange={(event) => setColor(event.target.value)}
                  className="h-10 w-14 cursor-pointer rounded-md border border-border bg-surface p-1"
                />
              </label>
            </div>
            <p id="brand-color-help" className="text-xs text-muted-foreground">
              Six-digit hex, for example <code>#EF7220</code>. Leave empty for the built-in palette.
            </p>

            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">Suggestions</legend>
              <div className="flex flex-wrap gap-2">
                {SUGGESTIONS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => setColor(option.value)}
                    aria-pressed={color.toLowerCase() === option.value.toLowerCase()}
                    className="press flex items-center gap-2 rounded-full border border-border bg-surface py-1.5 pl-1.5 pr-3 text-xs font-medium hover:bg-muted aria-pressed:border-primary aria-pressed:ring-1 aria-pressed:ring-primary"
                  >
                    <span
                      aria-hidden="true"
                      className="size-5 rounded-full border border-black/10"
                      style={{ backgroundColor: option.value }}
                    />
                    {option.label}
                  </button>
                ))}
              </div>
            </fieldset>

            <Field label="Institution name" htmlFor="brand-name" error={errors.display_name}>
              <Input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Grras Solutions"
              />
            </Field>

            {!isValid ? (
              <Alert variant="warning">
                That is not a hex colour, so it has not been previewed. Use six digits after a hash.
              </Alert>
            ) : null}

            <div className="flex items-center gap-3">
              <Button type="submit" disabled={isSaving || !isValid}>
                {isSaving ? 'Saving…' : 'Save branding'}
              </Button>
              {saved?.brand_color ? (
                <Button type="button" variant="outline" onClick={() => setColor('')}>
                  Use the built-in palette
                </Button>
              ) : null}
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Preview</CardTitle>
          <CardDescription>
            The whole page is already using the colour above. These are the pieces it changes most.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-3">
          <Button type="button">Primary action</Button>
          <Button type="button" variant="outline">
            Secondary
          </Button>
          <span className="rounded-full bg-accent px-3 py-1 text-xs font-medium text-primary">
            Highlighted
          </span>
          <span
            aria-hidden="true"
            className="h-8 w-24 rounded-md"
            style={{ backgroundColor: 'var(--color-brand)' }}
          />
          <a href="#preview" className="text-primary underline underline-offset-2">
            A link
          </a>
        </CardContent>
      </Card>
    </div>
  );
}

export default function BrandingPage() {
  return (
    <RequireAuth capability={Capability.platformConfigure}>
      <BrandingSettings />
    </RequireAuth>
  );
}
