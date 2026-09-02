/** API calls for batches, schedules, enrolment, calendar and dashboards. */

import { apiFetch, apiMutate, queryString } from './api';
import type { ListQuery } from './people';
import type {
  BatchDetail,
  BatchListRow,
  BatchSchedule,
  BatchStatus,
  CalendarResponse,
  CourseProgress,
  Enrollment,
  EnrollmentStatus,
  LessonProgress,
  Paginated,
  RosterEntry,
  StudentDashboard,
  TrainerDashboard,
  Weekday,
} from '@/types/api';

// --- Batches ---------------------------------------------------------------

export async function listBatches(query: ListQuery = {}): Promise<Paginated<BatchListRow>> {
  return apiFetch<Paginated<BatchListRow>>(`/api/v1/batches/${queryString(query)}`);
}

export async function getBatch(id: string): Promise<BatchDetail> {
  return apiFetch<BatchDetail>(`/api/v1/batches/${id}/`);
}

export async function createBatch(payload: {
  name: string;
  course: string;
  description?: string;
  start_date: string;
  end_date: string;
  capacity: number;
}): Promise<BatchDetail> {
  return apiMutate<BatchDetail>('/api/v1/batches/', { method: 'POST', body: payload });
}

export async function updateBatch(
  id: string,
  changes: Record<string, unknown>,
): Promise<BatchDetail> {
  return apiMutate<BatchDetail>(`/api/v1/batches/${id}/`, { method: 'PATCH', body: changes });
}

export async function setBatchStatus(
  id: string,
  status: BatchStatus,
  note = '',
): Promise<BatchDetail> {
  return apiMutate<BatchDetail>(`/api/v1/batches/${id}/status/`, {
    method: 'POST',
    body: { status, note },
  });
}

export async function assignBatchTrainer(
  id: string,
  trainerId: string | null,
): Promise<BatchDetail> {
  return apiMutate<BatchDetail>(`/api/v1/batches/${id}/trainer/`, {
    method: 'POST',
    body: { trainer_id: trainerId },
  });
}

export async function getBatchRoster(id: string): Promise<RosterEntry[]> {
  return apiFetch<RosterEntry[]>(`/api/v1/batches/${id}/roster/`);
}

// --- Schedules -------------------------------------------------------------

export async function listBatchSchedules(id: string): Promise<BatchSchedule[]> {
  return apiFetch<BatchSchedule[]>(`/api/v1/batches/${id}/schedules/`);
}

export async function createSchedule(
  batchId: string,
  payload: {
    weekday: Weekday;
    start_time: string;
    end_time: string;
    timezone_name?: string;
    location?: string;
  },
): Promise<BatchSchedule> {
  return apiMutate<BatchSchedule>(`/api/v1/batches/${batchId}/schedules/`, {
    method: 'POST',
    body: payload,
  });
}

export async function updateSchedule(
  scheduleId: string,
  changes: Record<string, unknown>,
): Promise<BatchSchedule> {
  return apiMutate<BatchSchedule>(`/api/v1/schedules/${scheduleId}/`, {
    method: 'PATCH',
    body: changes,
  });
}

export async function deleteSchedule(scheduleId: string): Promise<void> {
  return apiMutate<void>(`/api/v1/schedules/${scheduleId}/`, { method: 'DELETE' });
}

// --- Enrolment -------------------------------------------------------------

export async function listEnrollments(query: ListQuery = {}): Promise<Paginated<Enrollment>> {
  return apiFetch<Paginated<Enrollment>>(`/api/v1/enrollments/${queryString(query)}`);
}

export async function listMyEnrollments(): Promise<Enrollment[]> {
  return apiFetch<Enrollment[]>('/api/v1/enrollments/mine/');
}

export async function enrolStudent(payload: {
  student_id: string;
  batch_id: string;
  status?: EnrollmentStatus;
  note?: string;
}): Promise<Enrollment> {
  return apiMutate<Enrollment>('/api/v1/enrollments/', { method: 'POST', body: payload });
}

export async function setEnrollmentStatus(
  id: string,
  status: EnrollmentStatus,
  note = '',
): Promise<Enrollment> {
  return apiMutate<Enrollment>(`/api/v1/enrollments/${id}/status/`, {
    method: 'POST',
    body: { status, note },
  });
}

export async function getEnrollmentProgress(id: string): Promise<CourseProgress> {
  return apiFetch<CourseProgress>(`/api/v1/enrollments/${id}/progress/`);
}

export async function setLessonCompletion(
  lessonId: string,
  completed: boolean,
): Promise<LessonProgress> {
  return apiMutate<LessonProgress>(`/api/v1/progress/lessons/${lessonId}/completion/`, {
    method: 'POST',
    body: { completed },
  });
}

// --- Calendar and dashboards ----------------------------------------------

export async function getCalendar(start: string, end: string): Promise<CalendarResponse> {
  return apiFetch<CalendarResponse>(`/api/v1/calendar/${queryString({ start, end })}`);
}

export async function getStudentDashboard(): Promise<StudentDashboard> {
  return apiFetch<StudentDashboard>('/api/v1/dashboard/student/');
}

export async function getTrainerDashboard(): Promise<TrainerDashboard> {
  return apiFetch<TrainerDashboard>('/api/v1/dashboard/trainer/');
}
