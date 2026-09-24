'use client';

/**
 * The institution's centres: open one, rename one, close one.
 *
 * A bounded administrator sees only their own row here (the server narrows
 * the list); only an unbounded operator holds `organisation.manage`, so the
 * add and edit controls appear for them alone.
 */

import { useState } from 'react';
import { Building2 } from 'lucide-react';

import { useAuth } from '@/components/auth-provider';
import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Table, TableWrapper, Td, Th, Tr } from '@/components/ui/table';
import { useApi } from '@/hooks/use-api';
import { fieldErrors } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import { formatDate } from '@/lib/format';
import { createBranch, updateBranch } from '@/lib/organisation';
import type { Branch, Paginated } from '@/types/api';

function BranchForm({
  initial,
  onSaved,
  onCancel,
}: {
  initial: Branch | null;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [code, setCode] = useState(initial?.code ?? '');
  const [name, setName] = useState(initial?.name ?? '');
  const [city, setCity] = useState(initial?.city ?? '');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setErrors({});
    try {
      if (initial) {
        await updateBranch(initial.id, { code: code.trim(), name: name.trim(), city: city.trim() });
      } else {
        await createBranch({ code: code.trim(), name: name.trim(), city: city.trim() });
      }
      onSaved();
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate className="space-y-3">
      {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Field
          label="Code"
          htmlFor="branch-code"
          error={errors.code}
          required
          hint="Short and stable, e.g. JPR."
        >
          <Input
            id="branch-code"
            value={code}
            autoFocus
            onChange={(event) => setCode(event.target.value.toUpperCase())}
          />
        </Field>
        <Field label="Name" htmlFor="branch-name" error={errors.name} required>
          <Input id="branch-name" value={name} onChange={(event) => setName(event.target.value)} />
        </Field>
        <Field label="City" htmlFor="branch-city" error={errors.city}>
          <Input id="branch-city" value={city} onChange={(event) => setCity(event.target.value)} />
        </Field>
      </div>
      <div className="flex gap-2">
        <Button
          type="submit"
          size="sm"
          disabled={saving || code.trim() === '' || name.trim() === ''}
        >
          {saving ? 'Saving…' : initial ? 'Save changes' : 'Open centre'}
        </Button>
        <Button type="button" size="sm" variant="ghost" disabled={saving} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

export function BranchesContent() {
  const { can } = useAuth();
  const mayManage = can(Capability.organisationManage);
  const { data, error, isLoading, reload } = useApi<Paginated<Branch>>(
    '/api/v1/branches/?page_size=100',
  );
  const [editing, setEditing] = useState<Branch | null>(null);
  const [adding, setAdding] = useState(false);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Centres</h1>
          <p className="text-sm text-ink-muted">
            Where the institution teaches. A centre bounds people and classes; courses and academic
            rules are shared by all of them.
          </p>
        </div>
        {mayManage && !adding ? (
          <Button
            onClick={() => {
              setAdding(true);
              setEditing(null);
            }}
          >
            Open a centre
          </Button>
        ) : null}
      </div>

      {adding ? (
        <Card className="">
          <CardHeader>
            <CardTitle as="h2">Open a centre</CardTitle>
            <CardDescription>Staff, students and batches are then placed in it.</CardDescription>
          </CardHeader>
          <CardContent>
            <BranchForm
              initial={null}
              onSaved={() => {
                setAdding(false);
                reload();
              }}
              onCancel={() => setAdding(false)}
            />
          </CardContent>
        </Card>
      ) : null}

      {editing ? (
        <Card className="">
          <CardHeader>
            <CardTitle as="h2">Edit {editing.name}</CardTitle>
          </CardHeader>
          <CardContent>
            <BranchForm
              initial={editing}
              onSaved={() => {
                setEditing(null);
                reload();
              }}
              onCancel={() => setEditing(null)}
            />
          </CardContent>
        </Card>
      ) : null}

      {error ? (
        <ErrorState
          title="Could not load the centres"
          message={error.message}
          requestId={error.requestId || undefined}
          onRetry={reload}
        />
      ) : isLoading || !data ? (
        <LoadingState label="Loading centres…" rows={3} />
      ) : data.results.length === 0 ? (
        <EmptyState
          title="No centres yet"
          description="Open the first one to start placing people in it."
        />
      ) : (
        <TableWrapper className="animate-fade-in">
          <Table>
            <thead>
              <tr>
                <Th>Code</Th>
                <Th>Centre</Th>
                <Th>City</Th>
                <Th>Status</Th>
                <Th>Opened</Th>
                {mayManage ? <Th className="text-right">Actions</Th> : null}
              </tr>
            </thead>
            <tbody>
              {data.results.map((branch) => (
                <Tr key={branch.id}>
                  <Td className="font-mono text-xs font-semibold">{branch.code}</Td>
                  <Td className="font-medium">
                    <span className="inline-flex items-center gap-2">
                      <Building2 className="size-4 text-ink-muted" aria-hidden="true" />
                      {branch.name}
                    </span>
                  </Td>
                  <Td>{branch.city || '—'}</Td>
                  <Td>
                    <Badge variant={branch.is_active ? 'success' : 'neutral'}>
                      {branch.is_active ? 'Open' : 'Closed'}
                    </Badge>
                  </Td>
                  <Td className="whitespace-nowrap text-ink-muted">
                    {formatDate(branch.created_at)}
                  </Td>
                  {mayManage ? (
                    <Td className="text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setEditing(branch);
                          setAdding(false);
                        }}
                      >
                        Edit
                      </Button>
                    </Td>
                  ) : null}
                </Tr>
              ))}
            </tbody>
          </Table>
        </TableWrapper>
      )}
    </div>
  );
}

export default function BranchesPage() {
  return (
    <RequireAuth capability={Capability.organisationViewAny}>
      <BranchesContent />
    </RequireAuth>
  );
}
