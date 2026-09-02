'use client';

import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';

import { EmptyState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { formatDate } from '@/lib/academic-labels';
import { verifyCertificate } from '@/lib/progress';
import type { PublicCertificate } from '@/types/api';

/**
 * Public certificate verification — §6.8.
 *
 * Deliberately *not* wrapped in `RequireAuth`: an employer checking a
 * certificate has no account here, and requiring one would make verification
 * useless. The page shows only what the public endpoint returns, which is an
 * allowlist enforced on the server.
 */
function Verify({ code }: { code: string }) {
  const [certificate, setCertificate] = useState<PublicCertificate | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    verifyCertificate(code)
      .then((data) => {
        if (!cancelled) setCertificate(data);
      })
      .catch(() => {
        if (!cancelled) setNotFound(true);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [code]);

  if (isLoading) return <LoadingState label="Checking this certificate…" rows={3} />;

  if (notFound || !certificate) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight">Certificate verification</h1>
        <EmptyState
          title="No certificate found"
          description="No certificate matches this code. Check the code on the certificate, or the link in its QR code."
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Certificate verification</h1>
        <p className="text-sm text-muted-foreground">{certificate.institution}</p>
      </div>

      <Card>
        <CardHeader className="gap-2">
          <div>
            <Badge
              variant={certificate.is_valid ? 'success' : 'error'}
              data-testid="verification-verdict"
            >
              {certificate.is_valid ? 'Valid certificate' : 'Not valid'}
            </Badge>
          </div>
          <CardTitle data-testid="verified-student">{certificate.student_name}</CardTitle>
          <CardDescription data-testid="verified-course">
            {certificate.course_title}
          </CardDescription>
        </CardHeader>

        <CardContent>
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-muted-foreground">Certificate number</dt>
              <dd className="font-mono">{certificate.certificate_number}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Completed on</dt>
              <dd>{formatDate(certificate.completion_date)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Issued on</dt>
              <dd>{formatDate(certificate.issued_on)}</dd>
            </div>
            {certificate.revoked_on ? (
              <div>
                <dt className="text-muted-foreground">Revoked on</dt>
                <dd>{formatDate(certificate.revoked_on)}</dd>
              </div>
            ) : null}
          </dl>

          {!certificate.is_valid ? (
            <p className="mt-4 text-sm text-muted-foreground">
              This certificate was issued by {certificate.institution} and has since been
              withdrawn. It is not a valid claim.
            </p>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

export default function VerifyPage() {
  const params = useParams<{ code: string }>();
  return <Verify code={params.code} />;
}
