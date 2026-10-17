/**
 * Ready to admit: Meritto's leads not yet registered, each with its way to
 * the pre-filled registration.
 */
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ReadyToAdmitPage from '@/app/admissions/ready/page';

const useApi = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/use-api', () => ({ useApi }));
vi.mock('@/components/require-auth', () => ({
  RequireAuth: ({ children }: { children: React.ReactNode }) => children,
}));

const LEAD = {
  id: 'e-2',
  full_name: 'Aman Verma',
  mobile: '9876500001',
  email: 'aman@example.test',
  course: 'DevOps',
  external_stage: 'Ready for admission',
  external_owner: 'Pooja (Meritto)',
  created_at: '2026-10-17T10:00:00Z',
  can_register: true,
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ReadyToAdmitPage', () => {
  it("lists Meritto's ready leads with a register button", () => {
    useApi.mockReturnValue({
      data: { count: 1, next: null, previous: null, results: [LEAD] },
      error: null,
      isLoading: false,
      reload: vi.fn(),
    });
    render(<ReadyToAdmitPage />);
    expect(useApi).toHaveBeenCalledWith('/api/v1/enquiries/?ready_to_admit=true');
    expect(screen.getByRole('link', { name: 'Aman Verma' })).toHaveAttribute('href', '/enquiries/e-2');
    expect(screen.getByText('Ready for admission')).toBeInTheDocument();
    expect(screen.getByText('Pooja (Meritto)')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Register' })).toHaveAttribute(
      'href',
      '/admissions/new?enquiry=e-2',
    );
  });

  it('says when nothing is waiting', () => {
    useApi.mockReturnValue({
      data: { count: 0, next: null, previous: null, results: [] },
      error: null,
      isLoading: false,
      reload: vi.fn(),
    });
    render(<ReadyToAdmitPage />);
    expect(screen.getByText('Nothing waiting')).toBeInTheDocument();
  });
});
