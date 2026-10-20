import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { PasswordInput } from '@/components/ui/input';

/**
 * Every password field in the product was a bare `type="password"` with no way
 * to see what had been typed — seven of them, across four screens. On a phone,
 * with a generated password pasted out of an email, that is the difference
 * between signing in and not knowing why you cannot.
 */
describe('PasswordInput', () => {
  it('hides the value until asked', () => {
    render(<PasswordInput aria-label="Password" defaultValue="hunter2" />);
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password');
  });

  it('reveals and hides again, and says what the button will do next', () => {
    render(<PasswordInput aria-label="Password" defaultValue="hunter2" />);

    const toggle = screen.getByRole('button', { name: 'Show the password' });
    expect(toggle).toHaveAttribute('aria-pressed', 'false');

    fireEvent.click(toggle);
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'text');

    const hide = screen.getByRole('button', { name: 'Hide the password' });
    expect(hide).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(hide);
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password');
  });

  it('never changes the value when revealing', () => {
    // Password managers key off the value and the autocomplete hint; toggling
    // visibility must not look like an edit to them.
    render(
      <PasswordInput aria-label="Password" defaultValue="hunter2" autoComplete="current-password" />,
    );
    const field = screen.getByLabelText('Password') as HTMLInputElement;

    fireEvent.click(screen.getByRole('button', { name: 'Show the password' }));

    expect(field.value).toBe('hunter2');
    expect(field).toHaveAttribute('autoComplete', 'current-password');
  });

  it('is a plain button, so it cannot submit the form it sits in', () => {
    // A toggle that submitted the login form on click would be worse than no
    // toggle at all.
    render(<PasswordInput aria-label="Password" />);
    expect(screen.getByRole('button', { name: 'Show the password' })).toHaveAttribute(
      'type',
      'button',
    );
  });

  it('starts hidden on every render', () => {
    // Nothing is remembered between visits: a field left revealed from earlier
    // is a shoulder-surfing hole nobody asked for.
    const { unmount } = render(<PasswordInput aria-label="Password" />);
    fireEvent.click(screen.getByRole('button', { name: 'Show the password' }));
    unmount();

    render(<PasswordInput aria-label="Password" />);
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password');
  });
});
