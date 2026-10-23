/**
 * The Admissions card on a student's record, and the Cancel Admission dialog
 * it opens.
 *
 * The figures are the server's. These tests check they are *shown*, never
 * recomputed — and that the one irreversible action on the card says what has
 * already been paid before anybody confirms it.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AdmissionsTab } from '@/components/admissions/admissions-tab';
import { ApiError } from '@/lib/api';
import type { Admission } from '@/lib/admissions-api';

const listAdmissions = vi.hoisted(() => vi.fn());
const cancelAdmission = vi.hoisted(() => vi.fn());
vi.mock('@/lib/admissions-api', () => ({ listAdmissions, cancelAdmission }));

function admission(overrides: Partial<Admission> = {}): Admission {
  return {
    id: 'adm-1',
    student_id: 'student-1',
    student_name: 'Vipul Attri',
    branch_id: 'branch-1',
    branch_name: 'Jaipur',
    academic_year_id: 'y-2026',
    academic_year: '2026',
    admission_date: '2026-10-23',
    status: 'active',
    is_cancelled: false,
    discount_kind: 'flat',
    discount_amount: '0.00',
    discount_percent: null,
    gross_total: '30000.00',
    total_fees: '30000.00',
    note: '',
    money: {
      total: '30000.00',
      paid: '1000.00',
      uncleared: '0.00',
      refund: '0.00',
      balance: '29000.00',
    },
    lines: [
      {
        id: 'line-1',
        kind: 'course',
        course_id: 'c-1',
        course_title: 'Data Analytics',
        label: '',
        name: 'Data Analytics',
        charged_on_id: null,
        quantity: 1,
        unit_fee: '30000.00',
        line_total: '30000.00',
        discount_share: '0.00',
        enrollment_id: 'enrol-1',
      },
    ],
    created_by: 'Deepti Vyas',
    cancelled_at: null,
    cancellation_reason: '',
    created_at: '2026-10-23T09:00:00Z',
    updated_at: '2026-10-23T09:00:00Z',
    ...overrides,
  };
}

function page(rows: Admission[]) {
  return { count: rows.length, page: 1, page_size: 20, total_pages: 1, next: null, previous: null, results: rows };
}

describe('AdmissionsTab', () => {
  beforeEach(() => {
    listAdmissions.mockReset().mockResolvedValue(page([admission()]));
    cancelAdmission.mockReset().mockResolvedValue(admission({ is_cancelled: true }));
  });

  it('shows the course, the year and the five figures the desk reads across', async () => {
    render(<AdmissionsTab studentId="student-1" canManage />);

    expect(await screen.findByRole('link', { name: 'Data Analytics' })).toBeInTheDocument();
    expect(screen.getByText('(2026)')).toBeInTheDocument();
    expect(screen.getByText('Rs. 30,000')).toBeInTheDocument();
    expect(screen.getByText('Rs. 1,000')).toBeInTheDocument();
    expect(screen.getByText('Rs. 29,000')).toBeInTheDocument();
    for (const label of ['Total', 'Paid', 'Uncleared', 'Refund', 'Balance']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it('offers Pay, edit, Cancel Admission — and no Delete once money has been taken', async () => {
    render(<AdmissionsTab studentId="student-1" canManage />);
    await screen.findByRole('link', { name: 'Data Analytics' });

    expect(screen.getByRole('link', { name: /Pay/ })).toHaveAttribute(
      'href',
      '/students/student-1/admissions/adm-1/payment',
    );
    expect(screen.getByRole('link', { name: /edit/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Cancel Admission/ })).toBeInTheDocument();
    // A receipt that points at nothing is the one thing a ledger must not
    // allow, so Delete is absent the moment anything has been paid.
    expect(screen.queryByRole('button', { name: /Delete/ })).not.toBeInTheDocument();
  });

  it('offers nothing that writes to somebody who may only read', async () => {
    render(<AdmissionsTab studentId="student-1" canManage={false} />);
    await screen.findByRole('link', { name: 'Data Analytics' });

    expect(screen.queryByRole('link', { name: /New Admission/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Cancel Admission/ })).not.toBeInTheDocument();
  });

  it('says what has already been paid before anybody cancels', async () => {
    render(<AdmissionsTab studentId="student-1" canManage />);
    await screen.findByRole('link', { name: 'Data Analytics' });
    fireEvent.click(screen.getByRole('button', { name: /Cancel Admission/ }));

    const dialog = await screen.findByRole('dialog');
    expect(
      within(dialog).getByText('Rs. 1,000 paid by student and Rs. 0 is refunded.'),
    ).toBeInTheDocument();
  });

  it('will not cancel without a reason', async () => {
    render(<AdmissionsTab studentId="student-1" canManage />);
    await screen.findByRole('link', { name: 'Data Analytics' });
    fireEvent.click(screen.getByRole('button', { name: /Cancel Admission/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Submit' }));

    expect(await screen.findByText('Say why it was cancelled.')).toBeInTheDocument();
    expect(cancelAdmission).not.toHaveBeenCalled();
  });

  it('cancels with a reason and reloads the list', async () => {
    render(<AdmissionsTab studentId="student-1" canManage />);
    await screen.findByRole('link', { name: 'Data Analytics' });
    fireEvent.click(screen.getByRole('button', { name: /Cancel Admission/ }));
    fireEvent.change(await screen.findByLabelText('Reason'), {
      target: { value: 'Moved city.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Submit' }));

    await waitFor(() => expect(cancelAdmission).toHaveBeenCalledWith('adm-1', 'Moved city.'));
    await waitFor(() => expect(listAdmissions).toHaveBeenCalledTimes(2));
  });

  it('refuses a refund larger than what was paid', async () => {
    render(<AdmissionsTab studentId="student-1" canManage />);
    await screen.findByRole('link', { name: 'Data Analytics' });
    fireEvent.click(screen.getByRole('button', { name: /Cancel Admission/ }));
    fireEvent.change(await screen.findByLabelText('Reason'), { target: { value: 'Moved.' } });
    fireEvent.click(screen.getByLabelText(/Do You want add refund/));
    fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '5000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Submit' }));

    expect(await screen.findByText('More than the Rs. 1,000 paid.')).toBeInTheDocument();
    expect(cancelAdmission).not.toHaveBeenCalled();
  });

  it('cannot offer a refund on an admission nobody has paid', async () => {
    listAdmissions.mockResolvedValue(
      page([
        admission({
          money: {
            total: '30000.00',
            paid: '0.00',
            uncleared: '0.00',
            refund: '0.00',
            balance: '30000.00',
          },
        }),
      ]),
    );
    render(<AdmissionsTab studentId="student-1" canManage />);
    await screen.findByRole('link', { name: 'Data Analytics' });
    fireEvent.click(screen.getByRole('button', { name: /Cancel Admission/ }));

    expect(await screen.findByLabelText(/Do You want add refund/)).toBeDisabled();
    expect(screen.getByText('(nothing has been paid)')).toBeInTheDocument();
  });

  it('marks a cancelled admission and stops offering to cancel it again', async () => {
    listAdmissions.mockResolvedValue(
      page([admission({ is_cancelled: true, status: 'cancelled', cancellation_reason: 'Moved city.' })]),
    );
    render(<AdmissionsTab studentId="student-1" canManage />);

    expect(await screen.findByText('Cancelled')).toBeInTheDocument();
    expect(screen.getByText('Cancelled: Moved city.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Cancel Admission/ })).not.toBeInTheDocument();
  });

  it('says so plainly when there are none, and offers to record one', async () => {
    listAdmissions.mockResolvedValue(page([]));
    render(<AdmissionsTab studentId="student-1" canManage />);

    expect(await screen.findByText('No admissions yet')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /New Admission/ })).toHaveAttribute(
      'href',
      '/students/student-1/admissions/new',
    );
  });

  it('offers a retry when the list fails to load', async () => {
    listAdmissions.mockRejectedValue(new ApiError(500, 'server_error', 'Down.', 'req-1'));
    render(<AdmissionsTab studentId="student-1" canManage />);

    expect(await screen.findByText('Down.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /try again/i }));
    await waitFor(() => expect(listAdmissions).toHaveBeenCalledTimes(2));
  });
});
