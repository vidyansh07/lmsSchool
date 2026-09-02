'use client';

import { useCallback, useEffect, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Textarea } from '@/components/ui/input';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { ApiError, errorMessage } from '@/lib/api';
import {
  CERTIFICATE_STATUS_LABEL,
  CERTIFICATE_STATUS_VARIANT,
  formatDate,
} from '@/lib/academic-labels';
import {
  certificatePdfUrl,
  createCertificateTemplate,
  listCertificateTemplates,
  listCertificates,
  reissueCertificate,
  revokeCertificate,
} from '@/lib/progress';
import type { Certificate, CertificateTemplate } from '@/types/api';

/** Certificates and their templates. Issuing happens from the completion queue. */
function Certificates() {
  const [rows, setRows] = useState<Certificate[]>([]);
  const [templates, setTemplates] = useState<CertificateTemplate[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [isOpen, setIsOpen] = useState(false);
  const [template, setTemplate] = useState({
    name: '',
    institution_name: 'Grras Solutions',
    title: 'Certificate of Completion',
    body:
      'This is to certify that {student_name} has successfully completed ' +
      'the course {course_title} on {completion_date}.',
    signatory_name: '',
    signatory_title: '',
    is_default: true,
  });

  const load = useCallback(async () => {
    const [page, templateRows] = await Promise.all([
      listCertificates(),
      listCertificateTemplates(),
    ]);
    setRows(page.results);
    setTemplates(templateRows);
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listCertificates(), listCertificateTemplates()])
      .then(([page, templateRows]) => {
        if (cancelled) return;
        setRows(page.results);
        setTemplates(templateRows);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof ApiError ? cause : null);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function run(key: string, action: () => Promise<unknown>, message: string) {
    setBusy(key);
    setFormError(null);
    setNotice(null);
    try {
      await action();
      await load();
      setNotice(message);
    } catch (cause) {
      setFormError(errorMessage(cause, 'That could not be done.'));
    } finally {
      setBusy(null);
    }
  }

  if (isLoading) return <LoadingState label="Loading certificates…" rows={5} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load certificates"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Certificates</h1>
          <p className="text-sm text-muted-foreground">
            Issued from the completion queue once an administrator has approved the course.
          </p>
        </div>
        <Button type="button" onClick={() => setIsOpen((open) => !open)}>
          {isOpen ? 'Cancel' : 'New template'}
        </Button>
      </div>

      {formError ? <Alert variant="error">{formError}</Alert> : null}
      {notice ? (
        <Alert variant="success" role="status">
          {notice}
        </Alert>
      ) : null}

      {templates.length === 0 ? (
        <Alert variant="warning">
          There is no certificate template yet, so nothing can be issued. Create one first.
        </Alert>
      ) : null}

      {isOpen ? (
        <Card>
          <CardHeader>
            <CardTitle>New certificate template</CardTitle>
            <CardDescription>
              The body accepts {'{student_name}'}, {'{course_title}'}, {'{completion_date}'},{' '}
              {'{certificate_number}'}, {'{batch_code}'} and {'{institution_name}'}. Anything else
              is refused.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                void run(
                  'template',
                  async () => {
                    await createCertificateTemplate(template);
                    setIsOpen(false);
                  },
                  'Template saved.',
                );
              }}
            >
              <Field label="Name" htmlFor="name">
                <Input
                  id="name"
                  required
                  value={template.name}
                  onChange={(event) => setTemplate({ ...template, name: event.target.value })}
                />
              </Field>
              <Field label="Institution" htmlFor="institution_name">
                <Input
                  id="institution_name"
                  value={template.institution_name}
                  onChange={(event) =>
                    setTemplate({ ...template, institution_name: event.target.value })
                  }
                />
              </Field>
              <Field label="Heading" htmlFor="title">
                <Input
                  id="title"
                  value={template.title}
                  onChange={(event) => setTemplate({ ...template, title: event.target.value })}
                />
              </Field>
              <Field label="Body" htmlFor="body">
                <Textarea
                  id="body"
                  rows={3}
                  value={template.body}
                  onChange={(event) => setTemplate({ ...template, body: event.target.value })}
                />
              </Field>
              <Field label="Signatory" htmlFor="signatory_name">
                <Input
                  id="signatory_name"
                  value={template.signatory_name}
                  onChange={(event) =>
                    setTemplate({ ...template, signatory_name: event.target.value })
                  }
                />
              </Field>
              <Field label="Signatory title" htmlFor="signatory_title">
                <Input
                  id="signatory_title"
                  value={template.signatory_title}
                  onChange={(event) =>
                    setTemplate({ ...template, signatory_title: event.target.value })
                  }
                />
              </Field>
              <Button type="submit" disabled={busy === 'template' || !template.name}>
                {busy === 'template' ? 'Saving…' : 'Save template'}
              </Button>
            </form>
          </CardContent>
        </Card>
      ) : null}

      {rows.length === 0 ? (
        <EmptyState
          title="No certificates yet"
          description="Approve a completion, then issue its certificate from the completions queue."
        />
      ) : (
        <TableWrapper>
          <Table>
            <thead>
              <tr>
                <Th>Certificate</Th>
                <Th>Student</Th>
                <Th>Course</Th>
                <Th>Actions</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} data-testid="certificate-row">
                  <Td>
                    <div className="font-mono text-xs">{row.number}</div>
                    <Badge variant={CERTIFICATE_STATUS_VARIANT[row.status]} className="mt-1">
                      {CERTIFICATE_STATUS_LABEL[row.status]}
                    </Badge>
                    <div className="mt-1 text-xs text-muted-foreground">
                      Issued {formatDate(row.issued_at)}
                    </div>
                  </Td>
                  <Td>
                    {row.student_name}
                    <div className="font-mono text-xs text-muted-foreground">
                      {row.student_code}
                    </div>
                  </Td>
                  <Td>
                    {row.course_title}
                    <div className="text-xs text-muted-foreground">{row.batch_code}</div>
                  </Td>
                  <Td className="min-w-64 space-y-2">
                    <Button asChild size="sm" variant="outline">
                      <a href={certificatePdfUrl(row.id)}>Download</a>
                    </Button>
                    {row.status === 'issued' ? (
                      <>
                        <Field label="Reason" htmlFor={`reason-${row.id}`}>
                          <Input
                            id={`reason-${row.id}`}
                            value={reasons[row.id] ?? ''}
                            onChange={(event) =>
                              setReasons({ ...reasons, [row.id]: event.target.value })
                            }
                          />
                        </Field>
                        <div className="flex flex-wrap gap-2">
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            disabled={busy === row.id || !reasons[row.id]}
                            onClick={() =>
                              run(
                                row.id,
                                () => reissueCertificate(row.id, reasons[row.id] ?? ''),
                                'Reissued. The previous certificate is now superseded.',
                              )
                            }
                          >
                            Reissue
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="destructive"
                            disabled={busy === row.id || !reasons[row.id]}
                            onClick={() =>
                              run(
                                row.id,
                                () => revokeCertificate(row.id, reasons[row.id] ?? ''),
                                'Revoked. It still verifies, and says it was revoked.',
                              )
                            }
                          >
                            Revoke
                          </Button>
                        </div>
                      </>
                    ) : null}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </TableWrapper>
      )}
    </div>
  );
}

export default function CertificatesPage() {
  return (
    <RequireAuth>
      <Certificates />
    </RequireAuth>
  );
}
