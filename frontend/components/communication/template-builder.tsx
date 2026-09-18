'use client';

/**
 * One `MessageTemplate`'s builder screen (`docs/erp/COMMUNICATION_CATALOG.md`,
 * ADR-12): a version's subject/body/variables allowlist, approve/publish,
 * and a live Preview panel. Same "sections stacked on one detail route"
 * shape as `components/automation/rule-builder.tsx`.
 *
 * The server (`MessageTemplateSerializer`) hands back exactly two versions
 * worth looking at, never a full history list: `current_version` (the
 * published one — immutable, live) and `draft_version` (whichever version is
 * not yet published — draft or approved-but-unpublished; there is only ever
 * one at a time, `create_draft_version` refuses a second). This screen edits
 * `draft_version` when one exists, and offers "Start a new version" (cloned
 * server-side from `current_version`) when it does not.
 *
 * D-051 is load-bearing here, not incidental: `variables` is an *allowlist*,
 * not documentation — the server only ever substitutes a path that appears
 * in it, so this editor is the one place that list is written, and Preview
 * is the one place a body actually gets rendered against real-shaped data
 * before anyone sends it. Nothing here evaluates `body_html`/`body_text`
 * itself; every render is a round trip to `previewTemplateVersion`, and its
 * `html` is shown through `TemplateHtmlPreview`'s sandboxed iframe, never
 * `dangerouslySetInnerHTML` (see that file's own docstring for why).
 */

import { useState } from 'react';
import { X } from 'lucide-react';

import { useAuth } from '@/components/auth-provider';
import { Confirm } from '@/components/confirm';
import { isStepUpRequired, StepUpDialog } from '@/components/roles/step-up-dialog';
import { ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Textarea } from '@/components/ui/input';
import { TemplateHtmlPreview } from '@/components/communication/template-preview';
import { useApi } from '@/hooks/use-api';
import { errorMessage } from '@/lib/api';
import { Capability, can } from '@/lib/capabilities';
import {
  approveTemplateVersion,
  createTemplateVersion,
  publishTemplateVersion,
  previewTemplateVersion,
  testSendTemplateVersion,
  updateTemplateVersion,
} from '@/lib/communication';
import { COMMUNICATION_CHANNEL_LABEL, TEMPLATE_STATUS_LABEL, TEMPLATE_STATUS_VARIANT } from '@/lib/labels';
import { formatDateTime } from '@/lib/format';
import type { MessageTemplate, TemplatePreviewResult } from '@/types/api';

export function TemplateBuilder({ templateKey }: { templateKey: string }) {
  const { user } = useAuth();
  const mayManage = can(user?.capabilities, Capability.templateManage);
  const mayApprove = can(user?.capabilities, Capability.templateApprove);

  const { data: template, error, isLoading, reload } = useApi<MessageTemplate>(
    `/api/v1/templates/${templateKey}/`,
  );

  const [subject, setSubject] = useState('');
  const [bodyHtml, setBodyHtml] = useState('');
  const [bodyText, setBodyText] = useState('');
  const [variables, setVariables] = useState<string[]>([]);
  const [newVariable, setNewVariable] = useState('');
  const [dirty, setDirty] = useState(false);

  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isStartingVersion, setIsStartingVersion] = useState(false);
  const [isTransitioning, setIsTransitioning] = useState(false);
  const [confirmingPublish, setConfirmingPublish] = useState(false);

  const [stepUpOpen, setStepUpOpen] = useState(false);
  const [approvalPending, setApprovalPending] = useState(false);

  const [previewVars, setPreviewVars] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<TemplatePreviewResult | null>(null);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [previewFailure, setPreviewFailure] = useState<string | null>(null);
  const [testSendNotice, setTestSendNotice] = useState<string | null>(null);
  const [isTestSending, setIsTestSending] = useState(false);

  // Re-seed the editable draft from the server's own truth whenever a fresh
  // template arrives — same "reset during render on reference inequality"
  // pattern `rule-builder.tsx` uses, for the same reason (a `useApi` refetch
  // hands back a new object every time).
  const [seeded, setSeeded] = useState<MessageTemplate | null>(null);
  if (template && template !== seeded) {
    const draft = template.draft_version;
    setSubject(draft?.subject ?? '');
    setBodyHtml(draft?.body_html ?? '');
    setBodyText(draft?.body_text ?? '');
    setVariables(draft?.variables ?? []);
    setDirty(false);
    setPreview(null);
    setPreviewVars({});
    setSeeded(template);
  }

  if (isLoading) return <LoadingState label="Loading the template…" rows={8} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load this template"
        message={error.message}
        requestId={error.requestId || undefined}
        onRetry={reload}
      />
    );
  }
  if (!template) {
    return (
      <ErrorState
        title="Template not found"
        message="This template does not exist, or you may not have access to it."
      />
    );
  }

  const draft = template.draft_version;
  const published = template.current_version;
  const isWhatsapp = template.channel === 'whatsapp';
  // What Preview/Test-send act on: the version actually in progress, or —
  // once everything is published and nothing new has been started — the
  // live one, so those tools still work between versions.
  const activeVersion = draft ?? published;

  function addVariable() {
    const value = newVariable.trim();
    if (!value || variables.includes(value)) return;
    setVariables([...variables, value]);
    setNewVariable('');
    setDirty(true);
  }

  function removeVariable(value: string) {
    setVariables(variables.filter((entry) => entry !== value));
    setDirty(true);
  }

  async function save() {
    if (!draft) return;
    setIsSaving(true);
    setFailure(null);
    try {
      await updateTemplateVersion(templateKey, draft.number, {
        subject,
        body_html: bodyHtml,
        body_text: bodyText,
        variables,
      });
      setDirty(false);
      setNotice('Draft saved.');
      reload();
    } catch (cause) {
      setFailure(errorMessage(cause, 'Could not save this version.'));
    } finally {
      setIsSaving(false);
    }
  }

  async function startNewVersion() {
    setIsStartingVersion(true);
    setFailure(null);
    try {
      await createTemplateVersion(templateKey);
      setNotice('New draft version opened, cloned from the published one.');
      reload();
    } catch (cause) {
      setFailure(errorMessage(cause, 'Could not open a new version.'));
    } finally {
      setIsStartingVersion(false);
    }
  }

  async function runApprove() {
    if (!draft) return;
    setIsTransitioning(true);
    setFailure(null);
    try {
      await approveTemplateVersion(templateKey, draft.number);
      setNotice('Version approved.');
      reload();
    } catch (cause) {
      if (isStepUpRequired(cause)) {
        setApprovalPending(true);
        setStepUpOpen(true);
      } else {
        setFailure(errorMessage(cause, 'Could not approve this version.'));
      }
    } finally {
      setIsTransitioning(false);
    }
  }

  async function runPublish() {
    if (!draft) return;
    setIsTransitioning(true);
    setFailure(null);
    try {
      await publishTemplateVersion(templateKey, draft.number);
      setNotice('Version published — live for this key and channel.');
      setConfirmingPublish(false);
      reload();
    } catch (cause) {
      setFailure(errorMessage(cause, 'Could not publish this version.'));
    } finally {
      setIsTransitioning(false);
    }
  }

  async function runPreview() {
    if (!activeVersion) return;
    setIsPreviewing(true);
    setPreviewFailure(null);
    setPreview(null);
    try {
      const result = await previewTemplateVersion(templateKey, activeVersion.number, previewVars);
      setPreview(result);
    } catch (cause) {
      setPreviewFailure(errorMessage(cause, 'Could not render this preview.'));
    } finally {
      setIsPreviewing(false);
    }
  }

  async function runTestSend() {
    if (!activeVersion) return;
    setIsTestSending(true);
    setPreviewFailure(null);
    setTestSendNotice(null);
    try {
      await testSendTemplateVersion(templateKey, activeVersion.number);
      setTestSendNotice('Sent to your own account.');
    } catch (cause) {
      setPreviewFailure(errorMessage(cause, 'Could not send the test.'));
    } finally {
      setIsTestSending(false);
    }
  }

  return (
    <div className="animate-rise-in space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{template.name}</h1>
            <Badge variant={TEMPLATE_STATUS_VARIANT[template.status]}>
              {TEMPLATE_STATUS_LABEL[template.status]}
            </Badge>
            <span className="font-mono text-xs text-muted-foreground">{template.key}</span>
          </div>
          <p className="text-sm text-muted-foreground">
            {COMMUNICATION_CHANNEL_LABEL[template.channel]} · {template.kind}
            {published ? ` · v${published.number} published` : ' · never published'}
          </p>
        </div>
      </div>

      {notice ? <Alert variant="success">{notice}</Alert> : null}
      {failure ? <Alert variant="error">{failure}</Alert> : null}
      {dirty ? (
        <Alert variant="warning">
          Unsaved changes — save the draft before previewing, approving or publishing so any of
          those reflect what you see here.
        </Alert>
      ) : null}

      {draft ? (
        <Card>
          <CardHeader>
            <CardTitle>Editing v{draft.number}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {draft.approved_at ? (
              <p className="text-xs text-muted-foreground">
                Approved {formatDateTime(draft.approved_at)} — changing anything below clears
                that approval and needs a fresh one.
              </p>
            ) : null}
            <Field label="Subject" htmlFor="template-subject">
              <Input
                id="template-subject"
                disabled={!mayManage}
                value={subject}
                onChange={(event) => {
                  setSubject(event.target.value);
                  setDirty(true);
                }}
              />
            </Field>
            <Field
              label="Body (HTML)"
              htmlFor="template-body-html"
              hint="Plain text with {{ variable }} placeholders — never evaluated as code, only substituted from the allowlist below."
            >
              <Textarea
                id="template-body-html"
                rows={8}
                disabled={!mayManage}
                value={bodyHtml}
                onChange={(event) => {
                  setBodyHtml(event.target.value);
                  setDirty(true);
                }}
              />
            </Field>
            <Field label="Body (plain text)" htmlFor="template-body-text">
              <Textarea
                id="template-body-text"
                rows={4}
                disabled={!mayManage}
                value={bodyText}
                onChange={(event) => {
                  setBodyText(event.target.value);
                  setDirty(true);
                }}
              />
            </Field>

            <div className="space-y-2">
              <label className="block text-sm font-medium" htmlFor="template-new-variable">
                Variables allowlist
              </label>
              <p className="text-xs text-muted-foreground">
                Only these paths render in the body above; anything else is left blank and
                flagged by Preview as a warning.
              </p>
              <div className="flex flex-wrap gap-2" data-testid="template-variables-list">
                {variables.length === 0 ? (
                  <span className="text-xs text-muted-foreground">No variables yet.</span>
                ) : (
                  variables.map((name) => (
                    <Badge key={name} variant="neutral" className="gap-1 font-mono">
                      {name}
                      {mayManage ? (
                        <button
                          type="button"
                          aria-label={`Remove ${name}`}
                          onClick={() => removeVariable(name)}
                          className="ml-0.5 rounded-full transition-colors hover:bg-border hover:text-foreground"
                        >
                          <X className="size-3" aria-hidden="true" />
                        </button>
                      ) : null}
                    </Badge>
                  ))
                )}
              </div>
              {mayManage ? (
                <div className="flex gap-2">
                  <Input
                    id="template-new-variable"
                    placeholder="e.g. student.name"
                    value={newVariable}
                    onChange={(event) => setNewVariable(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault();
                        addVariable();
                      }
                    }}
                  />
                  <Button type="button" variant="outline" onClick={addVariable}>
                    Add
                  </Button>
                </div>
              ) : null}
            </div>

            {mayManage ? (
              <Button type="button" disabled={!dirty || isSaving} onClick={() => void save()}>
                {isSaving ? 'Saving…' : 'Save draft'}
              </Button>
            ) : null}
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>No draft in progress</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              v{published?.number} is published and immutable. Start a new version — cloned from
              it — to change anything.
            </p>
            {mayManage ? (
              <Button type="button" disabled={isStartingVersion} onClick={() => void startNewVersion()}>
                {isStartingVersion ? 'Opening…' : 'Start a new version'}
              </Button>
            ) : null}
          </CardContent>
        </Card>
      )}

      {draft ? (
        <Card>
          <CardHeader>
            <CardTitle>Approve and publish</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              v{draft.number}
              {draft.approved_at ? ` · approved ${formatDateTime(draft.approved_at)}` : ' · not yet approved'}
              {isWhatsapp ? ' · WhatsApp approval needs a fresh step-up.' : ''}
            </p>
            <div className="flex flex-wrap gap-2">
              {mayApprove && !draft.approved_at ? (
                <Button
                  type="button"
                  variant="outline"
                  disabled={dirty || isTransitioning}
                  onClick={() => void runApprove()}
                >
                  {isTransitioning ? 'Approving…' : 'Approve'}
                </Button>
              ) : null}
              {mayManage && draft.approved_at ? (
                <Button type="button" disabled={dirty || isTransitioning} onClick={() => setConfirmingPublish(true)}>
                  Publish
                </Button>
              ) : null}
            </div>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Preview</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {!activeVersion ? (
            <p className="text-sm text-muted-foreground">Nothing to preview yet.</p>
          ) : (
            <>
              <p className="text-xs text-muted-foreground">
                Rendering v{activeVersion.number}
                {draft ? ' (the version being edited)' : ' (the published version)'}.
              </p>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {(draft ? variables : activeVersion.variables).map((name) => (
                  <Field key={name} label={name} htmlFor={`preview-var-${name}`}>
                    <Input
                      id={`preview-var-${name}`}
                      value={previewVars[name] ?? ''}
                      onChange={(event) =>
                        setPreviewVars({ ...previewVars, [name]: event.target.value })
                      }
                    />
                  </Field>
                ))}
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  disabled={isPreviewing || (draft != null && dirty)}
                  onClick={() => void runPreview()}
                >
                  {isPreviewing ? 'Rendering…' : 'Render preview'}
                </Button>
                {mayManage ? (
                  <Button type="button" variant="outline" disabled={isTestSending} onClick={() => void runTestSend()}>
                    {isTestSending ? 'Sending…' : 'Send a test to myself'}
                  </Button>
                ) : null}
              </div>
              {previewFailure ? <Alert variant="error">{previewFailure}</Alert> : null}
              {testSendNotice ? <Alert variant="success">{testSendNotice}</Alert> : null}
              {preview ? (
                <div className="space-y-3">
                  {preview.warnings.length > 0 ? (
                    <Alert variant="warning" data-testid="preview-warnings">
                      <p className="font-medium">This body references a variable not on the allowlist:</p>
                      <ul className="list-disc pl-5">
                        {preview.warnings.map((warning) => (
                          <li key={warning}>{warning}</li>
                        ))}
                      </ul>
                    </Alert>
                  ) : null}
                  <p className="text-sm">
                    <span className="font-medium">Subject: </span>
                    {preview.subject}
                  </p>
                  <TemplateHtmlPreview html={preview.html} title={`${template.name} preview`} />
                  <details>
                    <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">Plain text</summary>
                    <pre className="mt-1 whitespace-pre-wrap text-xs">{preview.text}</pre>
                  </details>
                </div>
              ) : null}
            </>
          )}
        </CardContent>
      </Card>

      <Confirm
        open={confirmingPublish}
        title={`Publish v${draft?.number ?? ''}?`}
        description="Once published, this version is immutable and live for this key and channel — every future send on this channel uses it until a newer version is published. This cannot be undone; a mistake needs a new version, not a rollback."
        confirmLabel="Publish"
        confirmVariant="primary"
        isConfirming={isTransitioning}
        onConfirm={() => void runPublish()}
        onCancel={() => setConfirmingPublish(false)}
      />

      <StepUpDialog
        open={stepUpOpen}
        onConfirmed={() => {
          setStepUpOpen(false);
          if (approvalPending) void runApprove();
          setApprovalPending(false);
        }}
        onCancel={() => {
          setStepUpOpen(false);
          setApprovalPending(false);
        }}
      />
    </div>
  );
}
