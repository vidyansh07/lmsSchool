import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  listEnrolmentDestinations,
  listStudentEnrollments,
  transferEnrollment,
} from '@/lib/batches';
import { ApiError } from '@/lib/api';
import type { BatchListRow, BatchStatus, Enrollment, Paginated } from '@/types/api';

const apiFetch = vi.hoisted(() => vi.fn());
const apiMutate = vi.hoisted(() => vi.fn());

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, apiFetch, apiMutate };
});

function enrollment(overrides: Partial<Enrollment> = {}): Enrollment {
  return {
    id: 'e1',
    code: 'GRS-E-00001',
    course_id: 'c1',
    course_code: 'GRS-C-001',
    course_title: 'Linux Essentials',
    course_slug: 'linux-essentials',
    batch_id: 'b1',
    batch_code: 'GRS-B-001',
    batch_name: 'Morning batch',
    batch_status: 'active',
    trainer_name: 'Tina Trainer',
    status: 'active',
    enrolled_at: '2026-01-01T00:00:00Z',
    start_date: null,
    access_end_date: null,
    completed_at: null,
    grants_access: true,
    student_code: 'GRS-S-00042',
    ...overrides,
  };
}

function batch(
  id: string,
  status: BatchStatus,
  start_date: string,
  name = id,
): BatchListRow {
  return {
    id,
    code: `GRS-B-${id}`,
    name,
    course_id: 'c1',
    course_code: 'GRS-C-001',
    course_title: 'Linux Essentials',
    course_slug: 'linux-essentials',
    trainer_name: 'Tina Trainer',
    start_date,
    end_date: '2026-12-31',
    capacity: 20,
    enrolled_count: 1,
    seats_available: 19,
    status,
    created_at: '2026-01-01T00:00:00Z',
  };
}

function page(results: BatchListRow[], count = results.length): Paginated<BatchListRow> {
  return { count, page: 1, page_size: 100, total_pages: 1, next: null, previous: null, results };
}

beforeEach(() => {
  apiFetch.mockReset();
  apiMutate.mockReset();
});

describe('listStudentEnrollments', () => {
  it('searches by the student code, since there is no direct filter for it', async () => {
    apiFetch.mockResolvedValue({
      count: 1,
      page: 1,
      page_size: 100,
      total_pages: 1,
      next: null,
      previous: null,
      results: [enrollment()],
    });
    const rows = await listStudentEnrollments('GRS-S-00042');
    expect(apiFetch).toHaveBeenCalledWith(
      expect.stringContaining('search=GRS-S-00042'),
      expect.anything(),
    );
    expect(rows).toHaveLength(1);
  });

  it('drops any row that is not an exact match for the student code', async () => {
    // A defensive filter in case the search endpoint's substring match ever
    // widens beyond what the student's own code should return.
    apiFetch.mockResolvedValue({
      count: 2,
      page: 1,
      page_size: 100,
      total_pages: 1,
      next: null,
      previous: null,
      results: [enrollment({ student_code: 'GRS-S-00042' }), enrollment({ id: 'e2', student_code: 'GRS-S-00099' })],
    });
    const rows = await listStudentEnrollments('GRS-S-00042');
    expect(rows).toHaveLength(1);
    expect(rows[0]!.student_code).toBe('GRS-S-00042');
  });
});

describe('transferEnrollment', () => {
  it('enrols on the new batch before cancelling the old one', async () => {
    const calls: string[] = [];
    apiMutate.mockImplementation(async (path: string) => {
      calls.push(path);
      if (path === '/api/v1/enrollments/') return enrollment({ id: 'new', batch_code: 'GRS-B-002' });
      return enrollment({ id: 'e1', status: 'cancelled' });
    });

    await transferEnrollment({ studentId: 's1', fromEnrollmentId: 'e1', toBatchId: 'b2' });

    expect(calls[0]).toBe('/api/v1/enrollments/');
    expect(calls[1]).toBe('/api/v1/enrollments/e1/status/');
  });

  it('never cancels the old enrolment when the new one fails', async () => {
    apiMutate.mockRejectedValue(new ApiError(409, 'batch_full', 'This batch is full.', 'req-1'));

    await expect(
      transferEnrollment({ studentId: 's1', fromEnrollmentId: 'e1', toBatchId: 'b2' }),
    ).rejects.toThrow('This batch is full.');
    expect(apiMutate).toHaveBeenCalledTimes(1);
    expect(apiMutate).not.toHaveBeenCalledWith(
      expect.stringContaining('/status/'),
      expect.anything(),
    );
  });
});

describe('listEnrolmentDestinations', () => {
  /**
   * A destination is a batch that can accept an enrolment. The pickers used to
   * offer every non-archived batch — a cancelled one and sixteen completed ones
   * among them — thirty rows at a time, so the server's refusal arrived after
   * the operator had chosen, and a live batch below the cut could not be
   * reached from the list at all.
   */
  it('asks only for the statuses that can accept an enrolment, uncapped', async () => {
    apiFetch.mockResolvedValue(page([]));

    await listEnrolmentDestinations({ search: 'devops' });

    const paths = apiFetch.mock.calls.map((call) => String(call[0]));
    expect(paths).toHaveLength(2);
    expect(paths.some((path) => path.includes('status=upcoming'))).toBe(true);
    expect(paths.some((path) => path.includes('status=active'))).toBe(true);
    expect(paths.every((path) => path.includes('page_size=100'))).toBe(true);
    expect(paths.every((path) => path.includes('search=devops'))).toBe(true);
    // Never a completed, cancelled or archived batch, by any spelling.
    expect(paths.join(' ')).not.toMatch(/status=(completed|cancelled|archived)/);
  });

  it('merges the two pages back into one newest-first list', async () => {
    apiFetch.mockImplementation(async (path: string) =>
      path.includes('status=upcoming')
        ? page([batch('u1', 'upcoming', '2026-10-17'), batch('u2', 'upcoming', '2026-09-29')])
        : page([batch('a1', 'active', '2026-10-01'), batch('a2', 'active', '2026-05-09')]),
    );

    const { batches, isComplete } = await listEnrolmentDestinations();

    expect(batches.map((row) => row.id)).toEqual(['u1', 'a1', 'u2', 'a2']);
    expect(isComplete).toBe(true);
  });

  it('says so when a status has more batches than one page holds', async () => {
    apiFetch.mockImplementation(async (path: string) =>
      path.includes('status=active')
        ? page([batch('a1', 'active', '2026-10-01')], 140)
        : page([]),
    );

    const { isComplete } = await listEnrolmentDestinations();

    expect(isComplete).toBe(false);
  });
});
