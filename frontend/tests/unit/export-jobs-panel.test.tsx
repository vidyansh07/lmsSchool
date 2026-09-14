/** Your exports: a ready job has a download link, a failed one shows why. */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ExportJobsPanel } from '@/components/export-jobs-panel';
import type { ExportJob } from '@/types/api';

const listExportJobs = vi.hoisted(() => vi.fn());
vi.mock('@/lib/reporting', async () => {
  const actual = await vi.importActual<typeof import('@/lib/reporting')>('@/lib/reporting');
  return { ...actual, listExportJobs, cancelExport: vi.fn() };
});

const jobs: ExportJob[] = [
  {
    id: 'j1',
    report_key: 'fee_payments',
    format: 'xlsx',
    filters: {},
    status: 'completed',
    requested_by_email: 'admin@example.test',
    queued_at: '2026-09-14T10:00:00Z',
    started_at: '2026-09-14T10:00:01Z',
    finished_at: '2026-09-14T10:00:05Z',
    row_count: 3120,
    error: '',
    expires_at: '2026-09-28T10:00:05Z',
    download_url: '/api/v1/reports/exports/j1/download/',
  },
  {
    id: 'j2',
    report_key: 'students',
    format: 'pdf',
    filters: {},
    status: 'failed',
    requested_by_email: 'admin@example.test',
    queued_at: '2026-09-14T11:00:00Z',
    started_at: null,
    finished_at: '2026-09-14T11:00:02Z',
    row_count: 0,
    error: 'More than 2,000 rows for a PDF.',
    expires_at: null,
    download_url: null,
  },
];

describe('ExportJobsPanel', () => {
  it('lists jobs with a download for the ready one and the reason for the failed one', async () => {
    listExportJobs.mockResolvedValue(jobs);
    render(<ExportJobsPanel />);
    expect(await screen.findByText('fee payments')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /download/i })).toHaveAttribute(
      'href',
      expect.stringContaining('/api/v1/reports/exports/j1/download/'),
    );
    expect(screen.getByText('Ready')).toBeInTheDocument();
    expect(screen.getByText('More than 2,000 rows for a PDF.')).toBeInTheDocument();
  });
});
