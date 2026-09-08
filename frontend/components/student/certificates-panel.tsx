/**
 * Certificates already issued to this student.
 *
 * Deliberately narrow: `/api/v1/certificates/mine/` returns only certificates
 * that exist, so there is nothing here about a course that is merely on track
 * to earn one — that standing is what `standing-panel.tsx`'s course-progress
 * tile and `/my-progress` are for. A certificate either exists or it does
 * not; this panel just lists the ones that do, newest first, with the same
 * download and verification links `app/my-progress/page.tsx` already offers.
 *
 * Only the newest few, though. This is one card among a dozen on the
 * dashboard, and a student who has been through several courses can hold
 * dozens of certificates — rendering all of them turned the page into a single
 * six-thousand-pixel column with everything below the card pushed off-screen.
 * The full list is a click away on `/my-progress`, which is built for it.
 */
import Link from 'next/link';
import { Award } from 'lucide-react';

import { ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { CERTIFICATE_STATUS_LABEL, CERTIFICATE_STATUS_VARIANT } from '@/lib/academic-labels';
import { formatDate } from '@/lib/format';
import { certificatePdfUrl } from '@/lib/progress';
import type { Certificate } from '@/types/api';

/** Enough to be useful at a glance, few enough to stay one card among many. */
const DEFAULT_LIMIT = 4;

export function CertificatesPanel({
  certificates,
  isLoading,
  error,
  onRetry,
  limit = DEFAULT_LIMIT,
}: {
  certificates: Certificate[];
  isLoading?: boolean;
  error?: { message: string; requestId?: string } | null;
  onRetry?: () => void;
  /** How many to show before linking out. Pass `Infinity` for the lot. */
  limit?: number;
}) {
  if (isLoading) return <LoadingState label="Loading your certificates…" rows={2} />;
  if (error) {
    return <ErrorState message={error.message} requestId={error.requestId} onRetry={onRetry} />;
  }

  if (certificates.length === 0) {
    return (
      <p className="rounded-[var(--radius-card)] border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
        No certificates yet. One appears here as soon as a course is complete and it is issued.
      </p>
    );
  }

  const shown = certificates.slice(0, limit);
  const hidden = certificates.length - shown.length;

  return (
    <>
      <ul className="space-y-3">
        {shown.map((certificate) => (
          <li
            key={certificate.id}
            className="flex flex-wrap items-start justify-between gap-3 rounded-[var(--radius-card)] border border-border p-3"
          >
            <div className="flex min-w-0 items-start gap-2.5">
              <Award className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{certificate.course_title}</p>
                <p className="text-xs text-muted-foreground">
                  <Badge variant={CERTIFICATE_STATUS_VARIANT[certificate.status]}>
                    {CERTIFICATE_STATUS_LABEL[certificate.status]}
                  </Badge>
                  <span className="ml-2">Issued {formatDate(certificate.issued_at)}</span>
                </p>
              </div>
            </div>
            <div className="flex shrink-0 gap-2">
              <Button asChild size="sm" variant="outline">
                <a href={certificatePdfUrl(certificate.id)}>Download</a>
              </Button>
              <Button asChild size="sm" variant="ghost">
                <Link href={`/verify/${certificate.verification_code}`}>Verify</Link>
              </Button>
            </div>
          </li>
        ))}
      </ul>
      {hidden > 0 ? (
        <Button asChild variant="ghost" size="sm" className="mt-3">
          <Link href="/my-progress">
            {hidden === 1 ? 'One more certificate' : `${hidden} more certificates`}
          </Link>
        </Button>
      ) : null}
    </>
  );
}
