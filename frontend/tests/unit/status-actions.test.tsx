/**
 * Status changes on a course or a batch are confirmed before they are sent:
 * the dialog says what will happen, the request goes only on "confirm", and
 * "go back" sends nothing.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PublishPanel, transitionsFor } from '@/app/admin/courses/[courseId]/publish-panel';
import { StatusActions } from '@/components/status-actions';
import type { CourseDetail } from '@/types/api';

const setCourseStatus = vi.hoisted(() => vi.fn());
const getPublishChecklist = vi.hoisted(() => vi.fn());
vi.mock('@/lib/courses', () => ({ setCourseStatus, getPublishChecklist }));

function course(overrides: Partial<CourseDetail> = {}): CourseDetail {
  return {
    id: 'course-1',
    status: 'draft',
    can_manage: true,
    can_publish: true,
    ...overrides,
  } as CourseDetail;
}

beforeEach(() => {
  setCourseStatus.mockReset();
  getPublishChecklist.mockReset().mockResolvedValue({ ready: true, blockers: [] });
});

describe('StatusActions', () => {
  it('asks before acting, and sends nothing on "go back"', async () => {
    const onConfirm = vi.fn();
    render(
      <StatusActions
        actions={[
          {
            target: 'archived',
            label: 'Archive',
            description: 'Students lose access.',
            variant: 'destructive',
          },
        ]}
        onConfirm={onConfirm}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Archive' }));
    const dialog = screen.getByRole('alertdialog');
    expect(dialog).toHaveTextContent('Archive?');
    expect(dialog).toHaveTextContent('Students lose access.');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Go back' }));
    expect(onConfirm).not.toHaveBeenCalled();
    // The dialog fades out before it unmounts.
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Archive' }));
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Archive' }));
    await waitFor(() => expect(onConfirm).toHaveBeenCalledWith('archived'));
  });
});

describe('PublishPanel', () => {
  it('offers Activate on an inactive course and says what it means', () => {
    render(<PublishPanel course={course()} onChanged={vi.fn()} />);
    expect(screen.getByText(/^Inactive\.$/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Activate' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Publish' })).not.toBeInTheDocument();
  });

  it('activates only after the confirmation', async () => {
    setCourseStatus.mockResolvedValue({});
    const onChanged = vi.fn();
    render(<PublishPanel course={course()} onChanged={onChanged} />);
    fireEvent.click(screen.getByRole('button', { name: 'Activate' }));
    expect(setCourseStatus).not.toHaveBeenCalled();
    const dialog = screen.getByRole('alertdialog');
    expect(dialog).toHaveTextContent('Activate this course?');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Activate' }));
    await waitFor(() => expect(setCourseStatus).toHaveBeenCalledWith('course-1', 'published'));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it('shows the archived banner with a restore action', () => {
    render(<PublishPanel course={course({ status: 'archived' })} onChanged={vi.fn()} />);
    expect(screen.getByTestId('course-archived-banner')).toHaveTextContent(/archived/i);
    expect(screen.getByRole('button', { name: 'Restore' })).toBeInTheDocument();
  });

  it('an editor who cannot publish is offered review only', () => {
    expect(transitionsFor(course({ can_publish: false })).map((action) => action.label)).toEqual([
      'Submit for review',
    ]);
    expect(transitionsFor(course({ status: 'published' })).map((action) => action.label)).toEqual([
      'Deactivate',
      'Archive',
    ]);
  });
});
