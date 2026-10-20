import { render, screen } from '@testing-library/react';
import { Eye, IndianRupee, Pencil, Send, Trash2 } from 'lucide-react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { RowActions, type RowAction } from '@/components/row-actions';

/**
 * A table row used to offer one link, whatever the person looking at it was
 * allowed to do. These check the half that matters: that the column offers
 * exactly the actions this caller may perform, and never one they may not.
 *
 * This is presentation, not protection. Every endpoint behind these actions
 * makes its own decision, and these tests assert what is drawn — not what is
 * permitted.
 */
const mockAuth = vi.hoisted(() => ({ capabilities: [] as string[] }));

vi.mock('@/components/auth-provider', () => ({
  useAuth: () => ({
    can: (capability: string) => mockAuth.capabilities.includes(capability),
  }),
}));

const ACTIONS: RowAction[] = [
  { label: 'Open', icon: Eye, href: '/admissions/1' },
  { label: 'Edit', icon: Pencil, href: '/admissions/1?edit=1', capability: 'student.update_any' },
  { label: 'Fees', icon: IndianRupee, href: '/fees?student=1', capability: 'fee.view_any' },
  { label: 'Message', icon: Send, href: '/communication/new', capability: 'communication.send' },
];

function renderFor(capabilities: string[], actions: RowAction[] = ACTIONS) {
  mockAuth.capabilities = capabilities;
  return render(<RowActions actions={actions} subject="Asha Rao" />);
}

describe('RowActions', () => {
  beforeEach(() => {
    mockAuth.capabilities = [];
  });

  it('offers an action that needs no permission', () => {
    renderFor([]);

    expect(screen.getByLabelText('Open Asha Rao')).toBeInTheDocument();
  });

  it('does not render an action the caller lacks the permission for', () => {
    renderFor([]);

    // Absent, not disabled: a control that never becomes usable is a puzzle,
    // and in a list of fifty rows it is fifty puzzles.
    expect(screen.queryByLabelText('Edit Asha Rao')).not.toBeInTheDocument();
    expect(screen.queryByText('Edit')).not.toBeInTheDocument();
  });

  it('offers an action once the caller has the permission', () => {
    renderFor(['student.update_any']);

    expect(screen.getByLabelText('Edit Asha Rao')).toBeInTheDocument();
  });

  it('names the row, so a screen reader hears which one', () => {
    renderFor(['student.update_any']);

    expect(screen.getByLabelText('Edit Asha Rao')).toBeInTheDocument();
    expect(screen.queryByLabelText('Edit')).not.toBeInTheDocument();
  });

  it('gives a caller with one permission a button, not a menu holding one item', () => {
    renderFor([]);

    expect(screen.queryByLabelText('More actions for Asha Rao')).not.toBeInTheDocument();
  });

  it('folds the rest into a menu once there are more than two', () => {
    renderFor(['student.update_any', 'fee.view_any', 'communication.send']);

    expect(screen.getByLabelText('Open Asha Rao')).toBeInTheDocument();
    expect(screen.getByLabelText('Edit Asha Rao')).toBeInTheDocument();
    expect(screen.getByLabelText('More actions for Asha Rao')).toBeInTheDocument();
  });

  it('counts only the actions the caller may use when deciding what to fold', () => {
    // The first two *permitted*, not the first two listed. This caller may use
    // Open and Fees — Edit sits between them in the list and is skipped — so
    // both fit inline and nothing folds.
    renderFor(['fee.view_any']);

    expect(screen.getByLabelText('Open Asha Rao')).toBeInTheDocument();
    expect(screen.getByLabelText('Fees Asha Rao')).toBeInTheDocument();
    expect(screen.queryByLabelText('More actions for Asha Rao')).not.toBeInTheDocument();
  });

  it('renders nothing at all when the caller may do nothing', () => {
    const { container } = renderFor([], ACTIONS.slice(1));

    expect(container).toBeEmptyDOMElement();
  });

  it('keeps a destructive action out of the inline buttons', () => {
    mockAuth.capabilities = ['student.update_any', 'user.set_active'];
    render(
      <RowActions
        subject="Asha Rao"
        actions={[
          { label: 'Open', icon: Eye, href: '/x' },
          {
            label: 'Deactivate',
            icon: Trash2,
            capability: 'user.set_active',
            destructive: true,
            onSelect: () => {},
          },
        ]}
      />,
    );

    // Two permitted actions would otherwise both fit inline; a destructive
    // one belongs
    // behind the deliberate step of opening a menu.
    expect(screen.queryByLabelText('Deactivate Asha Rao')).not.toBeInTheDocument();
    expect(screen.getByLabelText('More actions for Asha Rao')).toBeInTheDocument();
  });

  it('keeps a row-specific refusal visible, with its reason', () => {
    // Different from a missing permission: this person may delete, but not
    // this row, and knowing why is useful.
    mockAuth.capabilities = ['student.update_any'];
    render(
      <RowActions
        subject="Asha Rao"
        actions={[
          {
            label: 'Edit',
            icon: Pencil,
            capability: 'student.update_any',
            disabledReason: 'This student has left.',
            onSelect: () => {},
          },
        ]}
      />,
    );

    const control = screen.getByLabelText('Edit Asha Rao');
    expect(control).toBeDisabled();
  });

  it('does not let a row action trigger the row itself', () => {
    // Rows in this app open on click. "Delete" opening the record instead
    // would be the worst possible miss.
    const rowClick = vi.fn();
    mockAuth.capabilities = ['student.update_any'];
    render(
      <table>
        <tbody>
          <tr onClick={rowClick}>
            <td>
              <RowActions
                subject="Asha Rao"
                actions={[
                  { label: 'Edit', icon: Pencil, capability: 'student.update_any', onSelect: () => {} },
                ]}
              />
            </td>
          </tr>
        </tbody>
      </table>,
    );

    screen.getByLabelText('Edit Asha Rao').click();

    expect(rowClick).not.toHaveBeenCalled();
  });
});
