/**
 * `StudentTimeline` (Phase 10): mixed-kind rendering, kind filters narrowing
 * the request, load-more appending without duplicates, and every state
 * (loading, empty, error, an unrecognized kind falling back generically).
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { StudentTimeline } from '@/components/students/timeline';
import type { TimelineEntry, TimelineResponse } from '@/types/api';

const getStudentTimeline = vi.hoisted(() => vi.fn());
vi.mock('@/lib/timeline', () => ({ getStudentTimeline }));

function entry(overrides: Partial<TimelineEntry>): TimelineEntry {
  return {
    id: 'e1',
    occurred_at: '2026-09-14T10:00:00Z',
    kind: 'enrollment_started',
    title: 'Untitled event',
    summary: null,
    href: null,
    actor: null,
    ...overrides,
  };
}

function page(results: TimelineEntry[], nextCursor: string | null = null): TimelineResponse {
  return { results, next_cursor: nextCursor };
}

describe('StudentTimeline', () => {
  it('shows a loading state, then renders mixed-kind entries', async () => {
    let resolve!: (value: TimelineResponse) => void;
    getStudentTimeline.mockReturnValueOnce(
      new Promise((r) => {
        resolve = r;
      }),
    );

    render(<StudentTimeline studentId="s1" />);
    expect(screen.getByRole('status')).toBeInTheDocument();

    resolve(
      page([
        entry({ id: 'e1', kind: 'enrollment_started', title: 'Enrolled in Full Stack', occurred_at: '2026-09-14T10:00:00Z' }),
        entry({
          id: 'e2',
          kind: 'dsr_submitted',
          title: 'Daily report submitted',
          summary: 'Covered arrays and loops',
          href: '/dsr/e2',
          actor: { id: 'u1', name: 'Priya Trainer', role: 'trainer' },
          occurred_at: '2026-09-14T15:00:00Z',
        }),
      ]),
    );

    expect(await screen.findByText('Enrolled in Full Stack')).toBeInTheDocument();
    expect(screen.getByText('Covered arrays and loops')).toBeInTheDocument();
    expect(screen.getByText(/Priya Trainer/)).toBeInTheDocument();
    // "Daily report submitted" is also a filter chip's label, so the entry
    // itself is found through its link (the chip is a <button>, not a link).
    expect(screen.getByRole('link', { name: 'Daily report submitted' })).toHaveAttribute(
      'href',
      '/dsr/e2',
    );
  });

  it('renders an unrecognized kind with the generic fallback instead of crashing', async () => {
    getStudentTimeline.mockResolvedValueOnce(
      page([
        entry({ id: 'e9', kind: 'communication_delivered', title: 'WhatsApp reminder sent', occurred_at: '2026-09-14T09:00:00Z' }),
      ]),
    );

    render(<StudentTimeline studentId="s1" />);

    expect(await screen.findByText('WhatsApp reminder sent')).toBeInTheDocument();
    expect(screen.getByText('Communication Delivered')).toBeInTheDocument();
  });

  it('narrows the request params when a kind filter chip is toggled', async () => {
    getStudentTimeline.mockResolvedValue(page([]));
    render(<StudentTimeline studentId="s1" />);

    await waitFor(() =>
      expect(getStudentTimeline).toHaveBeenLastCalledWith(
        's1',
        expect.objectContaining({ kinds: undefined }),
      ),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Attendance' }));
    await waitFor(() =>
      expect(getStudentTimeline).toHaveBeenLastCalledWith(
        's1',
        expect.objectContaining({ kinds: ['attendance_day'] }),
      ),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Assessment result' }));
    await waitFor(() =>
      expect(getStudentTimeline).toHaveBeenLastCalledWith(
        's1',
        expect.objectContaining({ kinds: ['attendance_day', 'assessment_result'] }),
      ),
    );
  });

  it('loads more and appends without duplicating an entry the next page repeats', async () => {
    getStudentTimeline.mockResolvedValueOnce(
      page([entry({ id: 'e1', title: 'First event', occurred_at: '2026-09-14T10:00:00Z' })], 'cursor-1'),
    );
    render(<StudentTimeline studentId="s1" />);

    expect(await screen.findByText('First event')).toBeInTheDocument();

    getStudentTimeline.mockResolvedValueOnce(
      page(
        [
          // The same id the first page already returned, as a cursor overlap
          // would produce, plus one genuinely new row.
          entry({ id: 'e1', title: 'First event', occurred_at: '2026-09-14T10:00:00Z' }),
          entry({ id: 'e2', title: 'Second event', occurred_at: '2026-09-13T10:00:00Z' }),
        ],
        null,
      ),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Load more' }));

    expect(await screen.findByText('Second event')).toBeInTheDocument();
    expect(screen.getAllByTestId('timeline-entry')).toHaveLength(2);
    // The cursor for the second call must be the first page's `next_cursor`.
    expect(getStudentTimeline).toHaveBeenLastCalledWith(
      's1',
      expect.objectContaining({ cursor: 'cursor-1' }),
    );
    // "Load more" disappears once `next_cursor` comes back null.
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument();
  });

  it('shows an empty state when there is nothing to show', async () => {
    getStudentTimeline.mockResolvedValueOnce(page([]));
    render(<StudentTimeline studentId="s1" />);
    expect(await screen.findByText('Nothing recorded yet')).toBeInTheDocument();
  });

  it('shows an error state with a retry that re-fetches', async () => {
    getStudentTimeline.mockRejectedValueOnce(new Error('boom'));
    render(<StudentTimeline studentId="s1" />);

    expect(await screen.findByText('Could not load the timeline')).toBeInTheDocument();

    getStudentTimeline.mockResolvedValueOnce(page([entry({ id: 'e1', title: 'Recovered event' })]));
    fireEvent.click(screen.getByRole('button', { name: /Try again/i }));

    expect(await screen.findByText('Recovered event')).toBeInTheDocument();
  });
});
