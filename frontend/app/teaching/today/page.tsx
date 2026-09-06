'use client';

/**
 * The trainer's "Today's Class" workspace — one screen, end of class, no
 * navigating away.
 *
 * Two components, two jobs:
 *
 * - `TodayWorkspace` only decides *which* class. It reads `?session=` from
 *   the URL rather than holding the choice in local state, so a backdated
 *   catch-up is a real, reloadable, bookmarkable place rather than a modal
 *   that forgets itself on refresh — the brief is explicit that the screen
 *   must not fight a trainer over the date. With exactly one class today it
 *   skips the picker by replacing straight to that class's URL; with zero or
 *   several, `ClassPicker` handles both "today" and "any other day" with the
 *   same date field, because a backdated class is not a different feature,
 *   just a different date.
 * - `ClassWorkspace` owns one class end to end: the register, the planned
 *   vs. actual topic, the daily status report and the quick assessment /
 *   assignment actions. It is keyed by `sessionId` at the call site so
 *   switching classes remounts it — resetting a dozen pieces of local state
 *   by hand invites exactly the bug where yesterday's marks bleed into
 *   today's class, and a fresh mount cannot have that bug.
 *
 * Autosave has two layers. `localStorage` (see `lib/dsr.ts`) is written
 * synchronously on every change once the trainer has actually edited
 * something — cheap enough to not debounce, and it is the only layer that
 * also carries in-progress register marks, since the backend has no draft
 * concept for attendance. The DSR fields are *also* pushed to the server
 * draft, debounced, wherever `is_editable` allows it — that is the "save to
 * the server draft where the API allows" half of the brief. Finishing the
 * class does not depend on either autosave having run: it always resends
 * the register (a no-op per row if nothing changed — see
 * `apps.attendance.services.mark_attendance`) and always writes the DSR with
 * `submit: true`, so a trainer who closed and reopened the tab twice still
 * finishes in exactly one action.
 *
 * "Finish class" is deliberately three sequential requests (register, topic,
 * report) rather than one endpoint, because the backend does not offer one —
 * but each step is fast, each surfaces its own error against its own part of
 * the screen, and a step that fails stops the sequence rather than
 * submitting a report describing an unsaved register.
 */
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useMemo, useRef, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { ErrorState, LoadingState } from '@/components/states';
import {
  ClassHeader,
  initialTopicSelection,
  SKIP_TOPIC_VALUE,
} from '@/components/teaching/class-header';
import { ClassPicker } from '@/components/teaching/class-picker';
import { ClassWorkPanel } from '@/components/teaching/class-work-panel';
import { DsrPanel } from '@/components/teaching/dsr-panel';
import { RegisterEditor } from '@/components/teaching/register-editor';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useDebouncedValue } from '@/hooks/use-debounced-value';
import { useKeyboardShortcuts } from '@/hooks/use-keyboard-shortcuts';
import { getRegister, listTodaySessions, markAttendance } from '@/lib/academics';
import { ApiError, fieldErrors } from '@/lib/api';
import { getBatch } from '@/lib/batches';
import { listModules } from '@/lib/courses';
import {
  clearDsrDraft,
  getSessionDsr,
  getSessionWithTopic,
  readDsrDraft,
  recordTopic,
  startDsr,
  toWritePayload,
  updateDsr,
  writeDsrDraft,
  type DSR,
  type DSRWritePayload,
  type SessionWithTopic,
} from '@/lib/dsr';
import { fallback, formatDate, formatNumber } from '@/lib/format';
import type { AttendanceStatus, BatchDetail, ClassSession, Module, Register } from '@/types/api';

const TODAY_PATH = '/teaching/today';

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function ClassCompleteSummary({
  session,
  present,
  absent,
  onChangeClass,
}: {
  session: SessionWithTopic;
  present: number;
  absent: number;
  onChangeClass?: () => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Class complete</CardTitle>
        <CardDescription>
          {fallback(session.batch_name)} · {formatDate(session.session_date)}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Alert variant="success" role="status">
          The register is saved and the report has been sent for review.
        </Alert>
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <span>
            <span className="text-muted-foreground">Present: </span>
            <strong className="tabular-nums">{formatNumber(present)}</strong>
          </span>
          <span>
            <span className="text-muted-foreground">Absent: </span>
            <strong className="tabular-nums">{formatNumber(absent)}</strong>
          </span>
        </div>
        {onChangeClass ? (
          <Button type="button" variant="outline" onClick={onChangeClass}>
            Back to today&rsquo;s classes
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}

/**
 * One class, start to finish. Exported (alongside `TodayWorkspace`) so tests
 * can mount a class directly by id, the same way `RegistrationWizard` is
 * tested in `app/admissions/new/page.tsx` — without needing to drive
 * `next/navigation` for every behaviour that has nothing to do with routing.
 */
export function ClassWorkspace({
  sessionId,
  onChangeClass,
}: {
  sessionId: string;
  onChangeClass?: () => void;
}) {
  // Read once, at mount — this is the local safety net a reload restores
  // from, not a value that should be re-read while the trainer is working.
  const [localDraft] = useState(() => readDsrDraft(sessionId));

  const [session, setSession] = useState<SessionWithTopic | null>(null);
  const [register, setRegister] = useState<Register | null>(null);
  const [dsr, setDsr] = useState<DSR | null>(null);
  const [coreError, setCoreError] = useState<ApiError | null>(null);
  const [isLoadingCore, setIsLoadingCore] = useState(true);
  const [coreAttempt, setCoreAttempt] = useState(0);

  const [batch, setBatch] = useState<BatchDetail | null>(null);
  const [modules, setModules] = useState<Module[]>([]);
  const [isLoadingBatchInfo, setIsLoadingBatchInfo] = useState(false);

  const [marks, setMarks] = useState<Record<string, AttendanceStatus>>({});
  const [draft, setDraft] = useState<DSRWritePayload>({});
  const [topicSelection, setTopicSelection] = useState('');
  const [isDirty, setIsDirty] = useState(Boolean(localDraft));

  const [isSavingDraft, setIsSavingDraft] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState<string | null>(null);

  const [isSavingRegister, setIsSavingRegister] = useState(false);
  const [registerSaved, setRegisterSaved] = useState<string | null>(null);
  const [registerError, setRegisterError] = useState<string | null>(null);
  const [topicError, setTopicError] = useState<string | null>(null);
  const [dsrFieldErrors, setDsrFieldErrors] = useState<Record<string, string>>({});

  const [isFinishing, setIsFinishing] = useState(false);
  const [finished, setFinished] = useState(false);
  const [finishedCounts, setFinishedCounts] = useState({ present: 0, absent: 0 });

  // --- Load the class -------------------------------------------------------

  useEffect(() => {
    let cancelled = false;
    Promise.all([getSessionWithTopic(sessionId), getRegister(sessionId), getSessionDsr(sessionId)])
      .then(([sessionData, registerData, dsrData]) => {
        if (cancelled) return;
        setSession(sessionData);
        setRegister(registerData);
        setDsr(dsrData);
        setTopicSelection(localDraft?.topicSelection ?? initialTopicSelection(sessionData));
        setMarks(
          Object.fromEntries(
            registerData.entries
              .map((entry): [string, AttendanceStatus | null] => [
                entry.enrollment_id,
                localDraft?.marks[entry.enrollment_id] ?? entry.status,
              ])
              .filter((pair): pair is [string, AttendanceStatus] => pair[1] !== null),
          ),
        );
        setDraft(localDraft?.fields ?? toWritePayload(dsrData));
      })
      .catch((cause: unknown) => {
        if (!cancelled) setCoreError(cause instanceof ApiError ? cause : null);
      })
      .finally(() => {
        if (!cancelled) setIsLoadingCore(false);
      });
    return () => {
      cancelled = true;
    };
    // `localDraft` is read once at mount and intentionally not a dependency —
    // re-running this fetch must not re-seed already-edited state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, coreAttempt]);

  // The course a class's batch runs — secondary (lesson picker, quick
  // assignment creation), so its own failure never blocks the class above.
  // The "start loading" flip happens here, during render, when the batch id
  // this hook has already started fetching for falls behind the session's
  // current one — the same "adjust state during render" shape `use-list.ts`
  // uses for its own request-identity reset, kept out of the effect body
  // itself so nothing sets state synchronously inside it.
  const batchInfoKey = session?.batch_id ?? null;
  const [loadedBatchInfoKey, setLoadedBatchInfoKey] = useState<string | null>(null);
  if (batchInfoKey && loadedBatchInfoKey !== batchInfoKey) {
    setLoadedBatchInfoKey(batchInfoKey);
    setIsLoadingBatchInfo(true);
  }

  useEffect(() => {
    if (!batchInfoKey) return;
    let cancelled = false;
    getBatch(batchInfoKey)
      .then((batchData) => {
        if (cancelled) return undefined;
        setBatch(batchData);
        return listModules(batchData.course_id);
      })
      .then((moduleData) => {
        if (!cancelled && moduleData) setModules(moduleData);
      })
      .catch(() => {
        // Degrade quietly — see the module docstring.
      })
      .finally(() => {
        if (!cancelled) setIsLoadingBatchInfo(false);
      });
    return () => {
      cancelled = true;
    };
  }, [batchInfoKey]);

  // --- Live counts (always the number that will actually be submitted) -----

  const liveCounts = useMemo(() => {
    if (!register) return { present: 0, absent: 0, student: 0 };
    let present = 0;
    let absent = 0;
    for (const entry of register.entries) {
      const status = marks[entry.enrollment_id];
      if (status === 'present' || status === 'late') present += 1;
      else if (status === 'absent') absent += 1;
    }
    return { present, absent, student: register.entries.length };
  }, [register, marks]);

  // --- Local draft: synchronous, no debounce (see the module docstring) ----

  useEffect(() => {
    if (!isDirty) return;
    writeDsrDraft(sessionId, {
      savedAt: new Date().toISOString(),
      fields: draft,
      marks,
      topicSelection,
    });
  }, [sessionId, isDirty, draft, marks, topicSelection]);

  // --- Server draft: debounced, DSR fields only -----------------------------

  const debouncedDraft = useDebouncedValue(draft, 1200);

  // As with the batch-info load above, "a new debounced value just landed
  // and has not been sent yet" is decided during render (comparing against
  // the last value this hook started saving), not with a synchronous
  // setState at the top of the effect.
  const draftAutosaveDue = isDirty && Boolean(dsr?.is_editable);
  const [savingDraftFor, setSavingDraftFor] = useState<DSRWritePayload | null>(null);
  if (draftAutosaveDue && savingDraftFor !== debouncedDraft) {
    setSavingDraftFor(debouncedDraft);
    setIsSavingDraft(true);
  }

  useEffect(() => {
    if (!isDirty || !dsr || !dsr.is_editable) return;
    let cancelled = false;
    const payload: DSRWritePayload = {
      ...debouncedDraft,
      present_count: liveCounts.present,
      absent_count: liveCounts.absent,
      student_count: liveCounts.student,
    };
    const save = dsr.id ? updateDsr(dsr.id, payload) : startDsr(sessionId, payload);
    save
      .then((updated) => {
        if (cancelled) return;
        setDsr(updated);
        setLastSavedAt(new Date().toISOString());
      })
      .catch(() => {
        // A background autosave failure is not shown as an error — the local
        // draft is the safety net, and a real problem surfaces when the
        // trainer presses "Finish class".
      })
      .finally(() => {
        if (!cancelled) setIsSavingDraft(false);
      });
    return () => {
      cancelled = true;
    };
    // Fires only when the debounced DSR fields settle — see the module
    // docstring on why `dsr` itself must not be a dependency here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedDraft]);

  // --- Handlers --------------------------------------------------------------

  function updateDraft(patch: DSRWritePayload) {
    setIsDirty(true);
    setDraft((current) => ({ ...current, ...patch }));
  }

  function markStudent(enrollmentId: string, status: AttendanceStatus) {
    setIsDirty(true);
    setMarks((current) => ({ ...current, [enrollmentId]: status }));
  }

  function markAllPresent() {
    if (!register) return;
    setIsDirty(true);
    setMarks(Object.fromEntries(register.entries.map((entry) => [entry.enrollment_id, 'present'])));
  }

  function changeTopicSelection(value: string) {
    setIsDirty(true);
    setTopicSelection(value);
  }

  function buildRegisterEntries() {
    if (!register) return [];
    return register.entries.map((entry) => ({
      enrollment_id: entry.enrollment_id,
      status: marks[entry.enrollment_id] ?? ('absent' as AttendanceStatus),
      note: entry.note,
    }));
  }

  async function saveRegisterOnly() {
    if (!register || !register.can_mark) return;
    setIsSavingRegister(true);
    setRegisterError(null);
    setRegisterSaved(null);
    try {
      const result = await markAttendance(sessionId, buildRegisterEntries());
      setRegisterSaved(
        `Saved. ${result.created} new, ${result.updated} updated` +
          (result.corrections ? `, ${result.corrections} corrected.` : '.'),
      );
      setRegister(await getRegister(sessionId));
    } catch (cause) {
      setRegisterError(fieldErrors(cause).__all__ ?? 'The register could not be saved.');
    } finally {
      setIsSavingRegister(false);
    }
  }

  async function finishClass() {
    if (!session || !register || !dsr) return;
    setIsFinishing(true);
    setRegisterError(null);
    setTopicError(null);
    setDsrFieldErrors({});

    if (register.can_mark) {
      try {
        await markAttendance(sessionId, buildRegisterEntries());
      } catch (cause) {
        setRegisterError(fieldErrors(cause).__all__ ?? 'The register could not be saved.');
        setIsFinishing(false);
        return;
      }
    }

    if (topicSelection) {
      try {
        await recordTopic(
          sessionId,
          topicSelection === SKIP_TOPIC_VALUE
            ? { lesson_id: null, status: 'skipped' }
            : { lesson_id: topicSelection, status: 'completed' },
        );
      } catch (cause) {
        setTopicError(fieldErrors(cause).__all__ ?? 'The topic could not be recorded.');
        setIsFinishing(false);
        return;
      }
    }

    try {
      const payload: DSRWritePayload = {
        ...draft,
        present_count: liveCounts.present,
        absent_count: liveCounts.absent,
        student_count: liveCounts.student,
        submit: true,
      };
      const submitted = dsr.id ? await updateDsr(dsr.id, payload) : await startDsr(sessionId, payload);
      setDsr(submitted);
      clearDsrDraft(sessionId);
      setIsDirty(false);
      setFinishedCounts({ present: liveCounts.present, absent: liveCounts.absent });
      setFinished(true);
    } catch (cause) {
      setDsrFieldErrors(fieldErrors(cause));
    } finally {
      setIsFinishing(false);
    }
  }

  useKeyboardShortcuts(
    [
      {
        keys: 'mod+enter',
        description: 'Finish class',
        handler: () => {
          if (!isFinishing && !finished) void finishClass();
        },
      },
    ],
    Boolean(session) && !finished,
  );

  // --- Render ------------------------------------------------------------

  if (isLoadingCore) return <LoadingState label="Loading the class…" rows={8} />;
  if (coreError) {
    return (
      <ErrorState
        title="Could not load this class"
        message={coreError.message}
        requestId={coreError.requestId || undefined}
        onRetry={() => {
          setIsLoadingCore(true);
          setCoreError(null);
          setCoreAttempt((value) => value + 1);
        }}
      />
    );
  }
  if (!session || !register || !dsr) return null;

  if (finished) {
    return (
      <ClassCompleteSummary
        session={session}
        present={finishedCounts.present}
        absent={finishedCounts.absent}
        onChangeClass={onChangeClass}
      />
    );
  }

  return (
    <div className="space-y-6">
      <ClassHeader
        session={session}
        attendanceTaken={Boolean(register.attendance_taken_at)}
        topicSelection={topicSelection}
        onTopicSelectionChange={changeTopicSelection}
        modules={modules}
        isLoadingModules={isLoadingBatchInfo}
        onChangeClass={onChangeClass}
      />
      {topicError ? (
        <Alert variant="error" role="alert">
          {topicError}
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Register</CardTitle>
          <CardDescription>
            {formatNumber(register.entries.length)} student{register.entries.length === 1 ? '' : 's'}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {registerError ? (
            <Alert variant="error" role="alert">
              {registerError}
            </Alert>
          ) : null}
          {registerSaved ? (
            <Alert variant="success" role="status">
              {registerSaved}
            </Alert>
          ) : null}
          <RegisterEditor
            entries={register.entries}
            marks={marks}
            onMark={markStudent}
            onMarkAllPresent={markAllPresent}
            canMark={register.can_mark}
          />
          {register.can_mark ? (
            <Button type="button" variant="outline" size="sm" onClick={() => void saveRegisterOnly()} disabled={isSavingRegister}>
              {isSavingRegister ? 'Saving…' : 'Save register'}
            </Button>
          ) : null}
        </CardContent>
      </Card>

      <DsrPanel
        dsr={dsr}
        draft={draft}
        onChange={updateDraft}
        presentCount={liveCounts.present}
        absentCount={liveCounts.absent}
        studentCount={liveCounts.student}
        fieldErrors={dsrFieldErrors}
        isDirty={isDirty}
        isSavingDraft={isSavingDraft}
        lastSavedAt={lastSavedAt}
      />

      <ClassWorkPanel
        batchId={session.batch_id}
        courseId={batch?.course_id ?? null}
        isLoadingCourse={isLoadingBatchInfo}
        assignmentGiven={Boolean(draft.assignment_given)}
        assessmentConducted={Boolean(draft.assessment_conducted)}
        onToggleAssignmentGiven={(value) => updateDraft({ assignment_given: value })}
        onToggleAssessmentConducted={(value) => updateDraft({ assessment_conducted: value })}
      />

      {dsr.is_editable ? (
        <div className="flex flex-wrap items-center justify-end gap-3 border-t border-border pt-4">
          <span className="text-xs text-muted-foreground">Tip: Ctrl/Cmd + Enter finishes the class.</span>
          <Button type="button" size="lg" onClick={() => void finishClass()} disabled={isFinishing}>
            {isFinishing ? 'Finishing…' : 'Finish class'}
          </Button>
        </div>
      ) : (
        <p className="border-t border-border pt-4 text-sm text-muted-foreground">
          This report has moved to review — the register above can still be corrected, but the report
          itself is closed to further edits here.
        </p>
      )}
    </div>
  );
}

/** Picks which class `ClassWorkspace` shows — see the module docstring. */
export function TodayWorkspace() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const sessionId = searchParams.get('session');

  const [today] = useState(todayIso);
  const [todaySessions, setTodaySessions] = useState<ClassSession[]>([]);
  const [isLoadingToday, setIsLoadingToday] = useState(true);
  const [todayError, setTodayError] = useState<ApiError | null>(null);
  const [todayAttempt, setTodayAttempt] = useState(0);
  const autoOpenedRef = useRef(false);

  useEffect(() => {
    // A session id already in the URL means the picker below never renders
    // — fetching "today's classes" just to throw the answer away wastes the
    // one request a bookmarked or refreshed catch-up class needs least.
    if (sessionId) return;
    let cancelled = false;
    listTodaySessions()
      .then((rows) => {
        if (!cancelled) setTodaySessions(rows);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setTodayError(cause instanceof ApiError ? cause : null);
      })
      .finally(() => {
        if (!cancelled) setIsLoadingToday(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, todayAttempt]);

  // A trainer with one class today should not have to choose it from a list
  // of one — see the module docstring.
  useEffect(() => {
    if (sessionId || autoOpenedRef.current || isLoadingToday || todayError) return;
    const [only] = todaySessions;
    if (only && todaySessions.length === 1) {
      autoOpenedRef.current = true;
      router.replace(`${TODAY_PATH}?session=${only.id}`);
    }
  }, [sessionId, isLoadingToday, todayError, todaySessions, router]);

  function selectSession(session: ClassSession) {
    autoOpenedRef.current = true;
    router.replace(`${TODAY_PATH}?session=${session.id}`);
  }

  function changeClass() {
    router.replace(TODAY_PATH);
  }

  if (sessionId) {
    return <ClassWorkspace key={sessionId} sessionId={sessionId} onChangeClass={changeClass} />;
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Today&rsquo;s class</h1>
        <p className="text-sm text-muted-foreground">
          Choose a class to take its register and file the day&rsquo;s report.
        </p>
      </div>
      <ClassPicker
        todayIso={today}
        todaySessions={todaySessions}
        isLoadingToday={isLoadingToday}
        todayError={todayError}
        onRetryToday={() => {
          setIsLoadingToday(true);
          setTodayError(null);
          setTodayAttempt((value) => value + 1);
        }}
        onSelect={selectSession}
      />
    </div>
  );
}

export default function TodayPage() {
  return (
    <RequireAuth>
      <Suspense fallback={<LoadingState label="Loading today's classes…" rows={6} />}>
        <TodayWorkspace />
      </Suspense>
    </RequireAuth>
  );
}
