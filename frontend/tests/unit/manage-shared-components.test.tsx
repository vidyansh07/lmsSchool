import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ManagerAttentionStrip } from '@/components/manage/attention-strip';
import { RiskFlags } from '@/components/manage/risk-flags';
import { Stat } from '@/components/manage/stat';
import type { ManagerDashboard } from '@/lib/manage';

const mockUseApi = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/use-api', () => ({ useApi: mockUseApi }));

function dashboard(overrides: Partial<ManagerDashboard> = {}): ManagerDashboard {
  return {
    batches: { total: 10, active: 8, behind_schedule: 1, at_risk: 2 },
    students: { total: 100, active: 90, at_risk: 5 },
    trainers: { total: 12, with_overdue_dsr: 1 },
    attention: [],
    as_of: '2026-09-07',
    ...overrides,
  };
}

describe('Stat', () => {
  it('renders a label with its pre-formatted value', () => {
    render(<Stat label="Attendance" value="82%" />);
    expect(screen.getByText('Attendance')).toBeInTheDocument();
    expect(screen.getByText('82%')).toBeInTheDocument();
  });

  it('renders the fallback text handed to it, exactly as given, when there is nothing to show', () => {
    render(<Stat label="Average score" value="Not available" />);
    expect(screen.getByText('Not available')).toBeInTheDocument();
  });

  it('renders an optional hint beneath the value', () => {
    render(<Stat label="Score" value="Not available" hint="Nothing recorded yet" />);
    expect(screen.getByText('Nothing recorded yet')).toBeInTheDocument();
  });
});

describe('RiskFlags', () => {
  it('reads an empty flag list as good news, not a blank cell', () => {
    render(<RiskFlags flags={[]} />);
    expect(screen.getByText('On track')).toBeInTheDocument();
  });

  it('renders each flag with its own readable text, not colour alone', () => {
    render(<RiskFlags flags={['attendance', 'academic']} />);
    expect(screen.getByText('Attendance')).toBeInTheDocument();
    expect(screen.getByText('Assessment average')).toBeInTheDocument();
  });

  it('renders an icon alongside every flag, so colour is never the only signal', () => {
    const { container } = render(<RiskFlags flags={['progress']} />);
    expect(container.querySelectorAll('svg').length).toBeGreaterThan(0);
  });

  it('renders an unrecognised flag rather than silently dropping it', () => {
    render(<RiskFlags flags={['fee_overdue']} />);
    expect(screen.getByText('Fee overdue')).toBeInTheDocument();
  });
});

describe('ManagerAttentionStrip', () => {
  it('shows a loading state while the dashboard is being fetched', () => {
    mockUseApi.mockReturnValue({ data: null, error: null, isLoading: true, reload: vi.fn() });
    render(<ManagerAttentionStrip />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('shows an error with a retry action on failure', () => {
    const reload = vi.fn();
    mockUseApi.mockReturnValue({
      data: null,
      error: { message: 'Could not reach the server.', requestId: 'req-1' },
      isLoading: false,
      reload,
    });
    render(<ManagerAttentionStrip />);
    expect(screen.getByText('Could not reach the server.')).toBeInTheDocument();
    screen.getByRole('button', { name: /try again/i }).click();
    expect(reload).toHaveBeenCalledOnce();
  });

  it('reads an empty attention queue as positively good news', () => {
    mockUseApi.mockReturnValue({
      data: dashboard({ attention: [] }),
      error: null,
      isLoading: false,
      reload: vi.fn(),
    });
    render(<ManagerAttentionStrip />);
    expect(screen.getByText('Nothing needs attention')).toBeInTheDocument();
  });

  it('renders the headline KPI figures as plain, non-clickable numbers', () => {
    mockUseApi.mockReturnValue({ data: dashboard(), error: null, isLoading: false, reload: vi.fn() });
    render(<ManagerAttentionStrip />);
    expect(screen.getByText('Active batches')).toBeInTheDocument();
    expect(screen.getByText('8')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Active batches/ })).not.toBeInTheDocument();
  });

  it('renders a named attention item as a link to its own drill-down', () => {
    mockUseApi.mockReturnValue({
      data: dashboard({
        attention: [
          {
            kind: 'behind_schedule',
            label: 'Batches behind schedule',
            count: 3,
            href: '/manage/batches?status=active',
            severity: 'high',
          },
        ],
      }),
      error: null,
      isLoading: false,
      reload: vi.fn(),
    });
    render(<ManagerAttentionStrip />);
    const link = screen.getByRole('link', { name: /Batches behind schedule/ });
    expect(link).toHaveAttribute('href', '/manage/batches?status=active');
  });
});
