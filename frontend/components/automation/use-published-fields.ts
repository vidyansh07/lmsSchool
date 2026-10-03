"use client";

import { useEffect, useState } from "react";

import { getPublishedForm } from "@/lib/forms";
import type { FormField } from "@/types/api";

/** The answer-carrying questions of a form's published version, in order —
 *  or none while it loads, when it fails, or when no form is named.
 *  Headings are left out: they never have an answer. */
export function usePublishedFields(slug: string | null): FormField[] {
  const [loaded, setLoaded] = useState<{ slug: string; fields: FormField[] } | null>(null);
  useEffect(() => {
    if (!slug) return;
    let cancelled = false;
    getPublishedForm(slug)
      .then((form) => {
        if (!cancelled) setLoaded({ slug, fields: form.fields });
      })
      .catch(() => {
        if (!cancelled) setLoaded({ slug, fields: [] });
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);
  if (!slug || loaded?.slug !== slug) return [];
  return loaded.fields
    .filter((field) => field.type !== "heading")
    .slice()
    .sort((a, b) => a.order - b.order);
}
