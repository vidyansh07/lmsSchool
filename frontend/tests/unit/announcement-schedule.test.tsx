/**
 * Announcements (`app/announcements/page.tsx`, ERP Phase 19): "Schedule for
 * later" on the compose form, the new `role`/`branch` audiences, and
 * cancelling an already-scheduled announcement.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AnnouncementsPage from '@/app/announcements/page';
import type { Announcement, BatchListRow, Branch, Paginated } from '@/types/api';

const listAnnouncements = vi.hoisted(() => vi.fn());
const createAnnouncement = vi.hoisted(() => vi.fn());
const scheduleAnnouncement = vi.hoisted(() => vi.fn());
const cancelAnnouncement = vi.hoisted(() => vi.fn());
const publishAnnouncement = vi.hoisted(() => vi.fn());
const archiveAnnouncement = vi.hoisted(() => vi.fn());
vi.mock('@/lib/communication', async () => {
  const actual = await vi.importActual<typeof import('@/lib/communication')>('@/lib/communication');
  return {
    ...actual,
    listAnnouncements,
    createAnnouncement,
    scheduleAnnouncement,
    cancelAnnouncement,
    publishAnnouncement,
    archiveAnnouncement,
  };
});

const listBatches = vi.hoisted(() => vi.fn());
vi.mock('@/lib/batches', () => ({ listBatches }));

const listBranches = vi.hoisted(() => vi.fn());
vi.mock('@/lib/organisation', () => ({ listBranches }));

const auth = vi.hoisted(() => ({
  role: 'admin',
  capabilities: ['announcement.manage_any'] as string[],
}));
vi.mock('@/components/auth-provider', () => ({
  useAuth: () => ({
    user: { role: auth.role, capabilities: auth.capabilities },
    isLoading: false,
    can: (capability: string) => auth.capabilities.includes(capability),
  }),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => '/announcements',
}));

function emptyPage<T>(): Paginated<T> {
  return { count: 0, page: 1, page_size: 25, total_pages: 1, next: null, previous: null, results: [] };
}

function announcement(overrides: Partial<Announcement> = {}): Announcement {
  return {
    id: 'a-1',
    title: 'Exam week',
    body: 'Details inside.',
    audience: 'batch',
    course: null,
    course_title: null,
    batch: null,
    batch_code: null,
    is_pinned: false,
    status: 'draft',
    publish_at: null,
    published_at: null,
    expires_at: null,
    created_by_name: 'Admin',
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  auth.role = 'admin';
  auth.capabilities = ['announcement.manage_any'];
  listAnnouncements.mockResolvedValue(emptyPage<Announcement>());
  listBatches.mockResolvedValue(emptyPage<BatchListRow>());
  listBranches.mockResolvedValue(emptyPage<Branch>());
});

describe('Announcements — schedule for later', () => {
  it('creates the draft with publish_at and then schedules it', async () => {
    createAnnouncement.mockResolvedValue(announcement({ id: 'a-new' }));
    scheduleAnnouncement.mockResolvedValue(announcement({ id: 'a-new', status: 'scheduled' }));
    render(<AnnouncementsPage />);

    fireEvent.click(await screen.findByRole('button', { name: /new announcement/i }));
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Exam week' } });
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'Details inside.' } });
    fireEvent.change(screen.getByLabelText('Audience'), { target: { value: 'everyone' } });
    fireEvent.change(screen.getByLabelText('Schedule for later'), {
      target: { value: '2026-10-01T09:00' },
    });

    fireEvent.click(screen.getByRole('button', { name: /^schedule$/i }));

    await waitFor(() =>
      expect(createAnnouncement).toHaveBeenCalledWith(
        expect.objectContaining({ title: 'Exam week', publish_at: expect.any(String) }),
      ),
    );
    await waitFor(() => expect(scheduleAnnouncement).toHaveBeenCalledWith('a-new', expect.any(String)));
    expect(await screen.findByText(/scheduled for/i)).toBeInTheDocument();
  });

  it('without a date, saves as an immediate draft and never calls schedule', async () => {
    createAnnouncement.mockResolvedValue(announcement({ id: 'a-new' }));
    render(<AnnouncementsPage />);

    fireEvent.click(await screen.findByRole('button', { name: /new announcement/i }));
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Exam week' } });
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'Details inside.' } });
    fireEvent.change(screen.getByLabelText('Audience'), { target: { value: 'everyone' } });

    fireEvent.click(screen.getByRole('button', { name: /save as a draft/i }));

    await waitFor(() => expect(createAnnouncement).toHaveBeenCalled());
    expect(scheduleAnnouncement).not.toHaveBeenCalled();
  });

  it('shows Cancel schedule on a scheduled row, and it cancels the schedule', async () => {
    listAnnouncements.mockResolvedValue({
      ...emptyPage<Announcement>(),
      count: 1,
      results: [announcement({ status: 'scheduled', publish_at: '2026-10-01T09:00:00Z' })],
    });
    cancelAnnouncement.mockResolvedValue(announcement({ status: 'cancelled' }));
    render(<AnnouncementsPage />);

    const button = await screen.findByRole('button', { name: /cancel schedule/i });
    fireEvent.click(button);
    await waitFor(() => expect(cancelAnnouncement).toHaveBeenCalledWith('a-1'));
  });

  it('offers the role and branch audiences only to someone who may announce to all', async () => {
    auth.capabilities = [];
    render(<AnnouncementsPage />);
    fireEvent.click(await screen.findByRole('button', { name: /new announcement/i }));
    const options = Array.from(screen.getByLabelText('Audience').querySelectorAll('option')).map(
      (option) => option.getAttribute('value'),
    );
    expect(options).toEqual(['batch']);
  });
});
