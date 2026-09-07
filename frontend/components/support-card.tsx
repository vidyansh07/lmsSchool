'use client';

import { useApi } from '@/hooks/use-api';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import type { PublicSettings } from '@/lib/settings';

/**
 * Where to write when something goes wrong.
 *
 * Renders nothing at all when the institution has configured neither a support
 * address nor a phone number, and nothing while the answer is still in flight.
 * A card saying "Not available" for a support address would be worse than no
 * card: it tells somebody there is nowhere to go, rather than leaving them to
 * ask the person in front of them.
 *
 * `useApi` with a literal path rather than a `lib/settings` function, because
 * that is what carries the loading and error state — and a card whose only
 * failure mode is "do not render" needs no error state of its own.
 */
export function SupportCard() {
  const { data } = useApi<PublicSettings>('/api/v1/settings/public/');
  if (!data || (!data.support_email && !data.support_phone)) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Need help?</CardTitle>
        <CardDescription>Contact {data.institution_name}.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-1 text-sm">
        {data.support_email ? (
          <p>
            Email: <a href={`mailto:${data.support_email}`}>{data.support_email}</a>
          </p>
        ) : null}
        {data.support_phone ? <p>Phone: {data.support_phone}</p> : null}
      </CardContent>
    </Card>
  );
}
