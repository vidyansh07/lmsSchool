/**
 * Admission Details — step 3, where the money starts.
 *
 * The three behaviours worth fixing in place:
 *
 * 1. choosing a course fills its fee from the catalogue and the counsellor can
 *    overrule it — that figure is what gets frozen on the admission;
 * 2. an additional fee is charged *on* a course line, and goes with it when
 *    that course is removed, because a fee charged on nothing has no ledger;
 * 3. the totals shown match what is sent, and the discount is sent as what was
 *    typed rather than pre-applied — the server splits it.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AdmissionDetailsForm } from '@/app/students/[id]/admissions/new/page';
import { ApiError } from '@/lib/api';

const listAcademicYears = vi.hoisted(() => vi.fn());
vi.mock('@/lib/academic-years', () => ({ listAcademicYears }));

const createAdmission = vi.hoisted(() => vi.fn());
vi.mock('@/lib/admissions-api', () => ({ createAdmission }));

const listCourses = vi.hoisted(() => vi.fn());
vi.mock('@/lib/courses', () => ({ listCourses }));

const push = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

function course(id: string, title: string, fee: string | null, category = 'Python') {
  return {
    id,
    code: id.toUpperCase(),
    slug: id,
    title,
    short_description: '',
    category_name: category,
    category_slug: category.toLowerCase(),
    difficulty: 'beginner',
    default_fee: fee,
    estimated_duration_minutes: null,
    status: 'published',
    visibility: 'public',
    thumbnail_url: null,
    module_count: 1,
    lesson_count: 1,
    published_at: null,
    created_at: '2026-01-01',
  };
}

describe('AdmissionDetailsForm', () => {
  beforeEach(() => {
    push.mockReset();
    createAdmission.mockReset().mockResolvedValue({ id: 'adm-1' });
    listAcademicYears.mockReset().mockResolvedValue([
      { id: 'y-2026', name: '2026', starts_on: null, ends_on: null, is_current: true, is_closed: false },
      { id: 'y-2025', name: '2025', starts_on: null, ends_on: null, is_current: false, is_closed: true },
    ]);
    listCourses.mockReset().mockResolvedValue({
      count: 2,
      results: [
        course('data-analytics', 'Data Analytics', '30000.00'),
        course('linux', 'Linux RHCSA', '12000.00', 'Linux'),
      ],
    });
  });

  async function ready() {
    render(<AdmissionDetailsForm studentId="student-1" />);
    await screen.findByText('Course Information');
  }

  it('lays the table out as the desk reads it', async () => {
    await ready();
    expect(screen.getByText('Basic Information')).toBeInTheDocument();
    expect(screen.getByLabelText('Admission Date')).toBeInTheDocument();
    for (const header of ['Academic Year', 'Course', 'Qty', 'Fees']) {
      expect(screen.getAllByText(header).length).toBeGreaterThan(0);
    }
    expect(screen.getByRole('button', { name: /Course$/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Additional Fee/ })).toBeInTheDocument();
    expect(screen.getByText('Discount if any?')).toBeInTheDocument();
    expect(screen.getByText('Total Fees')).toBeInTheDocument();
  });

  it('opens on the current academic year and will not offer a closed one', async () => {
    await ready();
    const select = screen.getByLabelText('Academic Year') as HTMLSelectElement;
    expect(select.value).toBe('y-2026');
    const closed = within(select).getByRole('option', { name: '2025 (closed)' });
    expect(closed).toBeDisabled();
  });

  it('groups the courses under their standard', async () => {
    await ready();
    const select = screen.getByLabelText('Course 1');
    expect(within(select).getByRole('group', { name: 'Python' })).toBeInTheDocument();
    expect(within(select).getByRole('group', { name: 'Linux' })).toBeInTheDocument();
  });

  it('fills the fee from the catalogue, and lets the counsellor overrule it', async () => {
    await ready();
    fireEvent.change(screen.getByLabelText('Course 1'), { target: { value: 'data-analytics' } });
    expect(screen.getByLabelText('Fees 1')).toHaveValue(30000);
    expect(screen.getByTestId('total-fees')).toHaveTextContent('Rs. 30,000');

    fireEvent.change(screen.getByLabelText('Fees 1'), { target: { value: '27000' } });
    expect(screen.getByTestId('total-fees')).toHaveTextContent('Rs. 27,000');
  });

  it('multiplies by the quantity', async () => {
    await ready();
    fireEvent.change(screen.getByLabelText('Course 1'), { target: { value: 'linux' } });
    fireEvent.click(screen.getByRole('button', { name: 'One more on line 1' }));
    expect(screen.getByLabelText('Qty 1')).toHaveValue(2);
    expect(screen.getByTestId('total-fees')).toHaveTextContent('Rs. 24,000');
  });

  it('never drops the quantity below one', async () => {
    await ready();
    fireEvent.click(screen.getByRole('button', { name: 'One fewer on line 1' }));
    expect(screen.getByLabelText('Qty 1')).toHaveValue(1);
  });

  it('takes a flat discount off the total without applying it to the lines', async () => {
    await ready();
    fireEvent.change(screen.getByLabelText('Course 1'), { target: { value: 'data-analytics' } });
    fireEvent.change(screen.getByLabelText('Discount'), { target: { value: '2000' } });

    expect(screen.getByTestId('gross-total')).toHaveTextContent('Rs. 30,000');
    expect(screen.getByTestId('total-fees')).toHaveTextContent('Rs. 28,000');

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(createAdmission).toHaveBeenCalled());
    const payload = createAdmission.mock.calls[0]![0];
    // Sent as typed. The server splits it across the courses — a screen that
    // pre-applies it can disagree with the ledger.
    expect(payload.discount_kind).toBe('flat');
    expect(payload.discount_value).toBe('2000');
    expect(payload.lines[0].unit_fee).toBe('30000.00');
  });

  it('reads a percentage discount as a percentage', async () => {
    await ready();
    fireEvent.change(screen.getByLabelText('Course 1'), { target: { value: 'data-analytics' } });
    fireEvent.change(screen.getByLabelText('Discount kind'), { target: { value: 'percent' } });
    fireEvent.change(screen.getByLabelText('Discount'), { target: { value: '10' } });

    expect(screen.getByTestId('total-fees')).toHaveTextContent('Rs. 27,000');
  });

  it('refuses a percentage over a hundred', async () => {
    await ready();
    fireEvent.change(screen.getByLabelText('Course 1'), { target: { value: 'data-analytics' } });
    fireEvent.change(screen.getByLabelText('Discount kind'), { target: { value: 'percent' } });
    fireEvent.change(screen.getByLabelText('Discount'), { target: { value: '120' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('A discount cannot be more than 100%.')).toBeInTheDocument();
    expect(createAdmission).not.toHaveBeenCalled();
  });

  it('sends an additional fee with the index of the course it is charged on', async () => {
    await ready();
    fireEvent.change(screen.getByLabelText('Course 1'), { target: { value: 'data-analytics' } });
    fireEvent.click(screen.getByRole('button', { name: /Additional Fee/ }));
    fireEvent.change(screen.getByLabelText('Additional fee 2'), { target: { value: 'Exam fee' } });
    fireEvent.change(screen.getByLabelText('Fees 2'), { target: { value: '2000' } });

    expect(screen.getByTestId('gross-total')).toHaveTextContent('Rs. 32,000');

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(createAdmission).toHaveBeenCalled());
    expect(createAdmission.mock.calls[0]![0].lines).toEqual([
      { kind: 'course', course: 'data-analytics', quantity: 1, unit_fee: '30000.00' },
      { kind: 'additional_fee', label: 'Exam fee', quantity: 1, unit_fee: '2000', charged_on: 0 },
    ]);
  });

  it('removes an additional fee along with the course it was charged on', async () => {
    await ready();
    fireEvent.change(screen.getByLabelText('Course 1'), { target: { value: 'data-analytics' } });
    fireEvent.click(screen.getByRole('button', { name: /Additional Fee/ }));
    fireEvent.change(screen.getByLabelText('Additional fee 2'), { target: { value: 'Exam fee' } });

    fireEvent.click(screen.getByRole('button', { name: 'Remove line 1' }));

    // A fee charged on nothing has no ledger to sit in, so it goes too, and
    // the table falls back to one empty course row rather than none.
    expect(screen.queryByLabelText('Additional fee 2')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Course 1')).toHaveValue('');
  });

  it('offers no additional fee until there is a course to charge it on', async () => {
    listCourses.mockResolvedValue({ count: 0, results: [] });
    await ready();
    fireEvent.click(screen.getByRole('button', { name: 'Remove line 1' }));
    // One blank course row remains, so the button is available but the line
    // itself still has to name a course before it can be saved.
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('Choose the course on every line.')).toBeInTheDocument();
    expect(createAdmission).not.toHaveBeenCalled();
  });

  it('names an unnamed additional fee rather than sending a blank one', async () => {
    await ready();
    fireEvent.change(screen.getByLabelText('Course 1'), { target: { value: 'data-analytics' } });
    fireEvent.click(screen.getByRole('button', { name: /Additional Fee/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('Name every additional fee.')).toBeInTheDocument();
    expect(createAdmission).not.toHaveBeenCalled();
  });

  it('goes on to the payment step once the admission is recorded', async () => {
    await ready();
    fireEvent.change(screen.getByLabelText('Course 1'), { target: { value: 'data-analytics' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(push).toHaveBeenCalledWith('/students/student-1/admissions/adm-1/payment'),
    );
  });

  it('shows what the server said when it refuses', async () => {
    createAdmission.mockRejectedValue(
      new ApiError(400, 'validation_error', 'No.', 'req-1', {
        lines: ['An admission needs at least one course.'],
      }),
    );
    await ready();
    fireEvent.change(screen.getByLabelText('Course 1'), { target: { value: 'data-analytics' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(
      await screen.findByText('An admission needs at least one course.'),
    ).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
