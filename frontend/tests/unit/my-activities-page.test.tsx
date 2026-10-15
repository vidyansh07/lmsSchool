/**
 * The student's "My activities" page: lists what was shared with them through
 * their own student-scoped endpoint and opens one read-only, showing only the
 * form answers marked visible to students.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { MyActivities } from '@/app/my-activities/page';

const listStudentActivities = vi.hoisted(() => vi.fn());
const getActivity = vi.hoisted(() => vi.fn());
vi.mock('@/lib/work', () => ({ listStudentActivities, getActivity }));
const useAuth = vi.hoisted(() => vi.fn());
vi.mock('@/components/auth-provider', () => ({ useAuth }));
const replace = vi.hoisted(() => vi.fn());
const searchParams = vi.hoisted(() => ({ value: new URLSearchParams() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
  useSearchParams: () => searchParams.value,
}));

const row = {
  id: 'act-1',
  title: 'Mock interview',
  status: 'completed',
  priority: 'normal',
  planned_at: null,
  due_at: '2026-10-10T10:00:00Z',
  completed_at: '2026-10-11T10:00:00Z',
  created_at: '2026-10-01T10:00:00Z',
  student: null,
  enquiry: null,
  type: { id: 't1', slug: 'mock', name: 'Mock interview', category: 'assessment' },
  batch: null,
  assigned_to: null,
  created_by: null,
  counts: { history: 1 },
};

function field(key: string, label: string, visible: boolean) {
  return {
    id: key,
    key,
    label,
    help: '',
    type: 'textarea',
    required: false,
    order: 1,
    group: '',
    options: {},
    validation: {},
    visible_to_student: visible,
    performance_key: null,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  searchParams.value = new URLSearchParams();
  useAuth.mockReturnValue({ user: { id: 'u1', role: 'student', profile_id: 'stu-1' } });
  listStudentActivities.mockResolvedValue({
    count: 1,
    page: 1,
    page_size: 20,
    total_pages: 1,
    results: [row],
  });
});

describe('MyActivities', () => {
  it("lists the student's own shared activities and opens one read-only", async () => {
    getActivity.mockResolvedValue({
      ...row,
      performed_by: { id: 'tr', name: 'Tina Trainer' },
      reviewed_by: null,
      started_at: null,
      reviewed_at: null,
      duration_minutes: null,
      result: 'pass',
      score: '8.00',
      max_score: '10.00',
      summary: 'Clear answers on Linux basics.',
      review_note: '',
      student_visible: true,
      form: {
        version: 1,
        fields: [
          field('strengths', 'Strengths', true),
          field('private', 'Counsellor note', false),
        ],
      },
      form_values: { strengths: 'Confident' },
      history: [],
      parent: null,
      children: [],
      automation_run: null,
    });
    render(<MyActivities />);

    await waitFor(() =>
      expect(listStudentActivities).toHaveBeenCalledWith('stu-1', expect.objectContaining({ page: 1 })),
    );
    fireEvent.click(await screen.findByRole('button', { name: 'Mock interview' }));

    const sheet = await screen.findByRole('dialog');
    expect(await within(sheet).findByText('Clear answers on Linux basics.')).toBeInTheDocument();
    expect(within(sheet).getByText('Passed')).toBeInTheDocument();
    expect(within(sheet).queryByText('Counsellor note')).not.toBeInTheDocument();
    expect(replace).toHaveBeenCalledWith('/my-activities?activity=act-1');
  });

  it('opens the activity named in the address straight away', async () => {
    searchParams.value = new URLSearchParams('activity=act-1');
    getActivity.mockReturnValue(new Promise(() => {}));
    render(<MyActivities />);
    await waitFor(() => expect(getActivity).toHaveBeenCalledWith('act-1'));
  });

  it('tells staff this is the student page rather than showing an empty list', async () => {
    useAuth.mockReturnValue({ user: { id: 'u2', role: 'manager', profile_id: null } });
    render(<MyActivities />);
    expect(screen.getByText('This page is for students')).toBeInTheDocument();
    expect(listStudentActivities).not.toHaveBeenCalled();
  });
});
