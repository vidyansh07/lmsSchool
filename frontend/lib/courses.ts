/** API calls for the course catalogue and learning content. */

import { apiFetch, apiMutate, queryString } from './api';
import type { ListQuery } from './people';
import type {
  Category,
  CourseAssignment,
  CourseDetail,
  CourseListRow,
  LessonContent,
  LessonResource,
  Module,
  Paginated,
  PublishChecklist,
  PublishStatus,
  VideoPlayback,
} from '@/types/api';

// --- Categories ------------------------------------------------------------

export async function listCategories(query: ListQuery = {}): Promise<Paginated<Category>> {
  return apiFetch<Paginated<Category>>(`/api/v1/categories/${queryString(query)}`);
}

export async function createCategory(payload: {
  name: string;
  slug?: string;
  description?: string;
}): Promise<Category> {
  return apiMutate<Category>('/api/v1/categories/', { method: 'POST', body: payload });
}

export async function updateCategory(
  id: string,
  changes: Partial<Category>,
): Promise<Category> {
  return apiMutate<Category>(`/api/v1/categories/${id}/`, { method: 'PATCH', body: changes });
}

// --- Courses ---------------------------------------------------------------

export async function listCourses(query: ListQuery = {}): Promise<Paginated<CourseListRow>> {
  return apiFetch<Paginated<CourseListRow>>(`/api/v1/courses/${queryString(query)}`);
}

export async function listMyCourses(query: ListQuery = {}): Promise<Paginated<CourseListRow>> {
  return apiFetch<Paginated<CourseListRow>>(`/api/v1/courses/mine/${queryString(query)}`);
}

/** Accepts a slug or a UUID — the API resolves either. */
export async function getCourse(identifier: string): Promise<CourseDetail> {
  return apiFetch<CourseDetail>(`/api/v1/courses/${identifier}/`);
}

export async function createCourse(payload: {
  title: string;
  category: string;
  short_description?: string;
  description?: string;
  difficulty?: string;
  visibility?: string;
  estimated_duration_minutes?: number | null;
  learning_objectives?: string[];
  prerequisites?: string[];
}): Promise<CourseDetail> {
  return apiMutate<CourseDetail>('/api/v1/courses/', { method: 'POST', body: payload });
}

export async function updateCourse(
  id: string,
  changes: Record<string, unknown>,
): Promise<CourseDetail> {
  return apiMutate<CourseDetail>(`/api/v1/courses/${id}/`, { method: 'PATCH', body: changes });
}

export async function setCourseStatus(
  id: string,
  status: PublishStatus,
  note = '',
): Promise<CourseDetail> {
  return apiMutate<CourseDetail>(`/api/v1/courses/${id}/status/`, {
    method: 'POST',
    body: { status, note },
  });
}

export async function getPublishChecklist(id: string): Promise<PublishChecklist> {
  return apiFetch<PublishChecklist>(`/api/v1/courses/${id}/publish-checklist/`);
}

export async function uploadCourseThumbnail(id: string, file: File): Promise<CourseDetail> {
  const formData = new FormData();
  formData.append('image', file);
  return apiMutate<CourseDetail>(`/api/v1/courses/${id}/thumbnail/`, {
    method: 'POST',
    formData,
  });
}

export async function listCourseAuthors(id: string): Promise<CourseAssignment[]> {
  return apiFetch<CourseAssignment[]>(`/api/v1/courses/${id}/authors/`);
}

export async function assignCourseAuthor(
  id: string,
  userId: string,
  role: string,
): Promise<CourseAssignment> {
  return apiMutate<CourseAssignment>(`/api/v1/courses/${id}/authors/`, {
    method: 'POST',
    body: { user_id: userId, role },
  });
}

export async function removeCourseAuthor(id: string, userId: string): Promise<void> {
  return apiMutate<void>(`/api/v1/courses/${id}/authors/${userId}/`, { method: 'DELETE' });
}

// --- Modules ---------------------------------------------------------------

export async function listModules(courseId: string): Promise<Module[]> {
  return apiFetch<Module[]>(`/api/v1/courses/${courseId}/modules/`);
}

export async function createModule(
  courseId: string,
  payload: { title: string; description?: string },
): Promise<Module> {
  return apiMutate<Module>(`/api/v1/courses/${courseId}/modules/`, {
    method: 'POST',
    body: payload,
  });
}

export async function updateModule(
  moduleId: string,
  changes: Record<string, unknown>,
): Promise<Module> {
  return apiMutate<Module>(`/api/v1/modules/${moduleId}/`, { method: 'PATCH', body: changes });
}

export async function deleteModule(moduleId: string): Promise<void> {
  return apiMutate<void>(`/api/v1/modules/${moduleId}/`, { method: 'DELETE' });
}

export async function setModuleStatus(moduleId: string, status: PublishStatus): Promise<Module> {
  return apiMutate<Module>(`/api/v1/modules/${moduleId}/status/`, {
    method: 'POST',
    body: { status },
  });
}

export async function reorderModules(courseId: string, orderedIds: string[]): Promise<Module[]> {
  return apiMutate<Module[]>(`/api/v1/courses/${courseId}/modules/reorder/`, {
    method: 'POST',
    body: { ordered_ids: orderedIds },
  });
}

// --- Lessons ---------------------------------------------------------------

export async function getLesson(lessonId: string): Promise<LessonContent> {
  return apiFetch<LessonContent>(`/api/v1/lessons/${lessonId}/`);
}

export async function createLesson(
  moduleId: string,
  payload: Record<string, unknown>,
): Promise<LessonContent> {
  return apiMutate<LessonContent>(`/api/v1/modules/${moduleId}/lessons/`, {
    method: 'POST',
    body: payload,
  });
}

export async function updateLesson(
  lessonId: string,
  changes: Record<string, unknown>,
): Promise<LessonContent> {
  return apiMutate<LessonContent>(`/api/v1/lessons/${lessonId}/`, {
    method: 'PATCH',
    body: changes,
  });
}

export async function deleteLesson(lessonId: string): Promise<void> {
  return apiMutate<void>(`/api/v1/lessons/${lessonId}/`, { method: 'DELETE' });
}

export async function setLessonStatus(
  lessonId: string,
  status: PublishStatus,
): Promise<LessonContent> {
  return apiMutate<LessonContent>(`/api/v1/lessons/${lessonId}/status/`, {
    method: 'POST',
    body: { status },
  });
}

export async function reorderLessons(
  moduleId: string,
  orderedIds: string[],
): Promise<unknown> {
  return apiMutate(`/api/v1/modules/${moduleId}/lessons/reorder/`, {
    method: 'POST',
    body: { ordered_ids: orderedIds },
  });
}

/**
 * Fetch the playable video URL.
 *
 * Separate call by design: the URL is not in the lesson payload, so it is only
 * requested when a viewer actually opens the player, and only handed over after
 * the server has re-checked entitlement.
 */
export async function getVideoPlayback(lessonId: string): Promise<VideoPlayback> {
  return apiFetch<VideoPlayback>(`/api/v1/lessons/${lessonId}/video/`);
}

// --- Resources -------------------------------------------------------------

export async function listLessonResources(lessonId: string): Promise<LessonResource[]> {
  return apiFetch<LessonResource[]>(`/api/v1/lessons/${lessonId}/resources/`);
}

export async function uploadLessonResource(
  lessonId: string,
  title: string,
  file: File,
  description = '',
): Promise<LessonResource> {
  const formData = new FormData();
  formData.append('title', title);
  formData.append('description', description);
  formData.append('file', file);
  return apiMutate<LessonResource>(`/api/v1/lessons/${lessonId}/resources/`, {
    method: 'POST',
    formData,
  });
}

export async function addLessonResourceLink(
  lessonId: string,
  payload: { title: string; external_url: string; description?: string },
): Promise<LessonResource> {
  return apiMutate<LessonResource>(`/api/v1/lessons/${lessonId}/resources/link/`, {
    method: 'POST',
    body: payload,
  });
}

export async function deleteResource(resourceId: string): Promise<void> {
  return apiMutate<void>(`/api/v1/resources/${resourceId}/`, { method: 'DELETE' });
}
