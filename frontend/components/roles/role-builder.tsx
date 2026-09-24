"use client";

/**
 * The Role Builder (ERP Phase 1): name → permissions → review → create.
 *
 * Three steps on one page rather than a dialog, because the permission list
 * is long and Back must be safe. Nothing is written until the last step's
 * verb; every earlier click is local state. The same component edits an
 * existing role, where a system role keeps its name and kind and only its
 * description and non-locked grants can change.
 *
 * API on load: `GET /permissions/` and, for an edit, `GET /roles/{slug}/`
 * plus `GET /roles/` (to diff against the kind's system role). On create:
 * `POST /roles/`. On save: `PATCH /roles/{slug}/`. Nothing else.
 */

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ArrowRight, Lock } from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { ErrorState, LoadingState } from "@/components/states";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input, Select, Textarea } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { ApiError, errorMessage, fieldErrors } from "@/lib/api";
import { Capability, can } from "@/lib/capabilities";
import {
  PERMISSION_CATEGORY_LABEL,
  ROLE_LABEL,
  SCOPE_LABEL,
} from "@/lib/labels";
import {
  createRole,
  getRole,
  listPermissions,
  listRoles,
  scopesFor,
  slugify,
  updateRole,
  type GrantInput,
} from "@/lib/roles";
import type {
  PermissionCategory,
  PermissionDef,
  PermissionScope,
  Role,
  RoleSummary,
  UserRole,
} from "@/types/api";

const KINDS: UserRole[] = [
  "admin",
  "manager",
  "counsellor",
  "trainer",
  "student",
];
const CATEGORIES: PermissionCategory[] = [
  "people",
  "academic",
  "operations",
  "configuration",
  "communication",
  "system",
];

type Grants = Record<
  string,
  { on: boolean; scope: PermissionScope | ""; locked: boolean }
>;

export function RoleBuilder({ slug }: { slug?: string }) {
  const router = useRouter();
  const { user } = useAuth();
  const mayAssign = can(user?.capabilities, Capability.permissionAssign);
  const isEdit = Boolean(slug);

  const [permissions, setPermissions] = useState<PermissionDef[] | null>(null);
  const [roles, setRoles] = useState<RoleSummary[]>([]);
  const [existing, setExisting] = useState<Role | null>(null);
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [name, setName] = useState("");
  const [roleSlug, setRoleSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [kind, setKind] = useState<UserRole>("manager");
  const [description, setDescription] = useState("");
  const [grants, setGrants] = useState<Grants>({});
  const [baseline, setBaseline] = useState<Set<string>>(new Set());
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      listPermissions(),
      listRoles(),
      slug ? getRole(slug) : Promise.resolve(null),
    ])
      .then(([defs, summaries, role]) => {
        if (cancelled) return;
        setPermissions(defs);
        setRoles(summaries);
        if (role) {
          setExisting(role);
          setName(role.name);
          setRoleSlug(role.slug);
          setKind(role.kind);
          setDescription(role.description);
          const next: Grants = {};
          for (const grant of role.permissions) {
            next[grant.code] = {
              on: true,
              scope: grant.scope,
              locked: grant.is_locked,
            };
          }
          setGrants(next);
        }
      })
      .catch((cause: unknown) => {
        if (!cancelled) setLoadError(cause instanceof ApiError ? cause : null);
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  // The kind's system role is the baseline the review step diffs against,
  // and the starting set for a new role.
  useEffect(() => {
    if (!permissions || isEdit) return;
    const system = roles.find((row) => row.is_system && row.slug === kind);
    if (!system) return;
    getRole(system.slug)
      .then((role) => {
        const codes = new Set(role.permissions.map((grant) => grant.code));
        setBaseline(codes);
        setGrants((current) => {
          if (Object.keys(current).length > 0) return current;
          const next: Grants = {};
          for (const code of codes)
            next[code] = { on: true, scope: "", locked: false };
          return next;
        });
      })
      .catch(() => {
        // Without a baseline the builder still works; the review shows no diff.
      });
  }, [kind, roles, permissions, isEdit]);

  useEffect(() => {
    if (!isEdit || !existing) return;
    const system = roles.find(
      (row) => row.is_system && row.slug === existing.kind,
    );
    if (!system) return;
    getRole(system.slug)
      .then((role) =>
        setBaseline(new Set(role.permissions.map((grant) => grant.code))),
      )
      .catch(() => {});
  }, [isEdit, existing, roles]);

  const grouped = useMemo(() => {
    const byCategory = new Map<PermissionCategory, PermissionDef[]>();
    for (const category of CATEGORIES) byCategory.set(category, []);
    for (const def of permissions ?? [])
      byCategory.get(def.category)?.push(def);
    return byCategory;
  }, [permissions]);

  const selected = useMemo(
    () => Object.entries(grants).filter(([, value]) => value.on),
    [grants],
  );
  const added = selected
    .map(([code]) => code)
    .filter((code) => !baseline.has(code));
  const removed = [...baseline].filter((code) => !grants[code]?.on);
  const isSystem = existing?.is_system ?? false;
  const scopes = scopesFor(kind);

  function toggle(code: string, on: boolean) {
    setGrants((current) => ({
      ...current,
      [code]: {
        on,
        scope: current[code]?.scope ?? "",
        locked: current[code]?.locked ?? false,
      },
    }));
  }

  function setScope(code: string, scope: PermissionScope | "") {
    setGrants((current) => ({
      ...current,
      [code]: { on: true, scope, locked: current[code]?.locked ?? false },
    }));
  }

  function grantList(): GrantInput[] {
    return selected.map(([code, value]) => ({
      code,
      scope: value.scope || "",
    }));
  }

  async function submit() {
    setIsSaving(true);
    setErrors({});
    setFormError(null);
    try {
      if (isEdit && existing) {
        const changes: Parameters<typeof updateRole>[1] = { description };
        if (!isSystem) changes.name = name.trim();
        if (mayAssign) changes.permissions = grantList();
        await updateRole(existing.slug, changes);
        router.push(`/admin/roles?saved=${existing.slug}`);
      } else {
        const role = await createRole({
          slug: roleSlug || slugify(name),
          name: name.trim(),
          kind,
          description,
          permissions: mayAssign ? grantList() : [],
        });
        router.push(`/admin/roles?created=${role.slug}`);
      }
    } catch (cause) {
      const fields = fieldErrors(cause);
      setErrors(fields);
      setFormError(
        Object.keys(fields).length === 0
          ? errorMessage(cause, "The role could not be saved.")
          : (fields.permissions ?? fields.__all__ ?? null),
      );
      if (fields.name || fields.slug || fields.kind) setStep(1);
    } finally {
      setIsSaving(false);
    }
  }

  if (loadError) {
    return (
      <ErrorState
        title="Could not load the role builder"
        message={loadError.message}
        requestId={loadError.requestId || undefined}
      />
    );
  }
  if (!permissions || (isEdit && !existing))
    return <LoadingState label="Loading permissions…" rows={4} />;

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">
          {isEdit ? `Edit role: ${existing?.name}` : "New role"}
        </h1>
        <p className="text-sm text-muted-foreground">
          Built-from decides what this role can never exceed and how far it
          sees. The permissions adjust the set; the review shows exactly what
          changes.
        </p>
      </div>

      <ol className="flex flex-wrap gap-2 text-sm" aria-label="Steps">
        {(["Name", "Permissions", "Review"] as const).map((label, index) => {
          const number = (index + 1) as 1 | 2 | 3;
          return (
            <li key={label}>
              <button
                type="button"
                onClick={() => setStep(number)}
                aria-current={step === number ? "step" : undefined}
                className={`rounded-full px-3 py-1 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${step === number ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-muted/70"}`}
              >
                {number}. {label}
              </button>
            </li>
          );
        })}
      </ol>

      {formError ? <Alert variant="error">{formError}</Alert> : null}

      {step === 1 ? (
        <Card>
          <CardHeader>
            <CardTitle>Name and kind</CardTitle>
            <CardDescription>
              {isSystem
                ? "A system role keeps its name and kind; only the description can change."
                : "Choose the system role this is built from. It fixes how far the role sees."}
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            <Field label="Name" htmlFor="role-name" error={errors.name}>
              <Input
                id="role-name"
                required
                maxLength={80}
                value={name}
                disabled={isSystem}
                onChange={(event) => {
                  setName(event.target.value);
                  if (!slugTouched && !isEdit)
                    setRoleSlug(slugify(event.target.value));
                }}
              />
            </Field>
            <Field
              label="Slug"
              htmlFor="role-slug"
              error={errors.slug}
              hint="Used in links and the API; cannot change later."
            >
              <Input
                id="role-slug"
                required
                maxLength={60}
                value={roleSlug}
                disabled={isEdit}
                onChange={(event) => {
                  setSlugTouched(true);
                  setRoleSlug(slugify(event.target.value));
                }}
              />
            </Field>
            <Field label="Built from" htmlFor="role-kind" error={errors.kind}>
              <Select
                id="role-kind"
                value={kind}
                disabled={isEdit}
                onChange={(event) => {
                  setKind(event.target.value as UserRole);
                  setGrants({});
                }}
              >
                {KINDS.map((value) => (
                  <option key={value} value={value}>
                    {ROLE_LABEL[value]}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              label="Description"
              htmlFor="role-description"
              error={errors.description}
              className="md:col-span-2"
            >
              <Textarea
                id="role-description"
                rows={2}
                maxLength={300}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </Field>
            <div className="md:col-span-2 flex justify-end">
              <Button
                type="button"
                onClick={() => setStep(2)}
                disabled={!name.trim() || !roleSlug}
              >
                Permissions
                <ArrowRight className="size-4" aria-hidden="true" />
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {step === 2 ? (
        <Card>
          <CardHeader>
            <CardTitle>Permissions</CardTitle>
            <CardDescription>
              {mayAssign
                ? `Switch each permission on or off. A scope narrows how far it reaches; it can never be wider than a ${ROLE_LABEL[kind].toLowerCase()} sees.`
                : "You can see the permissions but not change them: assigning permissions needs its own right."}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {CATEGORIES.map((category) => {
              const defs = grouped.get(category) ?? [];
              if (defs.length === 0) return null;
              return (
                <section key={category} className="space-y-2">
                  <h2 className="text-sm font-semibold">
                    {PERMISSION_CATEGORY_LABEL[category]}
                  </h2>
                  <ul className="divide-y divide-border rounded-md border border-border">
                    {defs.map((def) => {
                      const grant = grants[def.code];
                      const on = grant?.on ?? false;
                      const locked = grant?.locked ?? false;
                      return (
                        <li
                          key={def.code}
                          className="flex flex-wrap items-center gap-3 px-3 py-2"
                        >
                          <Switch
                            id={`grant-${def.code}`}
                            checked={on}
                            disabled={!mayAssign || locked}
                            onCheckedChange={(checked) =>
                              toggle(def.code, checked)
                            }
                            aria-label={def.description || def.code}
                          />
                          <label
                            htmlFor={`grant-${def.code}`}
                            className="min-w-0 flex-1 text-sm"
                          >
                            <span className="font-medium">
                              {def.description || def.code}
                            </span>
                            <span className="ml-2 font-mono text-xs text-muted-foreground">
                              {def.code}
                            </span>
                          </label>
                          {locked ? (
                            <Badge variant="neutral">
                              <Lock
                                className="mr-1 size-3"
                                aria-hidden="true"
                              />
                              Locked
                            </Badge>
                          ) : null}
                          {on && mayAssign && scopes.length > 1 ? (
                            <Select
                              aria-label={`Scope for ${def.code}`}
                              value={grant?.scope ?? ""}
                              disabled={locked}
                              onChange={(event) =>
                                setScope(
                                  def.code,
                                  event.target.value as PermissionScope | "",
                                )
                              }
                              className="w-56"
                            >
                              <option value="">{SCOPE_LABEL[""]}</option>
                              {scopes.map((scope) => (
                                <option key={scope} value={scope}>
                                  {SCOPE_LABEL[scope]}
                                </option>
                              ))}
                            </Select>
                          ) : null}
                        </li>
                      );
                    })}
                  </ul>
                </section>
              );
            })}
            <div className="flex justify-between">
              <Button type="button" variant="ghost" onClick={() => setStep(1)}>
                <ArrowLeft className="size-4" aria-hidden="true" />
                Back
              </Button>
              <Button type="button" onClick={() => setStep(3)}>
                Review
                <ArrowRight className="size-4" aria-hidden="true" />
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {step === 3 ? (
        <Card>
          <CardHeader>
            <CardTitle>Review</CardTitle>
            <CardDescription>
              Compared with the {ROLE_LABEL[kind].toLowerCase()} system role.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <dl className="grid gap-2 text-sm md:grid-cols-2">
              <dt className="text-muted-foreground">Name</dt>
              <dd>{name}</dd>
              <dt className="text-muted-foreground">Built from</dt>
              <dd>{ROLE_LABEL[kind]}</dd>
              <dt className="text-muted-foreground">Permissions</dt>
              <dd>{selected.length}</dd>
              <dt className="text-muted-foreground">Affected people</dt>
              <dd>
                {existing
                  ? `${existing.user_count} hold this role now`
                  : "Nobody yet"}
              </dd>
            </dl>
            <div className="flex flex-wrap gap-2">
              <Badge variant={added.length ? "success" : "neutral"}>
                {added.length} added
              </Badge>
              <Badge variant={removed.length ? "warning" : "neutral"}>
                {removed.length} removed
              </Badge>
            </div>
            {added.length ? (
              <p className="text-sm">
                <span className="font-medium">Added:</span> {added.join(", ")}
              </p>
            ) : null}
            {removed.length ? (
              <p className="text-sm">
                <span className="font-medium">Removed:</span>{" "}
                {removed.join(", ")}
              </p>
            ) : null}
            {existing && existing.user_count > 0 ? (
              <Alert variant="warning">
                Changing permissions signs out everyone who holds this role;
                they continue with the new set on their next sign-in.
              </Alert>
            ) : null}
            <div className="flex justify-between">
              <Button type="button" variant="ghost" onClick={() => setStep(2)}>
                <ArrowLeft className="size-4" aria-hidden="true" />
                Back
              </Button>
              <Button type="button" onClick={submit} disabled={isSaving}>
                {isSaving ? "Saving…" : isEdit ? "Save role" : "Create role"}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
