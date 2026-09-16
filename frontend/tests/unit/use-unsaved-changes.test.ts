/**
 * `useUnsavedChanges` (DESIGN_DECISIONS.md, "Unsaved-changes guard"): the
 * `beforeunload` listener only warns while dirty, `guard()` runs an action
 * immediately when clean and holds it behind a Stay/Discard prompt when
 * dirty, and `confirmDiscard`/`cancelDiscard` resolve that prompt correctly.
 */
import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useUnsavedChanges } from '@/hooks/use-unsaved-changes';

function dispatchBeforeUnload(): BeforeUnloadEvent {
  const event = new Event('beforeunload', { cancelable: true }) as BeforeUnloadEvent;
  Object.defineProperty(event, 'returnValue', { value: '', writable: true });
  window.dispatchEvent(event);
  return event;
}

describe('useUnsavedChanges', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('does not warn on beforeunload when clean', () => {
    renderHook(() => useUnsavedChanges(false));
    const event = dispatchBeforeUnload();
    expect(event.defaultPrevented).toBe(false);
  });

  it('warns on beforeunload once dirty', () => {
    const { rerender } = renderHook(({ dirty }) => useUnsavedChanges(dirty), {
      initialProps: { dirty: false },
    });
    rerender({ dirty: true });

    const event = dispatchBeforeUnload();
    expect(event.defaultPrevented).toBe(true);
  });

  it('stops warning again once changes are no longer dirty', () => {
    const { rerender } = renderHook(({ dirty }) => useUnsavedChanges(dirty), {
      initialProps: { dirty: true },
    });
    rerender({ dirty: false });

    const event = dispatchBeforeUnload();
    expect(event.defaultPrevented).toBe(false);
  });

  it('guard() runs the action immediately when there is nothing to lose', () => {
    const { result } = renderHook(() => useUnsavedChanges(false));
    const action = vi.fn();

    act(() => result.current.guard(action));

    expect(action).toHaveBeenCalledTimes(1);
    expect(result.current.isPrompting).toBe(false);
  });

  it('guard() holds the action behind a prompt when dirty, and confirmDiscard runs it', () => {
    const { result } = renderHook(() => useUnsavedChanges(true));
    const action = vi.fn();

    act(() => result.current.guard(action));
    expect(action).not.toHaveBeenCalled();
    expect(result.current.isPrompting).toBe(true);

    act(() => result.current.confirmDiscard());
    expect(action).toHaveBeenCalledTimes(1);
    expect(result.current.isPrompting).toBe(false);
  });

  it('cancelDiscard closes the prompt without ever running the held action', () => {
    const { result } = renderHook(() => useUnsavedChanges(true));
    const action = vi.fn();

    act(() => result.current.guard(action));
    act(() => result.current.cancelDiscard());

    expect(action).not.toHaveBeenCalled();
    expect(result.current.isPrompting).toBe(false);
  });
});
