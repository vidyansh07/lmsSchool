import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { formatShortcutLabel, useKeyboardShortcuts, type KeyboardShortcut } from '@/hooks/use-keyboard-shortcuts';

function Harness({ shortcuts, enabled = true }: { shortcuts: KeyboardShortcut[]; enabled?: boolean }) {
  useKeyboardShortcuts(shortcuts, enabled);
  return (
    <div>
      <input aria-label="Text field" />
      <textarea aria-label="Text area" />
      <div aria-label="Editable" contentEditable suppressContentEditableWarning />
    </div>
  );
}

describe('useKeyboardShortcuts', () => {
  it('fires the handler for a matching mod+key chord', async () => {
    const user = userEvent.setup();
    const handler = vi.fn();
    render(<Harness shortcuts={[{ keys: 'mod+k', description: 'Open palette', handler }]} />);

    await user.keyboard('{Control>}k{/Control}');
    expect(handler).toHaveBeenCalledOnce();
  });

  it('does not fire mod+k for the bare key', async () => {
    const user = userEvent.setup();
    const handler = vi.fn();
    render(<Harness shortcuts={[{ keys: 'mod+k', description: 'Open palette', handler }]} />);

    await user.keyboard('k');
    expect(handler).not.toHaveBeenCalled();
  });

  it('matches a plain single-character chord like "?"', async () => {
    const user = userEvent.setup();
    const handler = vi.fn();
    render(<Harness shortcuts={[{ keys: '?', description: 'Show shortcuts', handler }]} />);

    await user.keyboard('?');
    expect(handler).toHaveBeenCalledOnce();
  });

  it('matches named keys such as Escape', async () => {
    const user = userEvent.setup();
    const handler = vi.fn();
    render(<Harness shortcuts={[{ keys: 'escape', description: 'Close', handler }]} />);

    await user.keyboard('{Escape}');
    expect(handler).toHaveBeenCalledOnce();
  });

  it('does not fire while focus is inside a text input', async () => {
    const user = userEvent.setup();
    const handler = vi.fn();
    const { getByLabelText } = render(
      <Harness shortcuts={[{ keys: 'k', description: 'Should not fire', handler }]} />,
    );

    await user.click(getByLabelText('Text field'));
    await user.keyboard('k');
    expect(handler).not.toHaveBeenCalled();
  });

  it('does not fire while focus is inside a textarea', async () => {
    const user = userEvent.setup();
    const handler = vi.fn();
    const { getByLabelText } = render(
      <Harness shortcuts={[{ keys: 'k', description: 'Should not fire', handler }]} />,
    );

    await user.click(getByLabelText('Text area'));
    await user.keyboard('k');
    expect(handler).not.toHaveBeenCalled();
  });

  it('does not fire while focus is inside a contenteditable element', async () => {
    const user = userEvent.setup();
    const handler = vi.fn();
    const { getByLabelText } = render(
      <Harness shortcuts={[{ keys: 'k', description: 'Should not fire', handler }]} />,
    );

    await user.click(getByLabelText('Editable'));
    await user.keyboard('k');
    expect(handler).not.toHaveBeenCalled();
  });

  it('still fires an input-focused shortcut when allowInInput is set', async () => {
    const user = userEvent.setup();
    const handler = vi.fn();
    const { getByLabelText } = render(
      <Harness
        shortcuts={[{ keys: 'escape', description: 'Blur', handler, allowInInput: true }]}
      />,
    );

    await user.click(getByLabelText('Text field'));
    await user.keyboard('{Escape}');
    expect(handler).toHaveBeenCalledOnce();
  });

  it('does nothing when disabled', async () => {
    const user = userEvent.setup();
    const handler = vi.fn();
    render(<Harness shortcuts={[{ keys: 'mod+k', description: 'Open', handler }]} enabled={false} />);

    await user.keyboard('{Control>}k{/Control}');
    expect(handler).not.toHaveBeenCalled();
  });

  it('stops at the first matching shortcut', async () => {
    const user = userEvent.setup();
    const first = vi.fn();
    const second = vi.fn();
    render(
      <Harness
        shortcuts={[
          { keys: 'mod+k', description: 'First', handler: first },
          { keys: 'mod+k', description: 'Second', handler: second },
        ]}
      />,
    );

    await user.keyboard('{Control>}k{/Control}');
    expect(first).toHaveBeenCalledOnce();
    expect(second).not.toHaveBeenCalled();
  });
});

describe('formatShortcutLabel', () => {
  it('renders a chord as a readable label', () => {
    expect(formatShortcutLabel('mod+k')).toMatch(/K$/);
    expect(formatShortcutLabel('escape')).toBe('Esc');
    expect(formatShortcutLabel('shift+mod+p')).toMatch(/P$/);
  });
});
