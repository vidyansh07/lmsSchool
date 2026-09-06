'use client';

import { useEffect, useRef } from 'react';

/**
 * Global keyboard chords for an operational screen — Cmd/Ctrl-K for the
 * command palette, `?` for a shortcut list, and whatever a page adds on top.
 *
 * The one rule that matters more than any chord syntax: a shortcut must not
 * fire while the person is typing into a field. Missing that check is the
 * single most common way a command palette becomes unusable — every "k" typed
 * into a search box would otherwise reopen the palette. `allowInInput` exists
 * for the rare exception (e.g. Escape blurring a field) and defaults to off.
 *
 * `keys` is a small chord grammar: modifiers joined with `+`, ending in the
 * key itself — `"mod+k"`, `"shift+mod+p"`, `"escape"`, `"?"`. `mod` means
 * Cmd on macOS and Ctrl everywhere else, because that is the one modifier an
 * ERP's staff actually expect to double as both. Shift is deliberately *not*
 * required to be absent for a plain-letter chord: browsers report `event.key`
 * as the already-shifted character for punctuation (`?` is `shift+/`), so
 * checking "shift held" would make `"?"` never match on its own keyboard.
 */
export interface KeyboardShortcut {
  keys: string;
  /** Shown in a shortcut list (the command palette's `?` view, or elsewhere). */
  description: string;
  handler: (event: KeyboardEvent) => void;
  /** Fire even while focus is inside an input, textarea, select or a
   *  contenteditable element. Off by default — see the module docstring. */
  allowInInput?: boolean;
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
  // `isContentEditable` is the right check, but jsdom (used by the test suite)
  // never computes it — it only reflects the raw attribute. Checking both
  // keeps this correct in a real browser and verifiable in a test.
  return target.isContentEditable || target.getAttribute('contenteditable') === 'true';
}

function chordMatches(event: KeyboardEvent, chord: string): boolean {
  const parts = chord
    .toLowerCase()
    .split('+')
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.length === 0) return false;
  const key = parts[parts.length - 1];
  const modifiers = new Set(parts.slice(0, -1));

  const wantMod = modifiers.has('mod');
  const ctrlOk = wantMod ? event.ctrlKey || event.metaKey : modifiers.has('ctrl') === event.ctrlKey;
  const metaOk = wantMod ? true : modifiers.has('meta') === event.metaKey;
  const altOk = modifiers.has('alt') === event.altKey;
  if (!ctrlOk || !metaOk || !altOk) return false;

  return event.key.toLowerCase() === key;
}

/** Register a set of global chords. Pass `enabled: false` to suspend all of them at once. */
export function useKeyboardShortcuts(shortcuts: KeyboardShortcut[], enabled = true): void {
  // A ref, not a dependency: shortcuts are typically an inline array built on
  // every render, and re-attaching the listener every keystroke would be both
  // wasteful and (briefly) drop events. Written from an effect (with no
  // dependency array, so it runs after every render) rather than during
  // render itself — a ref is an escape hatch from React's render/effect
  // model, and mutating one while rendering is exactly the kind of tearing
  // that model exists to prevent.
  const shortcutsRef = useRef(shortcuts);
  useEffect(() => {
    shortcutsRef.current = shortcuts;
  });

  useEffect(() => {
    if (!enabled) return;

    function onKeyDown(event: KeyboardEvent) {
      const editable = isEditableTarget(event.target);
      for (const shortcut of shortcutsRef.current) {
        if (editable && !shortcut.allowInInput) continue;
        if (chordMatches(event, shortcut.keys)) {
          event.preventDefault();
          shortcut.handler(event);
          return;
        }
      }
    }

    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [enabled]);
}

/** A printable label for a chord, e.g. `"mod+k"` → `"⌘K"` on macOS, `"Ctrl+K"` elsewhere. */
export function formatShortcutLabel(keys: string): string {
  const isMac =
    typeof navigator !== 'undefined' && /Mac|iPhone|iPad|iPod/.test(navigator.userAgent ?? '');

  const symbols: Record<string, string> = {
    mod: isMac ? '⌘' : 'Ctrl',
    ctrl: 'Ctrl',
    meta: isMac ? '⌘' : 'Win',
    shift: isMac ? '⇧' : 'Shift',
    alt: isMac ? '⌥' : 'Alt',
    escape: 'Esc',
    enter: '↵',
    arrowup: '↑',
    arrowdown: '↓',
    arrowleft: '←',
    arrowright: '→',
  };

  const parts = keys
    .split('+')
    .map((part) => part.trim().toLowerCase())
    .map((part) => symbols[part] ?? part.toUpperCase());

  return parts.join(isMac ? '' : '+');
}
