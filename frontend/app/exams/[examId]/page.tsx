'use client';

import { useParams } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/input';
import { ApiError, errorMessage } from '@/lib/api';
import { QUESTION_TYPE_LABEL, formatCountdown } from '@/lib/academic-labels';
import { getAttemptPaper, saveAnswer, startAttempt, submitAttempt } from '@/lib/exams';
import type { AttemptPaper, CandidateQuestion } from '@/types/api';

/**
 * The examination player.
 *
 * Two things are deliberate about it. Every answer is saved to the server as it
 * is given, so a refresh or a closed browser loses nothing; and the clock is
 * only ever *displayed* here — `seconds_remaining` comes from the server with
 * every response, and the countdown below simply ticks it down between calls.
 * A candidate who changes their device clock changes what they see and nothing
 * else.
 */
function ExamPlayer({ examId }: { examId: string }) {
  const [paper, setPaper] = useState<AttemptPaper | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [remaining, setRemaining] = useState(0);
  const [answers, setAnswers] = useState<Record<string, CandidateQuestion>>({});
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  // The server is idempotent about starting, but there is no reason to ask it
  // twice: React re-runs effects in development, and a second request would
  // race the first for no benefit.
  const started = useRef(false);

  const adopt = useCallback((next: AttemptPaper) => {
    setPaper(next);
    setRemaining(next.attempt.seconds_remaining);
    setAnswers(Object.fromEntries(next.questions.map((question) => [question.id, question])));
  }, []);

  useEffect(() => {
    // Started exactly once. There is deliberately no cancel-on-unmount flag:
    // React re-runs effects in development, and discarding the first response
    // would leave the screen with a started attempt it never adopted.
    if (started.current) return;
    started.current = true;

    startAttempt(examId)
      .then(adopt)
      .catch((cause: unknown) => {
        setError(cause instanceof ApiError ? cause : null);
        // The envelope message is generic for a validation failure; the reason
        // a candidate needs ("this examination is not open") is in the details.
        setFormError(errorMessage(cause, 'The examination could not be opened.'));
      })
      .finally(() => setIsLoading(false));
  }, [examId, adopt]);

  useEffect(() => {
    if (!paper || paper.attempt.status !== 'in_progress') return undefined;
    timer.current = setInterval(() => {
      setRemaining((seconds) => Math.max(0, seconds - 1));
    }, 1000);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [paper]);

  async function record(question: CandidateQuestion, payload: Partial<CandidateQuestion>) {
    const next = { ...question, ...payload };
    setAnswers((current) => ({ ...current, [question.id]: next }));
    setFormError(null);
    if (!paper) return;
    try {
      await saveAnswer(paper.attempt.id, question.id, {
        selected_options: next.selected_options,
        text_answer: next.text_answer,
      });
      setSavedAt(new Date().toLocaleTimeString());
    } catch (cause) {
      setFormError(errorMessage(cause, 'That answer could not be saved.'));
      // The server is the record. Re-read rather than trusting local state.
      try {
        adopt(await getAttemptPaper(paper.attempt.id));
      } catch {
        /* the error above already says what happened */
      }
    }
  }

  async function finish() {
    if (!paper) return;
    setIsSubmitting(true);
    setFormError(null);
    try {
      await submitAttempt(paper.attempt.id);
      adopt(await getAttemptPaper(paper.attempt.id));
    } catch (cause) {
      setFormError(errorMessage(cause, 'The paper could not be submitted.'));
    } finally {
      setIsSubmitting(false);
    }
  }

  if (isLoading) return <LoadingState label="Opening the examination…" rows={6} />;
  if (error) {
    return (
      <ErrorState
        title="Could not open the examination"
        message={formError ?? error.message}
        requestId={error.requestId || undefined}
      />
    );
  }
  if (!paper) return null;

  const finished = paper.attempt.status !== 'in_progress';

  return (
    <div className="stagger space-y-6">
      <div className="animate-rise-in flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <span className="font-mono text-xs text-muted-foreground">
            {paper.attempt.exam_code}
          </span>
          <h1 className="text-2xl font-semibold tracking-tight">{paper.attempt.exam_title}</h1>
          <p className="text-sm text-muted-foreground">
            Attempt {paper.attempt.attempt_number} · {paper.questions.length} questions
          </p>
        </div>
        <div className="text-right">
          <div className="text-xs text-muted-foreground">Time remaining</div>
          <div className="font-mono text-2xl" data-testid="exam-countdown">
            {finished ? '—' : formatCountdown(remaining)}
          </div>
          {savedAt ? (
            <div className="text-xs text-muted-foreground" data-testid="autosave-marker">
              Saved at {savedAt}
            </div>
          ) : null}
        </div>
      </div>

      {formError ? <Alert variant="error">{formError}</Alert> : null}

      {finished ? (
        <Alert variant="success" role="status" className="animate-rise-in">
          Your paper has been submitted. Results appear once your trainer releases them.
        </Alert>
      ) : null}

      {paper.questions.map((question) => {
        const current = answers[question.id] ?? question;
        return (
          <Card key={question.id} data-testid="exam-question" className="animate-rise-in">
            <CardHeader className="gap-1">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="neutral">Question {question.position + 1}</Badge>
                {question.section ? <Badge variant="neutral">{question.section}</Badge> : null}
                <span className="text-xs text-muted-foreground">
                  {question.marks} marks
                  {Number(question.negative_marks) > 0
                    ? ` · −${question.negative_marks} if wrong`
                    : ''}
                </span>
              </div>
              <CardTitle className="text-base">{question.text}</CardTitle>
              <CardDescription>{QUESTION_TYPE_LABEL[question.question_type]}</CardDescription>
            </CardHeader>

            <CardContent>
              {question.options.length > 0 ? (
                <fieldset className="space-y-2" disabled={finished}>
                  <legend className="sr-only">Answer for question {question.position + 1}</legend>
                  {question.options.map((option) => {
                    const many = question.question_type === 'multiple';
                    const checked = current.selected_options.includes(option.id);
                    return (
                      <label key={option.id} className="flex items-center gap-2 text-sm">
                        <input
                          type={many ? 'checkbox' : 'radio'}
                          name={`question-${question.id}`}
                          checked={checked}
                          onChange={(event) => {
                            const selected = many
                              ? event.target.checked
                                ? [...current.selected_options, option.id]
                                : current.selected_options.filter((id) => id !== option.id)
                              : [option.id];
                            void record(current, { selected_options: selected });
                          }}
                        />
                        {option.text}
                      </label>
                    );
                  })}
                </fieldset>
              ) : (
                <Textarea
                  aria-label={`Answer for question ${question.position + 1}`}
                  rows={question.question_type === 'long_answer' ? 6 : 2}
                  disabled={finished}
                  value={current.text_answer}
                  onChange={(event) =>
                    setAnswers((all) => ({
                      ...all,
                      [question.id]: { ...current, text_answer: event.target.value },
                    }))
                  }
                  onBlur={(event) => void record(current, { text_answer: event.target.value })}
                />
              )}
            </CardContent>
          </Card>
        );
      })}

      {!finished ? (
        <Button type="button" onClick={finish} disabled={isSubmitting}>
          {isSubmitting ? 'Submitting…' : 'Submit my paper'}
        </Button>
      ) : null}
    </div>
  );
}

export default function ExamPage() {
  const params = useParams<{ examId: string }>();
  return (
    <RequireAuth>
      <ExamPlayer examId={params.examId} />
    </RequireAuth>
  );
}
