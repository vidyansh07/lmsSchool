'use client';

/**
 * Build a report: pick a thing, pick what to show, ask it questions.
 *
 * The second of the two report modes, and the one for the questions nobody
 * thought of in advance. The twenty fixed reports beside it answer what
 * somebody anticipated; an operations team spends its day on "RHCSA and AWS
 * payments at Jaipur between April and June, by course".
 *
 * Everything offered here comes from the server's own description of each
 * dataset — its columns, the questions each field will answer, what it will
 * total. Nothing is hard-coded, so a dataset added on the server appears here
 * without a line changing, and a field the server does not declare cannot be
 * asked for by a screen that does not know it exists.
 *
 * The filter row is built from the field's *kind*: a date gets a date input,
 * a choice gets its own choices, a boolean gets yes/no. The operators offered
 * are the ones that field's kind allows and no others, which is the same
 * allowlist the server enforces — the screen simply never offers the ones
 * that would be refused.
 */

import { useEffect, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input, Select } from '@/components/ui/input';
import { PageHeader } from '@/components/ui/layout';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { errorMessage } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import { buildReport, listDatasets } from '@/lib/reporting';
import type {
  ReportBuildResult,
  ReportDataset,
  ReportFilterClause,
  ReportFilterSpec,
} from '@/types/api';

/** A filter row mid-edit. `value` is a string until it is sent, because every
 *  control on the page produces one; the shape it becomes is decided by the
 *  field's kind at the moment of sending. */
type DraftClause = { field: string; op: string; value: string };

function valueFor(spec: ReportFilterSpec | undefined, draft: DraftClause): unknown {
  if (!spec) return draft.value;
  if (draft.op === 'isnull') return draft.value === 'true';
  if (spec.kind === 'boolean') return draft.value === 'true';
  if (spec.kind === 'number') return draft.value === '' ? null : Number(draft.value);
  if (draft.op === 'in') {
    return draft.value
      .split(',')
      .map((part) => part.trim())
      .filter(Boolean);
  }
  return draft.value;
}

function FilterRow({
  spec,
  draft,
  onChange,
  onRemove,
}: {
  spec: ReportFilterSpec;
  draft: DraftClause;
  onChange: (next: DraftClause) => void;
  onRemove: () => void;
}) {
  const asBoolean = spec.kind === 'boolean' || draft.op === 'isnull';
  return (
    <div className="flex flex-wrap items-end gap-2 rounded-card border border-line bg-surface p-3">
      <span className="min-w-24 pb-2 text-sm font-medium">{spec.label}</span>

      <Field label="Question" htmlFor={`op-${spec.name}`}>
        <Select
          id={`op-${spec.name}`}
          value={draft.op}
          onChange={(event) => onChange({ ...draft, op: event.target.value })}
        >
          {spec.operators.map((operator) => (
            <option key={operator.value} value={operator.value}>
              {operator.label}
            </option>
          ))}
        </Select>
      </Field>

      <Field label="Value" htmlFor={`value-${spec.name}`}>
        {asBoolean ? (
          <Select
            id={`value-${spec.name}`}
            value={draft.value}
            onChange={(event) => onChange({ ...draft, value: event.target.value })}
          >
            <option value="true">Yes</option>
            <option value="false">No</option>
          </Select>
        ) : spec.choices && spec.choices.length > 0 ? (
          <Select
            id={`value-${spec.name}`}
            value={draft.value}
            onChange={(event) => onChange({ ...draft, value: event.target.value })}
          >
            <option value="">Choose…</option>
            {spec.choices.map((choice) => (
              <option key={choice.value} value={choice.value}>
                {choice.label}
              </option>
            ))}
          </Select>
        ) : (
          <Input
            id={`value-${spec.name}`}
            type={spec.kind === 'date' ? 'date' : spec.kind === 'number' ? 'number' : 'text'}
            value={draft.value}
            onChange={(event) => onChange({ ...draft, value: event.target.value })}
          />
        )}
      </Field>

      <Button type="button" variant="ghost" size="sm" onClick={onRemove}>
        Remove
      </Button>
    </div>
  );
}

export function ReportBuilder() {
  const [catalogue, setCatalogue] = useState<ReportDataset[] | null>(null);
  const [loadFailure, setLoadFailure] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  const [datasetKey, setDatasetKey] = useState('');
  const [columns, setColumns] = useState<string[]>([]);
  const [clauses, setClauses] = useState<DraftClause[]>([]);
  const [groupBy, setGroupBy] = useState('');
  const [measures, setMeasures] = useState<string[]>([]);

  const [result, setResult] = useState<ReportBuildResult | null>(null);
  const [running, setRunning] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listDatasets()
      .then((rows) => {
        if (!cancelled) {
          setCatalogue(rows);
          setLoadFailure(null);
        }
      })
      .catch((cause: unknown) => {
        if (!cancelled) setLoadFailure(errorMessage(cause, 'Could not read what can be built.'));
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const dataset = (catalogue ?? []).find((row) => row.key === datasetKey) ?? null;

  // Choosing a different dataset starts afresh: its columns, filters and
  // totals are its own, and carrying the last one's selections across would
  // ask for fields this dataset has never heard of.
  const [shownFor, setShownFor] = useState(datasetKey);
  if (shownFor !== datasetKey) {
    setColumns([]);
    setClauses([]);
    setGroupBy('');
    setMeasures([]);
    setResult(null);
    setFailure(null);
    setShownFor(datasetKey);
  }

  async function run() {
    if (!dataset) return;
    setRunning(true);
    setFailure(null);
    try {
      const filters: ReportFilterClause[] = clauses.map((draft) => ({
        field: draft.field,
        op: draft.op,
        value: valueFor(
          dataset.filters.find((spec) => spec.name === draft.field),
          draft,
        ),
      }));
      setResult(
        await buildReport({
          dataset: dataset.key,
          columns: groupBy ? undefined : columns,
          filters,
          group_by: groupBy || undefined,
          measures: groupBy ? (measures.length > 0 ? measures : ['count']) : undefined,
        }),
      );
    } catch (cause) {
      setFailure(errorMessage(cause, 'Could not run this report.'));
      setResult(null);
    } finally {
      setRunning(false);
    }
  }

  if (loadFailure) {
    return <ErrorState message={loadFailure} onRetry={() => setAttempt((value) => value + 1)} />;
  }
  if (!catalogue) return <LoadingState label="Reading what can be built" />;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Build a report"
        meta="Pick a thing, choose what to show, and ask it questions. Everything you can see is scoped to what you may see."
      >
        <Button type="button" disabled={!dataset || running} onClick={() => void run()}>
          {running ? 'Running…' : 'Run'}
        </Button>
      </PageHeader>

      <div className="max-w-sm">
        <Field label="Report on" htmlFor="dataset" required>
          <Select
            id="dataset"
            value={datasetKey}
            onChange={(event) => setDatasetKey(event.target.value)}
          >
            <option value="">Choose something</option>
            {catalogue.map((row) => (
              <option key={row.key} value={row.key}>
                {row.label}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      {dataset ? (
        <>
          <p className="text-sm text-ink-muted">{dataset.description}</p>

          <section className="space-y-2">
            <h2 className="text-sm font-semibold">Questions</h2>
            {clauses.map((draft, index) => {
              const spec = dataset.filters.find((row) => row.name === draft.field);
              if (!spec) return null;
              return (
                <FilterRow
                  key={`${draft.field}-${index}`}
                  spec={spec}
                  draft={draft}
                  onChange={(next) =>
                    setClauses((current) =>
                      current.map((row, position) => (position === index ? next : row)),
                    )
                  }
                  onRemove={() =>
                    setClauses((current) => current.filter((_, position) => position !== index))
                  }
                />
              );
            })}
            <Field label="Ask about" htmlFor="add-filter" optional>
              <Select
                id="add-filter"
                value=""
                onChange={(event) => {
                  const spec = dataset.filters.find((row) => row.name === event.target.value);
                  if (!spec) return;
                  setClauses((current) => [
                    ...current,
                    {
                      field: spec.name,
                      op: spec.operators[0]?.value ?? 'exact',
                      value: '',
                    },
                  ]);
                }}
              >
                <option value="">Add a question…</option>
                {dataset.filters.map((spec) => (
                  <option key={spec.name} value={spec.name}>
                    {spec.label}
                  </option>
                ))}
              </Select>
            </Field>
          </section>

          <section className="grid gap-4 sm:grid-cols-2">
            <Field
              label="Group by"
              htmlFor="group-by"
              optional
              hint="Leave empty for a list of records; choose one for totals per group."
            >
              <Select
                id="group-by"
                value={groupBy}
                onChange={(event) => setGroupBy(event.target.value)}
              >
                <option value="">Don&rsquo;t group — list the records</option>
                {dataset.columns.map((column) => (
                  <option key={column.name} value={column.name}>
                    {column.label}
                  </option>
                ))}
              </Select>
            </Field>

            {groupBy ? (
              <fieldset className="space-y-1">
                <legend className="text-xs font-medium text-ink">Totals</legend>
                {dataset.measures.map((measure) => (
                  <label key={measure.name} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      className="size-4 accent-[var(--color-action)]"
                      checked={measures.includes(measure.name)}
                      onChange={(event) =>
                        setMeasures((current) =>
                          event.target.checked
                            ? [...current, measure.name]
                            : current.filter((name) => name !== measure.name),
                        )
                      }
                    />
                    {measure.label}
                  </label>
                ))}
              </fieldset>
            ) : (
              <fieldset className="space-y-1">
                <legend className="text-xs font-medium text-ink">Show</legend>
                <p className="text-2xs text-ink-faint">
                  Nothing ticked shows every column this report has.
                </p>
                <div className="grid gap-1 sm:grid-cols-2">
                  {dataset.columns.map((column) => (
                    <label key={column.name} className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        className="size-4 accent-[var(--color-action)]"
                        checked={columns.includes(column.name)}
                        onChange={(event) =>
                          setColumns((current) =>
                            event.target.checked
                              ? [...current, column.name]
                              : current.filter((name) => name !== column.name),
                          )
                        }
                      />
                      {column.label}
                    </label>
                  ))}
                </div>
              </fieldset>
            )}
          </section>
        </>
      ) : null}

      {failure ? <Alert variant="error">{failure}</Alert> : null}

      {result ? (
        <section className="space-y-2">
          <h2 className="flex flex-wrap items-center gap-2 text-sm font-semibold">
            {result.rows.length} {result.rows.length === 1 ? 'row' : 'rows'}
            {result.grouped ? <Badge variant="info">grouped</Badge> : null}
            {result.truncated ? <Badge variant="warning">cut at the limit</Badge> : null}
          </h2>
          {result.truncated ? (
            <Alert variant="warning">
              This is the first {result.rows.length} rows, not all of them. Narrow it with another
              question, or export it.
            </Alert>
          ) : null}
          {result.rows.length === 0 ? (
            <p className="text-sm text-ink-muted">Nothing matched.</p>
          ) : (
            <TableWrapper>
              <Table>
                <thead>
                  <tr>
                    {result.columns.map((column) => (
                      <Th key={column.name}>{column.label}</Th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((row, index) => (
                    <tr key={index}>
                      {result.columns.map((column) => (
                        <Td key={column.name}>{String(row[column.name] ?? '—')}</Td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </Table>
            </TableWrapper>
          )}
        </section>
      ) : null}
    </div>
  );
}

export default function ReportBuilderPage() {
  return (
    <RequireAuth capability={Capability.reportViewAny}>
      <ReportBuilder />
    </RequireAuth>
  );
}
