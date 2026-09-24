"use client";

/**
 * Form builder: the list of `FormDefinition`s, each entity's dynamic
 * schema. Opening one is a read; creating one is the only write here, and
 * it starts an empty definition with no versions — the field editor lives
 * on the detail screen.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Plus } from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { RequireAuth } from "@/components/require-auth";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
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
import { Field } from "@/components/ui/field";
import { Input, Select } from "@/components/ui/input";
import { Table, TableWrapper, Td, Th } from "@/components/ui/table";
import { useApi } from "@/hooks/use-api";
import { fieldErrors } from "@/lib/api";
import { Capability, can } from "@/lib/capabilities";
import {
  FORM_DEFINITION_STATUS_LABEL,
  FORM_DEFINITION_STATUS_VARIANT,
} from "@/lib/labels";
import { createFormDefinition, slugifyFormKey } from "@/lib/forms";
import type { FormDefinitionListResponse } from "@/lib/forms";
import type { FormEntity } from "@/types/api";

const ENTITIES: FormEntity[] = ["activity", "student", "registration", "review"];

function NewFormDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (slug: string) => void;
}) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [entity, setEntity] = useState<FormEntity>("activity");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  function reset() {
    setName("");
    setSlug("");
    setSlugTouched(false);
    setEntity("activity");
    setErrors({});
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setErrors({});
    try {
      const created = await createFormDefinition({
        slug: slug.trim(),
        name: name.trim(),
        entity,
      });
      reset();
      onCreated(created.slug);
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          reset();
          onClose();
        }
      }}
    >
      <DialogContent>
        <form className="space-y-4" onSubmit={(event) => void submit(event)} noValidate>
          <DialogHeader>
            <DialogTitle>New form</DialogTitle>
            <DialogDescription>
              Starts with no versions. Add fields from a draft on the next
              screen.
            </DialogDescription>
          </DialogHeader>
          {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}
          <Field label="Name" htmlFor="form-name" error={errors.name} required>
            <Input
              id="form-name"
              autoFocus
              value={name}
              onChange={(event) => {
                const value = event.target.value;
                setName(value);
                if (!slugTouched) setSlug(slugifyFormKey(value));
              }}
            />
          </Field>
          <Field
            label="Slug"
            htmlFor="form-slug"
            error={errors.slug}
            required
            hint="Used in the URL; stable once created."
          >
            <Input
              id="form-slug"
              value={slug}
              onChange={(event) => {
                setSlugTouched(true);
                setSlug(event.target.value);
              }}
            />
          </Field>
          <Field label="Entity" htmlFor="form-entity" error={errors.entity} required>
            <Select
              id="form-entity"
              value={entity}
              onChange={(event) => setEntity(event.target.value as FormEntity)}
            >
              {ENTITIES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </Select>
          </Field>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving || !name.trim() || !slug.trim()}>
              {saving ? "Creating…" : "Create form"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function FormsList() {
  const router = useRouter();
  const { user } = useAuth();
  const mayManage = can(user?.capabilities, Capability.formManage);
  const { data, error, isLoading, reload } =
    useApi<FormDefinitionListResponse>("/api/v1/forms/");
  const [creating, setCreating] = useState(false);

  const rows = data?.results ?? [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Forms</h1>
          <p className="text-sm text-muted-foreground">
            The dynamic schema behind activities, student profiles and
            registration. A published version is what the rest of the app
            renders; a draft is where you make the next change.
          </p>
        </div>
        {mayManage ? (
          <Button type="button" onClick={() => setCreating(true)}>
            <Plus className="size-4" aria-hidden="true" />
            New form
          </Button>
        ) : null}
      </div>

      {isLoading ? (
        <LoadingState label="Loading forms…" rows={6} />
      ) : error ? (
        <ErrorState
          title="Could not load forms"
          message={error.message}
          requestId={error.requestId || undefined}
          onRetry={reload}
        />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No forms yet"
          description="Create the first definition to start collecting structured data on an activity, student or registration."
          action={
            mayManage ? (
              <Button type="button" onClick={() => setCreating(true)}>
                <Plus className="size-4" aria-hidden="true" />
                New form
              </Button>
            ) : undefined
          }
        />
      ) : (
        <TableWrapper>
          <Table>
            <thead>
              <tr>
                <Th>Form</Th>
                <Th>Entity</Th>
                <Th>Status</Th>
                <Th>Published</Th>
                <Th>Draft</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.slug} className="hover:bg-muted/40">
                  <Td>
                    <Link
                      href={`/admin/forms/${row.slug}`}
                      className="font-medium underline-offset-2 hover:underline"
                    >
                      {row.name}
                    </Link>
                    <p className="text-xs text-muted-foreground">{row.slug}</p>
                  </Td>
                  <Td className="capitalize">{row.entity}</Td>
                  <Td>
                    <Badge variant={FORM_DEFINITION_STATUS_VARIANT[row.status]}>
                      {FORM_DEFINITION_STATUS_LABEL[row.status]}
                    </Badge>
                  </Td>
                  <Td>
                    {row.published_version ? (
                      <Badge variant="success">
                        v{row.published_version.number} ·{" "}
                        {row.published_version.field_count} fields
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground">None</span>
                    )}
                  </Td>
                  <Td>
                    {row.draft_version ? (
                      <Badge variant="warning">
                        v{row.draft_version.number} ·{" "}
                        {row.draft_version.field_count} fields
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground">None</span>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </TableWrapper>
      )}

      <NewFormDialog
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={(slug) => {
          setCreating(false);
          router.push(`/admin/forms/${slug}?created=1`);
        }}
      />
    </div>
  );
}

export default function FormsPage() {
  return (
    <RequireAuth capability={Capability.formView}>
      <FormsList />
    </RequireAuth>
  );
}
