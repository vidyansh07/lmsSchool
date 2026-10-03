"use client";

/**
 * Form definition detail: version history, opening a new draft (optionally
 * cloned from the published one), the field editor for whichever version is
 * selected, and publish/unpublish.
 *
 * Field writes only ever target the definition's current draft — a
 * published or archived version is read-only here, matching the server's
 * 409 on a field write to a non-draft version.
 */

import { useEffect, useState } from "react";

import { ErrorState, LoadingState } from "@/components/states";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableWrapper, Td, Th } from "@/components/ui/table";
import { FieldEditor } from "@/components/forms/field-editor";
import { FormAssignmentsTable } from "@/components/forms/form-assignments-table";
import { SendFormDialog } from "@/components/forms/send-form-dialog";
import { EmptyState } from "@/components/states";
import { useApi } from "@/hooks/use-api";
import { ApiError, errorMessage } from "@/lib/api";
import { Capability, can } from "@/lib/capabilities";
import { useAuth } from "@/components/auth-provider";
import {
  FORM_ENTITY_LABEL,
  FORM_VERSION_STATUS_LABEL,
  FORM_VERSION_STATUS_VARIANT,
} from "@/lib/labels";
import {
  createFormVersion,
  getFormDefinition,
  getFormVersion,
  publishFormVersion,
  replaceFormFields,
  unpublishFormVersion,
} from "@/lib/forms";
import { formatDateTime } from "@/lib/format";
import type {
  FormAssignment,
  FormDefinitionDetail,
  FormFieldInput,
  FormVersionDetail,
  FormVersionSummary,
  Paginated,
} from "@/types/api";

/** Who was sent this form, and what came back — newest first. */
function ResponsesCard({ slug, refreshKey }: { slug: string; refreshKey: number }) {
  const { data, error, isLoading, reload } = useApi<Paginated<FormAssignment>>(
    `/api/v1/forms/assignments/?box=all&form=${encodeURIComponent(slug)}&r=${refreshKey}`,
  );
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Responses</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <LoadingState label="Loading responses…" rows={3} />
        ) : error ? (
          <ErrorState message={error.message} onRetry={reload} />
        ) : !data || data.results.length === 0 ? (
          <EmptyState
            title="No responses yet"
            description="Send the form to someone, fill it in from Forms, or let an automation rule send it."
          />
        ) : (
          <FormAssignmentsTable rows={data.results} showForm={false} showAssignee />
        )}
      </CardContent>
    </Card>
  );
}

function toInputFields(fields: FormVersionDetail["fields"]): FormFieldInput[] {
  return fields.map((field) => ({ ...field }));
}

interface DefinitionLoadState {
  definition: FormDefinitionDetail | null;
  error: ApiError | null;
  isLoading: boolean;
  requestKey: string;
}

interface VersionLoadState {
  version: FormVersionDetail | null;
  error: ApiError | null;
  isLoading: boolean;
  requestKey: string;
}

export function FormDetail({ slug }: { slug: string }) {
  const { user } = useAuth();
  const mayManage = can(user?.capabilities, Capability.formManage);
  const maySend = can(user?.capabilities, Capability.formAssign);
  const mayReadResponses = can(user?.capabilities, Capability.formView);
  const [sending, setSending] = useState(false);
  const [responsesKey, setResponsesKey] = useState(0);

  const [reloadToken, setReloadToken] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);

  // Reset happens during render, not inside the effect body, when the
  // request identity changes — the same shape `hooks/use-api.ts` uses, so a
  // synchronous `setState` in the effect body never triggers a cascading
  // render lint warning.
  const defKey = `${slug}#${reloadToken}`;
  const [defState, setDefState] = useState<DefinitionLoadState>({
    definition: null,
    error: null,
    isLoading: true,
    requestKey: defKey,
  });
  if (defState.requestKey !== defKey) {
    setDefState({ definition: null, error: null, isLoading: true, requestKey: defKey });
  }

  const versionKey = `${slug}#${selected ?? "none"}#${reloadToken}`;
  const [versionState, setVersionState] = useState<VersionLoadState>({
    version: null,
    error: null,
    isLoading: selected !== null,
    requestKey: versionKey,
  });
  if (versionState.requestKey !== versionKey) {
    setVersionState({
      version: null,
      error: null,
      isLoading: selected !== null,
      requestKey: versionKey,
    });
  }

  const [fields, setFields] = useState<FormFieldInput[]>([]);
  const [fieldsForVersionKey, setFieldsForVersionKey] = useState<string | null>(
    null,
  );
  const [dirty, setDirty] = useState(false);

  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isOpeningDraft, setIsOpeningDraft] = useState(false);
  const [publishTarget, setPublishTarget] = useState<FormVersionSummary | null>(
    null,
  );
  const [unpublishTarget, setUnpublishTarget] =
    useState<FormVersionSummary | null>(null);
  const [isTransitioning, setIsTransitioning] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getFormDefinition(slug)
      .then((result) => {
        if (cancelled) return;
        setDefState({ definition: result, error: null, isLoading: false, requestKey: defKey });
        const draft = result.draft_version;
        const preferred =
          draft?.number ??
          result.published_version?.number ??
          result.versions[0]?.number ??
          null;
        setSelected((current) => current ?? preferred);
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        const error =
          cause instanceof ApiError
            ? cause
            : new ApiError(0, "unknown_error", "The request failed.", "");
        setDefState({ definition: null, error, isLoading: false, requestKey: defKey });
      });
    return () => {
      cancelled = true;
    };
  }, [defKey, slug]);

  useEffect(() => {
    if (selected === null) return;
    let cancelled = false;
    getFormVersion(slug, selected)
      .then((result) => {
        if (cancelled) return;
        setVersionState({ version: result, error: null, isLoading: false, requestKey: versionKey });
        setFields(toInputFields(result.fields));
        setFieldsForVersionKey(versionKey);
        setDirty(false);
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        const error =
          cause instanceof ApiError
            ? cause
            : new ApiError(0, "unknown_error", "The request failed.", "");
        setVersionState({ version: null, error, isLoading: false, requestKey: versionKey });
      });
    return () => {
      cancelled = true;
    };
  }, [versionKey, slug, selected]);

  const definition = defState.definition;
  const loadError = defState.error;
  const isLoading = defState.isLoading;
  const version = versionState.version;
  const versionError = versionState.error;
  const isLoadingVersion = versionState.isLoading;
  // `fields` lags one render behind `version` when the key just changed —
  // render the loading state until they line up, rather than a moment of
  // the previous version's fields under the new one's heading.
  const fieldsReady = fieldsForVersionKey === versionKey;

  function reload() {
    setReloadToken((value) => value + 1);
  }

  async function openDraft(clonedFrom?: number) {
    setIsOpeningDraft(true);
    setFailure(null);
    try {
      const created = await createFormVersion(slug, {
        cloned_from: clonedFrom,
      });
      setNotice(`Draft version ${created.number} opened.`);
      setSelected(created.number);
      reload();
    } catch (cause) {
      setFailure(errorMessage(cause, "Could not open a new draft."));
    } finally {
      setIsOpeningDraft(false);
    }
  }

  async function saveFields() {
    if (selected === null) return;
    setIsSaving(true);
    setFailure(null);
    try {
      const saved = await replaceFormFields(slug, selected, fields);
      setFields(toInputFields(saved.fields));
      setDirty(false);
      setNotice("Fields saved.");
      reload();
    } catch (cause) {
      setFailure(errorMessage(cause, "Could not save the fields."));
    } finally {
      setIsSaving(false);
    }
  }

  async function confirmPublish() {
    if (!publishTarget) return;
    setIsTransitioning(true);
    setFailure(null);
    try {
      await publishFormVersion(slug, publishTarget.number);
      setNotice(`Version ${publishTarget.number} published.`);
      setPublishTarget(null);
      reload();
    } catch (cause) {
      setFailure(
        errorMessage(
          cause,
          "Could not publish — the schema may be unchanged since the current published version.",
        ),
      );
      setPublishTarget(null);
    } finally {
      setIsTransitioning(false);
    }
  }

  async function confirmUnpublish() {
    if (!unpublishTarget) return;
    setIsTransitioning(true);
    setFailure(null);
    try {
      await unpublishFormVersion(slug, unpublishTarget.number);
      setNotice(`Version ${unpublishTarget.number} unpublished.`);
      setUnpublishTarget(null);
      reload();
    } catch (cause) {
      setFailure(errorMessage(cause, "Could not unpublish."));
      setUnpublishTarget(null);
    } finally {
      setIsTransitioning(false);
    }
  }

  if (isLoading) return <LoadingState label="Loading form…" rows={8} />;
  if (loadError) {
    return (
      <ErrorState
        title="Could not load this form"
        message={loadError.message}
        requestId={loadError.requestId || undefined}
        onRetry={reload}
      />
    );
  }
  if (!definition) {
    return (
      <ErrorState
        title="Form not found"
        message="This form definition does not exist, or you may not have access to it."
      />
    );
  }

  const hasDraft = Boolean(definition.draft_version);
  const isSelectedDraft = version?.status === "draft";

  // Activity forms reach people only through an activity; the rest can be
  // sent to someone or filled in directly once a version is published.
  const isSendable = definition.entity !== "activity" && Boolean(definition.published_version);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">
            {definition.name}
          </h1>
          <p className="text-sm text-ink-muted">
            {definition.slug} · {FORM_ENTITY_LABEL[definition.entity] ?? definition.entity}
          </p>
        </div>
        {isSendable && maySend ? (
          <Button type="button" onClick={() => setSending(true)}>
            Send to someone
          </Button>
        ) : null}
      </div>

      {notice ? <Alert variant="success">{notice}</Alert> : null}
      {failure ? <Alert variant="error">{failure}</Alert> : null}

      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">Versions</h2>
          {mayManage && !hasDraft ? (
            <Button
              type="button"
              variant="outline"
              disabled={isOpeningDraft}
              onClick={() =>
                void openDraft(definition.published_version?.number)
              }
            >
              {isOpeningDraft
                ? "Opening…"
                : definition.published_version
                  ? "Clone published as new draft"
                  : "New draft"}
            </Button>
          ) : null}
        </div>

        {definition.versions.length === 0 ? (
          <p className="text-sm text-ink-muted">
            No versions yet. Open a draft to start adding fields.
          </p>
        ) : (
          <TableWrapper>
            <Table>
              <thead>
                <tr>
                  <Th>Version</Th>
                  <Th>Status</Th>
                  <Th>Fields</Th>
                  <Th>Published</Th>
                  <Th>
                    <span className="sr-only">Actions</span>
                  </Th>
                </tr>
              </thead>
              <tbody>
                {definition.versions.map((row) => (
                  <tr
                    key={row.id}
                    className={
                      row.number === selected ? "bg-sunken/40" : "hover:bg-sunken/40"
                    }
                  >
                    <Td>
                      <button
                        type="button"
                        className="font-medium underline-offset-2 hover:underline"
                        onClick={() => setSelected(row.number)}
                      >
                        v{row.number}
                      </button>
                    </Td>
                    <Td>
                      <Badge variant={FORM_VERSION_STATUS_VARIANT[row.status]}>
                        {FORM_VERSION_STATUS_LABEL[row.status]}
                      </Badge>
                    </Td>
                    <Td>{row.field_count}</Td>
                    <Td>
                      {row.published_at
                        ? `${formatDateTime(row.published_at)}${row.published_by ? ` · ${row.published_by}` : ""}`
                        : "—"}
                    </Td>
                    <Td className="text-right">
                      {mayManage && row.status === "draft" ? (
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => setPublishTarget(row)}
                        >
                          Publish
                        </Button>
                      ) : null}
                      {mayManage && row.status === "published" ? (
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          onClick={() => setUnpublishTarget(row)}
                        >
                          Unpublish
                        </Button>
                      ) : null}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </TableWrapper>
        )}
      </div>

      <div className="space-y-3">
        <h2 className="text-lg font-semibold">
          {version ? `Fields — v${version.number}` : "Fields"}
        </h2>
        {isLoadingVersion || (version && !fieldsReady) ? (
          <LoadingState label="Loading version…" rows={4} />
        ) : versionError ? (
          <ErrorState
            title="Could not load this version"
            message={versionError.message}
            requestId={versionError.requestId || undefined}
            onRetry={reload}
          />
        ) : !version ? (
          <p className="text-sm text-ink-muted">
            Select a version above, or open a new draft, to edit its fields.
          </p>
        ) : (
          <>
            <FieldEditor
              slug={slug}
              fields={fields}
              disabled={!isSelectedDraft}
              onChange={(next) => {
                setFields(next);
                setDirty(true);
              }}
            />
            {isSelectedDraft && mayManage ? (
              <div className="flex justify-end">
                <Button
                  type="button"
                  onClick={() => void saveFields()}
                  disabled={isSaving || !dirty}
                >
                  {isSaving ? "Saving…" : "Save fields"}
                </Button>
              </div>
            ) : null}
          </>
        )}
      </div>

      {isSendable && mayReadResponses ? (
        <ResponsesCard slug={definition.slug} refreshKey={responsesKey} />
      ) : null}

      {isSendable && maySend ? (
        <SendFormDialog
          form={{ slug: definition.slug, name: definition.name }}
          open={sending}
          onClose={() => setSending(false)}
          onSent={(assignment) => {
            setSending(false);
            setNotice(`Sent to ${assignment.assigned_to.name}.`);
            setResponsesKey((key) => key + 1);
          }}
        />
      ) : null}

      <Dialog
        open={Boolean(publishTarget)}
        onOpenChange={(open) => (open ? undefined : setPublishTarget(null))}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Publish version {publishTarget?.number}?</DialogTitle>
            <DialogDescription>
              This replaces whichever version is currently published for
              every screen that renders &ldquo;{definition.name}&rdquo;. You
              can unpublish it again afterwards, but every response already
              submitted keeps pointing at the version it was written
              against.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setPublishTarget(null)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              disabled={isTransitioning}
              onClick={() => void confirmPublish()}
            >
              {isTransitioning ? "Publishing…" : "Publish"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={Boolean(unpublishTarget)}
        onOpenChange={(open) => (open ? undefined : setUnpublishTarget(null))}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              Unpublish version {unpublishTarget?.number}?
            </DialogTitle>
            <DialogDescription>
              Nothing will be published for &ldquo;{definition.name}&rdquo;
              until another version is published. Screens that render this
              form will show it as unavailable.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setUnpublishTarget(null)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              disabled={isTransitioning}
              onClick={() => void confirmUnpublish()}
            >
              {isTransitioning ? "Unpublishing…" : "Unpublish"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
