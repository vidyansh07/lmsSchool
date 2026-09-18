/**
 * `LessonEditor` (`app/admin/courses/[courseId]/lesson-editor.tsx`) —
 * Publish/Unpublish, Delete, and the per-resource remove button had no busy
 * guard (R11 double-submission audit gap). Covers that a fast double-click
 * on each only fires the mutation once.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LessonEditor } from '@/app/admin/courses/[courseId]/lesson-editor';
import type { LessonContent, LessonSummary } from '@/types/api';

const setLessonStatus = vi.hoisted(() => vi.fn());
const deleteLesson = vi.hoisted(() => vi.fn());
const deleteResource = vi.hoisted(() => vi.fn());
const getLesson = vi.hoisted(() => vi.fn());
vi.mock('@/lib/courses', async () => {
  const actual = await vi.importActual<typeof import('@/lib/courses')>('@/lib/courses');
  return { ...actual, setLessonStatus, deleteLesson, deleteResource, getLesson };
});

function lesson(overrides: Partial<LessonSummary> = {}): LessonSummary {
  return {
    id: 'lesson-1',
    title: 'Intro to shells',
    slug: 'intro-to-shells',
    description: '',
    content_type: 'text',
    duration_minutes: 10,
    position: 0,
    status: 'draft',
    is_preview: false,
    is_required: true,
    resource_count: 1,
    ...overrides,
  };
}

function lessonContent(overrides: Partial<LessonContent> = {}): LessonContent {
  return {
    ...lesson(),
    text_content: '',
    external_url: '',
    video: null,
    resources: [
      { id: 'resource-1', title: 'Cheat sheet', kind: 'file', size_bytes: 1024, external_url: '' } as never,
    ],
    module_id: 'module-1',
    course_id: 'course-1',
    ...overrides,
  };
}

beforeEach(() => {
  setLessonStatus.mockReset();
  deleteLesson.mockReset();
  deleteResource.mockReset();
  getLesson.mockReset();
  getLesson.mockResolvedValue(lessonContent());
});

describe('LessonEditor — double-submission protection', () => {
  it('disables Publish while the request is in flight and only calls it once on a fast double-click', async () => {
    let resolve!: () => void;
    setLessonStatus.mockReturnValue(
      new Promise<void>((r) => {
        resolve = r;
      }),
    );
    const onSaved = vi.fn();
    render(<LessonEditor moduleId="module-1" lesson={lesson()} onSaved={onSaved} onCancel={() => {}} />);

    const publishButton = await screen.findByRole('button', { name: 'Publish' });
    fireEvent.click(publishButton);
    fireEvent.click(publishButton);

    await waitFor(() => expect(publishButton).toBeDisabled());
    expect(setLessonStatus).toHaveBeenCalledOnce();

    resolve();
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
  });

  it('disables Delete while the request is in flight and only calls it once on a fast double-click', async () => {
    let resolve!: () => void;
    deleteLesson.mockReturnValue(
      new Promise<void>((r) => {
        resolve = r;
      }),
    );
    const onSaved = vi.fn();
    render(<LessonEditor moduleId="module-1" lesson={lesson()} onSaved={onSaved} onCancel={() => {}} />);

    const deleteButton = await screen.findByRole('button', { name: /Delete/ });
    fireEvent.click(deleteButton);
    fireEvent.click(deleteButton);

    await waitFor(() => expect(deleteButton).toBeDisabled());
    expect(deleteLesson).toHaveBeenCalledOnce();

    resolve();
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
  });

  it('disables the resource remove button while the request is in flight and only calls it once on a fast double-click', async () => {
    let resolve!: () => void;
    deleteResource.mockReturnValue(
      new Promise<void>((r) => {
        resolve = r;
      }),
    );
    render(<LessonEditor moduleId="module-1" lesson={lesson()} onSaved={() => {}} onCancel={() => {}} />);

    const removeButton = await screen.findByRole('button', { name: 'Remove Cheat sheet' });
    fireEvent.click(removeButton);
    fireEvent.click(removeButton);

    await waitFor(() => expect(removeButton).toBeDisabled());
    expect(deleteResource).toHaveBeenCalledOnce();

    resolve();
  });
});
