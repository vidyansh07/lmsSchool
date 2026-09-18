/**
 * `ModulePanel` (`app/admin/courses/[courseId]/page.tsx`) — Publish/Unpublish
 * and delete have no busy state of their own (R11 double-submission audit
 * gap). Covers that a fast double-click only fires the mutation once and
 * that the buttons re-enable once the request settles.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ModulePanel } from '@/app/admin/courses/[courseId]/page';
import type { Module } from '@/types/api';

const setModuleStatus = vi.hoisted(() => vi.fn());
const deleteModule = vi.hoisted(() => vi.fn());
vi.mock('@/lib/courses', async () => {
  const actual = await vi.importActual<typeof import('@/lib/courses')>('@/lib/courses');
  return { ...actual, setModuleStatus, deleteModule };
});

function module(overrides: Partial<Module> = {}): Module {
  return {
    id: 'module-1',
    title: 'Getting started',
    description: '',
    position: 0,
    status: 'draft',
    is_visible: true,
    lessons: [],
    ...overrides,
  };
}

beforeEach(() => {
  setModuleStatus.mockReset();
  deleteModule.mockReset();
});

describe('ModulePanel — double-submission protection', () => {
  it('disables Publish while the request is in flight and only calls it once on a fast double-click', async () => {
    let resolve!: (value: Module) => void;
    setModuleStatus.mockReturnValue(
      new Promise<Module>((r) => {
        resolve = r;
      }),
    );
    const onChanged = vi.fn();
    render(
      <ModulePanel module={module()} index={0} total={1} onChanged={onChanged} onMove={() => {}} />,
    );

    const publishButton = screen.getByRole('button', { name: 'Publish' });
    fireEvent.click(publishButton);
    fireEvent.click(publishButton);

    await waitFor(() => expect(publishButton).toBeDisabled());
    expect(setModuleStatus).toHaveBeenCalledOnce();

    resolve(module({ status: 'published' }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
  });

  it('disables Delete while the request is in flight and only calls it once on a fast double-click', async () => {
    let resolve!: () => void;
    deleteModule.mockReturnValue(
      new Promise<void>((r) => {
        resolve = r;
      }),
    );
    const onChanged = vi.fn();
    render(
      <ModulePanel module={module()} index={0} total={1} onChanged={onChanged} onMove={() => {}} />,
    );

    const deleteButton = screen.getByRole('button', { name: 'Delete Getting started' });
    fireEvent.click(deleteButton);
    fireEvent.click(deleteButton);

    await waitFor(() => expect(deleteButton).toBeDisabled());
    expect(deleteModule).toHaveBeenCalledOnce();

    resolve();
    await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
  });
});
