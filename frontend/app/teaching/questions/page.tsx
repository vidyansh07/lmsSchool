'use client';

import { useEffect, useState } from 'react';

import { ListToolbar } from '@/components/list-toolbar';
import { Pagination } from '@/components/pagination';
import { RequireAuth } from '@/components/require-auth';
import { Capability } from '@/lib/capabilities';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Select, Textarea } from '@/components/ui/input';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { useList } from '@/hooks/use-list';
import { ApiError, fieldErrors } from '@/lib/api';
import { DIFFICULTY_LABEL, QUESTION_TYPE_LABEL } from '@/lib/academic-labels';
import { formatNumber, NO_DATA } from '@/lib/format';
import { createQuestion, listQuestions } from '@/lib/exams';
import { listBatches } from '@/lib/batches';
import type { BatchListRow, Difficulty, Question, QuestionType } from '@/types/api';

const BLANK_OPTION = { text: '', is_correct: false };

/**
 * A tag as the bank stores it.
 *
 * The create form writes tags lowercased and hyphenated, and the server matches
 * a *whole* tag (`tags__contains=[value]`), not a prefix — so "Shell Scripting"
 * typed into the filter has to become "shell-scripting" or it matches nothing.
 * Shared with the filter below rather than spelled twice, because the two have
 * to agree by definition.
 *
 * It must only ever be applied to a *finished* value. Applied per keystroke it
 * eats the space between two words — "Shell " trims to "shell", and the next
 * keystroke lands as "shells" rather than "shell-s" — which is why the filter
 * keeps the raw text in `tagDraft` and normalises once the typing settles.
 */
function normaliseTag(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, '-');
}

/**
 * The question bank. Staff only — every row carries the answer.
 *
 * Server-filtered and server-paginated through `useList`, like every other
 * list in the product. It used to call `listQuestions()` with no query at all
 * and render `results`, so a trainer with fifty-seven questions saw
 * twenty-five of them, in one fixed order, with nothing on the page to reach
 * the rest — and the filters the API has always supported (`question_type`,
 * `difficulty`, `tag`, `search`) were unreachable from the only screen that
 * reads the bank.
 */
function QuestionBank() {
  const list = useList<Question>(listQuestions);
  const [tagDraft, setTagDraft] = useState('');
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

  // The tag box keeps what was typed and hands the *normalised* tag to the
  // query, debounced the same 300 ms as `ListToolbar`'s own search box — one
  // request per tag rather than one per keystroke.
  useEffect(() => {
    const tag = normaliseTag(tagDraft);
    if (tag === (list.query.tag ?? '')) return;
    const timer = setTimeout(() => list.setQuery({ tag }), 300);
    return () => clearTimeout(timer);
    // `list.setQuery` is stable; `list.query.tag` is the value being compared.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tagDraft, list.query.tag]);

  // Only the batch list for the create form lives here now; the questions
  // themselves are `useList`'s business, one page at a time.
  useEffect(() => {
    let cancelled = false;
    listBatches({ page_size: 100 })
      .then((batchPage) => {
        if (!cancelled) setBatches(batchPage.results);
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
  // Which empty state to show: "nothing matches" reads as a bug when the bank
  // really is empty, and "the bank is empty" reads as a bug when it is not.
  const hasFilters = Boolean(
    list.query.search || list.query.question_type || list.query.difficulty || list.query.tag,
  );

  // The create form normalises what it writes the same way the filter does.
  const formTags = form.tags.split(',').map(normaliseTag).filter(Boolean);

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
        tags: formTags,
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
      // Back to page 1 of the current filter, where a brand-new question is —
      // the list orders newest first.
      list.setQuery({});
      list.reload();
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSaving(false);
    }
  }

  const failure = error ?? list.error;
  if (isLoading && list.isLoading) {
    return <LoadingState label="Loading the question bank…" rows={5} />;
  }
  if (failure) {
    return (
      <ErrorState
        title="Could not load the question bank"
        message={failure.message}
        requestId={failure.requestId || undefined}
        onRetry={list.reload}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Question bank</h1>
          <p className="text-sm text-ink-muted">
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
            <CardTitle as="h2">New question</CardTitle>
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

      <ListToolbar
        search={String(list.query.search ?? '')}
        onSearchChange={(value) => list.setQuery({ search: value })}
        placeholder="Words in the question"
      >
        <div>
          <label htmlFor="filter-type" className="mb-1.5 block text-sm font-medium">
            Type
          </label>
          <Select
            id="filter-type"
            value={String(list.query.question_type ?? '')}
            onChange={(event) => list.setQuery({ question_type: event.target.value })}
          >
            <option value="">Any type</option>
            {Object.entries(QUESTION_TYPE_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <label htmlFor="filter-difficulty" className="mb-1.5 block text-sm font-medium">
            Difficulty
          </label>
          <Select
            id="filter-difficulty"
            value={String(list.query.difficulty ?? '')}
            onChange={(event) => list.setQuery({ difficulty: event.target.value })}
          >
            <option value="">Any difficulty</option>
            {Object.entries(DIFFICULTY_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <label htmlFor="filter-tag" className="mb-1.5 block text-sm font-medium">
            Tag
          </label>
          <Input
            id="filter-tag"
            value={tagDraft}
            placeholder="one tag"
            onChange={(event) => setTagDraft(event.target.value)}
          />
        </div>
        <div>
          <label htmlFor="filter-active" className="mb-1.5 block text-sm font-medium">
            In use
          </label>
          <Select
            id="filter-active"
            value={String(list.query.is_active ?? '')}
            onChange={(event) => list.setQuery({ is_active: event.target.value })}
          >
            <option value="">Live and retired</option>
            <option value="true">Live only</option>
            <option value="false">Retired only</option>
          </Select>
        </div>
      </ListToolbar>

      {list.isLoading ? (
        <LoadingState label="Loading the question bank…" rows={5} />
      ) : !list.data || list.data.count === 0 ? (
        <EmptyState
          title={hasFilters ? 'No question matches that' : 'The bank is empty'}
          description={
            hasFilters
              ? 'Widen the filters, or clear the search.'
              : 'Add questions here, then draw examinations from them.'
          }
        />
      ) : (
        <TableWrapper className="max-h-[min(36rem,65vh)] overflow-y-auto">
          <Table>
            <thead>
              <tr>
                <Th className="sticky top-0 z-10 bg-sunken">Question</Th>
                <Th className="sticky top-0 z-10 bg-sunken">Type</Th>
                <Th className="sticky top-0 z-10 bg-sunken text-right">Marks</Th>
                <Th className="sticky top-0 z-10 bg-sunken">Tags</Th>
              </tr>
            </thead>
            <tbody className="">
              {list.data.results.map((row) => (
                <tr key={row.id} className="animate-fade-in transition-colors hover:bg-sunken/40">
                  <Td>
                    <div className="font-medium">{row.text}</div>
                    {row.is_active ? null : <Badge variant="neutral">Retired</Badge>}
                  </Td>
                  <Td>
                    {QUESTION_TYPE_LABEL[row.question_type]}
                    <div className="text-xs text-ink-muted">
                      {DIFFICULTY_LABEL[row.difficulty]}
                    </div>
                  </Td>
                  <Td className="text-right tabular-nums">
                    {formatNumber(row.marks)}
                    {Number(row.negative_marks) > 0 ? ` / −${formatNumber(row.negative_marks)}` : ''}
                  </Td>
                  <Td>{row.tags.join(', ') || NO_DATA}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </TableWrapper>
      )}

      {list.data ? (
        <Pagination
          page={list.data.page}
          totalPages={list.data.total_pages}
          count={list.data.count}
          pageSize={list.data.page_size}
          onPageChange={list.setPage}
        />
      ) : null}
    </div>
  );
}

export default function QuestionBankPage() {
  return (
    <RequireAuth capability={Capability.questionViewAny} roles={["trainer"]}>
      <QuestionBank />
    </RequireAuth>
  );
}
