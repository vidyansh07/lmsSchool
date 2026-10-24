'use client';

/**
 * Import Students: upload the batch sheet a centre already keeps, see what it
 * would do, then let it do it.
 *
 * Two steps, and the first is not optional. The preview is produced by the
 * same code the import runs — inside a transaction that is then rolled back —
 * so what it says is what will happen. An importer that wrote first and
 * reported afterwards would be a spreadsheet typo turned into thirty student
 * records.
 *
 * The report is read as a whole: the counts plus the problems account for
 * every row in the file. A problem names the sheet and the row it came from,
 * because the fix is in the spreadsheet and somebody has to find the cell.
 */

import { useState } from 'react';
import { Upload } from 'lucide-react';

import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { errorMessage } from '@/lib/api';
import { importBatchSheet, type BatchSheetImportResult } from '@/lib/batches';

export function ImportSheetDialog({
  open,
  onClose,
  onImported,
}: {
  open: boolean;
  onClose: () => void;
  onImported: (summary: string) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<BatchSheetImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  // Reopening starts afresh; reset by key during render rather than from an
  // effect, as the other dialogs in this app do.
  const [openedFor, setOpenedFor] = useState(open);
  if (openedFor !== open) {
    setFile(null);
    setPreview(null);
    setFailure(null);
    setOpenedFor(open);
  }

  async function run(dryRun: boolean) {
    if (!file) {
      setFailure('Choose the sheet first.');
      return;
    }
    setBusy(true);
    setFailure(null);
    try {
      const result = await importBatchSheet(file, { dryRun });
      if (dryRun) {
        setPreview(result);
        return;
      }
      onImported(
        `${result.batches_created} batch(es) opened, ${result.students_created} student(s) added, ` +
          `${result.enrolments_created} enrolled.`,
      );
    } catch (cause) {
      setFailure(errorMessage(cause, 'The sheet could not be imported.'));
    } finally {
      setBusy(false);
    }
  }

  const counts = preview
    ? [
        ['Batches opened', preview.batches_created],
        ['Batches already there', preview.batches_matched],
        ['Students added', preview.students_created],
        ['Students already on the system', preview.students_matched],
        ['Enrolled', preview.enrolments_created],
        ['Already enrolled', preview.enrolments_existing],
      ]
    : [];

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : onClose())}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Import Students</DialogTitle>
          <DialogDescription>
            The batch sheet as it is kept: a banner with the course and the class time, the
            trainer, the starting date, then the roster. Several batches in one file is normal.
          </DialogDescription>
        </DialogHeader>

        {failure ? <Alert variant="error">{failure}</Alert> : null}

        <Field
          label="Batch sheet (.xlsx)"
          htmlFor="import-file"
          hint="Nothing is written until you have seen what it would do."
        >
          <Input
            id="import-file"
            type="file"
            accept=".xlsx,.xlsm"
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setPreview(null);
            }}
          />
        </Field>

        {preview ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {counts.map(([label, value]) => (
                <div key={String(label)} className="rounded-card border border-line px-3 py-2">
                  <p className="text-2xs uppercase tracking-wide text-ink-faint">{label}</p>
                  <p className="text-lg font-semibold tabular-nums">{value}</p>
                </div>
              ))}
            </div>

            {preview.batches.length > 0 ? (
              <p className="text-sm text-ink-muted">
                Batches: {preview.batches.join(', ')}
              </p>
            ) : null}

            {preview.problems.length > 0 ? (
              <section className="space-y-2">
                <h3 className="flex items-center gap-2 text-sm font-medium">
                  Rows this could not use
                  <Badge variant="warning">{preview.problems.length}</Badge>
                </h3>
                <TableWrapper>
                  <Table>
                    <thead>
                      <tr>
                        <Th>Sheet</Th>
                        <Th>Row</Th>
                        <Th>What is wrong</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.problems.map((problem, index) => (
                        <tr key={`${problem.sheet}-${problem.row}-${index}`}>
                          <Td>{problem.sheet}</Td>
                          <Td className="tabular-nums">{problem.row ?? '—'}</Td>
                          <Td>{problem.message}</Td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </TableWrapper>
                <p className="text-xs text-ink-muted">
                  Importing now takes everything else and leaves these; fix the cells and import
                  the sheet again, which adds what was missing rather than duplicating what was
                  not.
                </p>
              </section>
            ) : (
              <Alert variant="success">Every row in the file can be used.</Alert>
            )}
          </div>
        ) : null}

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={busy || !file}
            onClick={() => void run(true)}
          >
            <Upload className="size-4" aria-hidden="true" />
            {busy && !preview ? 'Reading…' : 'Preview'}
          </Button>
          <Button type="button" disabled={busy || !preview} onClick={() => void run(false)}>
            {busy && preview ? 'Importing…' : 'Import'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
