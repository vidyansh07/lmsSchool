'use client';

/**
 * One of the institution's short lists — banks, payment categories, tax
 * groups — as the reference product's Organization settings keep them: a
 * table of names, a switch for "this is the default", a switch for "still in
 * use", and a box to add another.
 *
 * Three things this card insists on, because all three are the list's whole
 * point:
 *
 * * **Nothing is deleted.** A bank or a category is named by payments that
 *   outlive the institute's interest in it, so retiring one takes it out of
 *   the pickers and leaves the history legible. There is no delete button to
 *   look for.
 * * **At most one default**, and the server makes that exclusive in the same
 *   transaction — pressing a second one moves it rather than adding a
 *   second.
 * * **A failure is said out loud, next to the list.** A switch that silently
 *   fails is a setting somebody believes they changed.
 */

import { useState } from 'react';
import { Plus } from 'lucide-react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { errorMessage } from '@/lib/api';
import type { NamedRow, NamedRowInput } from '@/lib/fee-settings';

export function NamedListCard({
  title,
  description,
  rows,
  /** Null when this list has no notion of a default (banks). */
  defaultLabel,
  canManage,
  onCreate,
  onUpdate,
  onChanged,
}: {
  title: string;
  description: string;
  rows: NamedRow[];
  defaultLabel?: string | null;
  canManage: boolean;
  onCreate: (payload: NamedRowInput) => Promise<unknown>;
  onUpdate: (id: string, payload: Partial<NamedRowInput>) => Promise<unknown>;
  onChanged: () => void;
}) {
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function run(work: () => Promise<unknown>) {
    setBusy(true);
    setFailure(null);
    try {
      await work();
      onChanged();
    } catch (cause) {
      setFailure(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {failure ? <Alert variant="error">{failure}</Alert> : null}

        {rows.length === 0 ? (
          <p className="text-sm text-ink-muted">Nothing on this list yet.</p>
        ) : (
          <TableWrapper>
            <Table>
              <thead>
                <tr>
                  <Th>Name</Th>
                  {defaultLabel ? <Th>{defaultLabel}</Th> : null}
                  <Th>In use</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} className="hover:bg-sunken/40">
                    <Td>{row.name}</Td>
                    {defaultLabel ? (
                      <Td>
                        <Switch
                          aria-label={`${row.name} is the ${defaultLabel.toLowerCase()}`}
                          checked={Boolean(row.is_default)}
                          disabled={!canManage || busy || Boolean(row.is_default)}
                          onCheckedChange={() => void run(() => onUpdate(row.id, { is_default: true }))}
                        />
                      </Td>
                    ) : null}
                    <Td>
                      <Switch
                        aria-label={`${row.name} is in use`}
                        checked={row.is_active !== false}
                        disabled={!canManage || busy}
                        onCheckedChange={(checked) =>
                          void run(() => onUpdate(row.id, { is_active: checked }))
                        }
                      />
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </TableWrapper>
        )}

        {canManage ? (
          <form
            className="flex items-end gap-2 border-t border-line pt-4"
            onSubmit={(event) => {
              event.preventDefault();
              const typed = name.trim();
              if (!typed) {
                setFailure('Give it a name first.');
                return;
              }
              void run(async () => {
                await onCreate({ name: typed });
                setName('');
              });
            }}
            noValidate
          >
            <Field label={`Add to ${title.toLowerCase()}`} htmlFor={`add-${title}`} className="flex-1">
              <Input
                id={`add-${title}`}
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </Field>
            <Button type="submit" variant="outline" className="mb-0.5" disabled={busy}>
              <Plus className="size-4" aria-hidden="true" />
              Add
            </Button>
          </form>
        ) : (
          <p className="border-t border-line pt-4 text-sm text-ink-muted">
            You can read this list but not change it.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
