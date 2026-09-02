/** API calls for the question bank and examinations (Phase 5.4–5.5). */

import { apiFetch, apiMutate, queryString } from './api';
import type {
  AcademicLifecycle,
  AttemptPaper,
  AttemptResult,
  AttemptReview,
  Exam,
  ExamReadiness,
  MarkableAnswer,
  Paginated,
  Question,
  StaffAttempt,
} from '@/types/api';

// --- Question bank ---------------------------------------------------------

export interface QuestionQuery {
  course?: string;
  question_type?: string;
  difficulty?: string;
  is_active?: string;
  tag?: string;
  search?: string;
  page?: number;
  [key: string]: string | number | undefined;
}

export async function listQuestions(query: QuestionQuery = {}): Promise<Paginated<Question>> {
  return apiFetch<Paginated<Question>>(`/api/v1/questions/${queryString(query)}`);
}

export async function createQuestion(payload: Record<string, unknown>): Promise<Question> {
  return apiMutate<Question>('/api/v1/questions/create/', { method: 'POST', body: payload });
}

export async function updateQuestion(
  id: string,
  changes: Record<string, unknown>,
): Promise<Question> {
  return apiMutate<Question>(`/api/v1/questions/${id}/`, { method: 'PATCH', body: changes });
}

// --- Examinations ----------------------------------------------------------

export interface ExamQuery {
  batch?: string;
  course?: string;
  status?: string;
  page?: number;
  ordering?: string;
  [key: string]: string | number | undefined;
}

export async function listExams(query: ExamQuery = {}): Promise<Paginated<Exam>> {
  return apiFetch<Paginated<Exam>>(`/api/v1/exams/${queryString(query)}`);
}

export async function listMyExams(query: ExamQuery = {}): Promise<Paginated<Exam>> {
  return apiFetch<Paginated<Exam>>(`/api/v1/exams/mine/${queryString(query)}`);
}

export async function getExam(id: string): Promise<Exam> {
  return apiFetch<Exam>(`/api/v1/exams/${id}/`);
}

export async function createExam(
  batchId: string,
  payload: Record<string, unknown>,
): Promise<Exam> {
  return apiMutate<Exam>(`/api/v1/batches/${batchId}/exams/`, { method: 'POST', body: payload });
}

export async function setExamStatus(id: string, status: AcademicLifecycle): Promise<Exam> {
  return apiMutate<Exam>(`/api/v1/exams/${id}/status/`, { method: 'POST', body: { status } });
}

export async function getExamReadiness(id: string): Promise<ExamReadiness> {
  return apiFetch<ExamReadiness>(`/api/v1/exams/${id}/readiness/`);
}

export async function publishExamResults(id: string, published = true): Promise<Exam> {
  return apiMutate<Exam>(`/api/v1/exams/${id}/results/publish/`, {
    method: 'POST',
    body: { published },
  });
}

export async function listExamAttempts(examId: string): Promise<Paginated<StaffAttempt>> {
  return apiFetch<Paginated<StaffAttempt>>(`/api/v1/exams/${examId}/attempts/`);
}

export async function listMarkingQueue(examId: string): Promise<MarkableAnswer[]> {
  return apiFetch<MarkableAnswer[]>(`/api/v1/exams/${examId}/marking/`);
}

export async function markAnswer(
  answerId: string,
  awarded: string,
  feedback = '',
): Promise<StaffAttempt> {
  return apiMutate<StaffAttempt>(`/api/v1/attempts/answers/${answerId}/mark/`, {
    method: 'POST',
    body: { awarded, feedback },
  });
}

// --- Sitting ---------------------------------------------------------------

/**
 * Start or resume. The backend is idempotent, so this is safe to call on a
 * refresh, a reopened browser, or a double-clicked button.
 */
export async function startAttempt(examId: string): Promise<AttemptPaper> {
  return apiMutate<AttemptPaper>(`/api/v1/exams/${examId}/start/`, { method: 'POST' });
}

export async function getAttemptPaper(attemptId: string): Promise<AttemptPaper> {
  return apiFetch<AttemptPaper>(`/api/v1/attempts/${attemptId}/`);
}

/** Auto-save one answer. No score travels in either direction. */
export async function saveAnswer(
  attemptId: string,
  questionId: string,
  payload: { selected_options?: string[]; text_answer?: string },
): Promise<unknown> {
  return apiMutate(`/api/v1/attempts/${attemptId}/questions/${questionId}/answer/`, {
    method: 'POST',
    body: payload,
  });
}

export async function submitAttempt(attemptId: string): Promise<AttemptResult> {
  return apiMutate<AttemptResult>(`/api/v1/attempts/${attemptId}/submit/`, { method: 'POST' });
}

export async function listMyAttempts(): Promise<Paginated<AttemptResult>> {
  return apiFetch<Paginated<AttemptResult>>('/api/v1/attempts/mine/');
}

export async function getAttemptResult(attemptId: string): Promise<AttemptResult> {
  return apiFetch<AttemptResult>(`/api/v1/attempts/${attemptId}/result/`);
}

export async function getAttemptReview(attemptId: string): Promise<AttemptReview> {
  return apiFetch<AttemptReview>(`/api/v1/attempts/${attemptId}/review/`);
}
