'use client';

import { useEffect, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Select, Textarea } from '@/components/ui/input';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { ApiError, fieldErrors } from '@/lib/api';
import { DIFFICULTY_LABEL, QUESTION_TYPE_LABEL } from '@/lib/academic-labels';
import { createQuestion, listQuestions } from '@/lib/exams';
import { listBatches } from '@/lib/batches';
import type { BatchListRow, Difficulty, Question, QuestionType } from '@/types/api';

const BLANK_OPTION = { text: '', is_correct: false };

/** The question bank. Staff only — every row carries the answer. */
function QuestionBank() {
  const [rows, setRows] = useState<Question[]>([]);
  const [batches, setBatches] = useState<BatchListRow[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isOpen, setIsOpen] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [form, setForm] = useState({
    batch: '',
    question_type: 'mcq' as QuestionType,
    text: '',
    difficulty: 'medium' as Difficulty,
    marks: '2',
    negative_marks: '0',
    tags: '',
    explanation: '',
    answer_key: '',
  });
  const [options, setOptions] = useState([
    { text: '', is_correct: true },
    { ...BLANK_OPTION },
  ]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listQuestions(), listBatches({ page_size: 100 })])
      .then(([questions, batchPage]) => {
        if (cancelled) return;
        setRows(questions.results);
        setBatches(batchPage.results);
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

  const takesOptions = ['mcq', 'multiple', 'true_false'].includes(form.question_type);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const batch = batches.find((row) => row.id === form.batch);
    if (!batch) {
      setErrors({ batch: 'Choose a batch so the question belongs to its course.' });
      return;
    }
    setIsSaving(true);
    setErrors({});
    try {
      await createQuestion({
        course: batch.course_id,
        question_type: form.question_type,
        text: form.text,
        difficulty: form.difficulty,
        marks: form.marks,
        negative_marks: form.negative_marks,
        tags: form.tags
          .split(',')
          .map((tag) => tag.trim().toLowerCase().replace(/\s+/g, '-'))
          .filter(Boolean),
        explanation: form.explanation || undefined,
        answer_key:
          form.question_type === 'short_answer'
            ? form.answer_key.split(',').map((value) => value.trim()).filter(Boolean)
            : undefined,
        options:
          takesOptions && form.question_type !== 'true_false'
            ? options.filter((option) => option.text.trim())
            : undefined,
      });
      setIsOpen(false);
      setRows((await listQuestions()).results);
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) return <LoadingState label="Loading the question bank…" rows={5} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load the question bank"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Question bank</h1>
          <p className="text-sm text-muted-foreground">
            Reusable questions. Examinations draw from here, and freeze what they drew.
          </p>
        </div>
        <Button type="button" onClick={() => setIsOpen((open) => !open)}>
          {isOpen ? 'Cancel' : 'New question'}
        </Button>
      </div>

      {isOpen ? (
        <Card>
          <CardHeader>
            <CardTitle>New question</CardTitle>
            <CardDescription>
              A question with no correct answer would mark every candidate wrong, so the server
              refuses one.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={submit}>
              {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}
              {errors.options ? <Alert variant="error">{errors.options}</Alert> : null}

              <Field label="Batch" htmlFor="batch" error={errors.batch ?? errors.course}>
                <Select
                  id="batch"
                  required
                  value={form.batch}
                  onChange={(event) => setForm({ ...form, batch: event.target.value })}
                >
                  <option value="">Choose a batch…</option>
                  {batches.map((batch) => (
                    <option key={batch.id} value={batch.id}>
                      {batch.code} · {batch.course_title}
                    </option>
                  ))}
                </Select>
              </Field>

              <Field label="Type" htmlFor="question_type" error={errors.question_type}>
                <Select
                  id="question_type"
                  value={form.question_type}
                  onChange={(event) =>
                    setForm({ ...form, question_type: event.target.value as QuestionType })
                  }
                >
                  {Object.entries(QUESTION_TYPE_LABEL).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </Field>

              <Field label="Question" htmlFor="text" error={errors.text}>
                <Textarea
                  id="text"
                  required
                  rows={3}
                  value={form.text}
                  onChange={(event) => setForm({ ...form, text: event.target.value })}
                />
              </Field>

              {takesOptions && form.question_type !== 'true_false' ? (
                <div className="space-y-2">
                  <p className="text-sm font-medium">Options</p>
                  {options.map((option, index) => (
                    <div key={index} className="flex items-center gap-2">
                      <Input
                        aria-label={`Option ${index + 1}`}
                        value={option.text}
                        onChange={(event) => {
                          const next = [...options];
                          next[index] = { ...option, text: event.target.value };
                          setOptions(next);
                        }}
                      />
                      <label className="flex shrink-0 items-center gap-1 text-xs">
                        <input
                          type="checkbox"
                          aria-label={`Option ${index + 1} is correct`}
                          checked={option.is_correct}
                          onChange={(event) => {
                            const next = options.map((item, position) =>
                              form.question_type === 'mcq'
                                ? { ...item, is_correct: position === index && event.target.checked }
                                : position === index
                                  ? { ...item, is_correct: event.target.checked }
                                  : item,
                            );
                            setOptions(next);
                          }}
                        />
                        correct
                      </label>
                    </div>
                  ))}
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => setOptions([...options, { ...BLANK_OPTION }])}
                  >
                    Add an option
                  </Button>
                </div>
              ) : null}

              {form.question_type === 'short_answer' ? (
                <Field
                  label="Accepted answers"
                  htmlFor="answer_key"
                  error={errors.answer_key}
                  hint="Comma separated. Matched ignoring case and spacing."
                >
                  <Input
                    id="answer_key"
                    value={form.answer_key}
                    onChange={(event) => setForm({ ...form, answer_key: event.target.value })}
                  />
                </Field>
              ) : null}

              <Field label="Difficulty" htmlFor="difficulty" error={errors.difficulty}>
                <Select
                  id="difficulty"
                  value={form.difficulty}
                  onChange={(event) =>
                    setForm({ ...form, difficulty: event.target.value as Difficulty })
                  }
                >
                  {Object.entries(DIFFICULTY_LABEL).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </Field>

              <Field label="Marks" htmlFor="marks" error={errors.marks}>
                <Input
                  id="marks"
                  type="number"
                  min="0.01"
                  step="0.01"
                  value={form.marks}
                  onChange={(event) => setForm({ ...form, marks: event.target.value })}
                />
              </Field>

              <Field
                label="Negative marks"
                htmlFor="negative_marks"
                error={errors.negative_marks}
                hint="Deducted only when the examination has negative marking on."
              >
                <Input
                  id="negative_marks"
                  type="number"
                  min="0"
                  step="0.01"
                  value={form.negative_marks}
                  onChange={(event) => setForm({ ...form, negative_marks: event.target.value })}
                />
              </Field>

              <Field label="Tags" htmlFor="tags" error={errors.tags} hint="Comma separated.">
                <Input
                  id="tags"
                  value={form.tags}
                  onChange={(event) => setForm({ ...form, tags: event.target.value })}
                />
              </Field>

              <Field label="Explanation" htmlFor="explanation" error={errors.explanation}>
                <Textarea
                  id="explanation"
                  rows={2}
                  value={form.explanation}
                  onChange={(event) => setForm({ ...form, explanation: event.target.value })}
                />
              </Field>

              <Button type="submit" disabled={isSaving || !form.batch}>
                {isSaving ? 'Saving…' : 'Add to the bank'}
              </Button>
            </form>
          </CardContent>
        </Card>
      ) : null}

      {rows.length === 0 ? (
        <EmptyState
          title="The bank is empty"
          description="Add questions here, then draw examinations from them."
        />
      ) : (
        <TableWrapper>
          <Table>
            <thead>
              <tr>
                <Th>Question</Th>
                <Th>Type</Th>
                <Th>Marks</Th>
                <Th>Tags</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <Td>
                    <div className="font-medium">{row.text}</div>
                    {row.is_active ? null : <Badge variant="neutral">Retired</Badge>}
                  </Td>
                  <Td>
                    {QUESTION_TYPE_LABEL[row.question_type]}
                    <div className="text-xs text-muted-foreground">
                      {DIFFICULTY_LABEL[row.difficulty]}
                    </div>
                  </Td>
                  <Td>
                    {row.marks}
                    {Number(row.negative_marks) > 0 ? ` / −${row.negative_marks}` : ''}
                  </Td>
                  <Td>{row.tags.join(', ') || '—'}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </TableWrapper>
      )}
    </div>
  );
}

export default function QuestionBankPage() {
  return (
    <RequireAuth>
      <QuestionBank />
    </RequireAuth>
  );
}
