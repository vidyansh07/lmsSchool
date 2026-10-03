"use client";

/**
 * Fill in a published form directly (`/forms/fill/[slug]`) — a counsellor
 * entering a walk-in enquiry, say. Saved as a submitted form in your own
 * name, so it reaches the same place, and starts the same automation rules,
 * as a form someone sent.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowLeft } from "lucide-react";

import { FieldRenderer, valuesForSubmit, type FormValues } from "@/components/forms/field-renderer";
import { ErrorState, LoadingState } from "@/components/states";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/layout";
import { useApi } from "@/hooks/use-api";
import { errorMessage, fieldErrors } from "@/lib/api";
import { fillForm } from "@/lib/forms";
import type { FillableForm, PublishedForm } from "@/types/api";

export function DirectFillScreen({ slug }: { slug: string }) {
  const router = useRouter();
  const published = useApi<PublishedForm>(`/api/v1/forms/published/${slug}/`);
  const fillable = useApi<FillableForm[]>("/api/v1/forms/fillable/");
  const [values, setValues] = useState<FormValues>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  if (published.isLoading || fillable.isLoading) return <LoadingState label="Loading form…" rows={6} />;
  const form = fillable.data?.find((row) => row.slug === slug);
  if (published.error || !published.data || !form) {
    return (
      <ErrorState
        title="This form cannot be filled in here"
        message={
          published.error?.message ??
          "It is not published, or it is an activity form, which is filled in from its activity."
        }
        onRetry={() => {
          published.reload();
          fillable.reload();
        }}
      />
    );
  }
  const fields = published.data.fields;

  async function submit() {
    setSaving(true);
    setErrors({});
    setFailure(null);
    try {
      const saved = await fillForm(slug, valuesForSubmit(fields, values));
      router.push(`/forms/${saved.id}`);
    } catch (cause) {
      const { __all__, ...rest } = fieldErrors(cause);
      setErrors(rest);
      setFailure(
        __all__ ??
          (Object.keys(rest).length > 0 ? "Some answers need attention." : errorMessage(cause)),
      );
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <Link
        href="/forms"
        className="inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        Forms
      </Link>
      <PageHeader title={form.name} meta="Saved in your name when you submit it." />
      {failure ? <Alert variant="error">{failure}</Alert> : null}
      <Card>
        <CardContent className="pt-5">
          <form
            className="space-y-5"
            onSubmit={(event) => {
              event.preventDefault();
              void submit();
            }}
          >
            <FieldRenderer
              fields={fields}
              values={values}
              errors={errors}
              onChange={(key, value) => setValues((current) => ({ ...current, [key]: value }))}
            />
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" onClick={() => router.push("/forms")}>
                Cancel
              </Button>
              <Button type="submit" disabled={saving}>
                {saving ? "Submitting…" : "Submit"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

