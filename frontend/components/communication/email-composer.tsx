'use client';

/**
 * Compose Email: the block editor the reference product's third wizard step
 * puts in front of a template author — heading, text, button, divider,
 * image, spacer, two columns, raw HTML — with the variable tokens the
 * template is allowed to use, and a desktop/phone preview.
 *
 * **Blocks, not drag-and-drop.** The original drags content in from a right
 * rail. Clicking a block adds it to the end and Up/Down move it, which gets
 * to the same arrangement, works from a keyboard, and does not need a
 * pointer-only interaction nobody can use on a phone. If dragging is wanted
 * later it is an addition to this, not a rewrite of it.
 *
 * **The blocks survive a round trip, exactly.** Parsing arbitrary HTML back
 * into blocks is lossy guesswork, so the composer writes its own block list
 * into a leading HTML comment and reads that back. A body it did not write
 * opens in HTML mode instead, and says so, rather than being silently
 * rearranged into blocks that do not match.
 *
 * **Nothing here is evaluated.** The body is a string with
 * `{{ variable }}` placeholders which the *server* substitutes from an
 * explicit allowlist; the preview renders it in the same sandboxed,
 * script-less iframe as the server-rendered preview.
 */

import { ArrowDown, ArrowUp, Monitor, Smartphone, Trash2 } from 'lucide-react';
import { useId, useState } from 'react';

import { TemplateHtmlPreview } from '@/components/communication/template-preview';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input, Textarea } from '@/components/ui/input';
import { cn } from '@/lib/utils';

export type EmailBlockKind =
  | 'heading'
  | 'text'
  | 'button'
  | 'divider'
  | 'image'
  | 'spacer'
  | 'columns'
  | 'html';

export interface EmailBlock {
  kind: EmailBlockKind;
  /** Heading/text/button label/HTML source, depending on the kind. */
  text?: string;
  /** Button or image target. */
  href?: string;
  /** Image source and its alt text. */
  src?: string;
  alt?: string;
  /** The second column of a `columns` block. */
  second?: string;
}

/** What the right-hand rail offers, in the original's order. */
export const BLOCK_PALETTE: { kind: EmailBlockKind; label: string }[] = [
  { kind: 'columns', label: 'Columns' },
  { kind: 'button', label: 'Button' },
  { kind: 'divider', label: 'Divider' },
  { kind: 'heading', label: 'Heading' },
  { kind: 'text', label: 'Text' },
  { kind: 'image', label: 'Image' },
  { kind: 'spacer', label: 'Spacer' },
  { kind: 'html', label: 'HTML' },
];

const MARKER = 'grras-blocks:';

/** The button's background. A hex colour, because that is the only thing the
 *  server's `bgcolor` rule keeps. */
const BUTTON_COLOUR = '#FFF3EA';

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Paragraphs from blank-line-separated text, so a body reads as written. */
function paragraphs(value: string): string {
  return value
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => `<p>${escapeHtml(part).replace(/\n/g, '<br />')}</p>`)
    .join('\n');
}

export function blockToHtml(block: EmailBlock): string {
  switch (block.kind) {
    case 'heading':
      return `<h2>${escapeHtml(block.text ?? '')}</h2>`;
    case 'text':
      return paragraphs(block.text ?? '');
    case 'button':
      // The old "bulletproof button": a one-cell table with `bgcolor` and a
      // link inside. No inline CSS, because the server's email sanitiser
      // allows none — `style` is how content hides and how
      // `background:url(javascript:…)` arrives — so the colour rides on a
      // presentational attribute that survives the trip.
      return (
        '<table role="presentation"><tr>' +
        `<td bgcolor="${BUTTON_COLOUR}" align="center">` +
        `<a href="${escapeHtml(block.href ?? '#')}">${escapeHtml(block.text ?? 'Open')}</a>` +
        '</td></tr></table>'
      );
    case 'divider':
      return '<hr />';
    case 'image':
      return `<p><img src="${escapeHtml(block.src ?? '')}" alt="${escapeHtml(block.alt ?? '')}" /></p>`;
    case 'spacer':
      // Two breaks rather than a styled div, for the same reason.
      return '<p><br /><br /></p>';
    case 'columns':
      return (
        '<table width="100%" role="presentation"><tr>' +
        `<td valign="top" width="50%">${paragraphs(block.text ?? '')}</td>` +
        `<td valign="top" width="50%">${paragraphs(block.second ?? '')}</td>` +
        '</tr></table>'
      );
    case 'html':
      // Written by an administrator and sanitised by the server before it is
      // ever sent; passed through here as typed.
      return block.text ?? '';
  }
}

/** The body, with the block list carried in a leading comment so reopening
 *  the composer gets the same blocks back rather than a guess at them.
 *
 *  The JSON is percent-encoded, which is not decoration: a block containing
 *  `-->` would otherwise close the comment early, putting the rest of the
 *  block list into the body as markup — and a block containing `<script>`
 *  would put that string in the body too, inside a comment where it cannot
 *  run but where anybody reading the HTML would rightly be alarmed.
 *  Percent-encoding leaves no `<` and no `>` to end anything with. */
export function blocksToHtml(blocks: EmailBlock[]): string {
  const body = blocks.map(blockToHtml).filter(Boolean).join('\n');
  return `<!--${MARKER}${encodeURIComponent(JSON.stringify(blocks))}-->\n${body}`;
}

/** The blocks a body carries, or null when it was not written here. */
export function htmlToBlocks(html: string): EmailBlock[] | null {
  const match = html.match(/^<!--grras-blocks:([^>]*?)-->/);
  if (!match || !match[1]) return null;
  try {
    const parsed: unknown = JSON.parse(decodeURIComponent(match[1]));
    if (!Array.isArray(parsed)) return null;
    return parsed as EmailBlock[];
  } catch {
    return null;
  }
}

function blankBlock(kind: EmailBlockKind): EmailBlock {
  switch (kind) {
    case 'heading':
      return { kind, text: 'Your heading' };
    case 'text':
      return { kind, text: '' };
    case 'button':
      return { kind, text: 'Open', href: 'https://' };
    case 'image':
      return { kind, src: '', alt: '' };
    case 'columns':
      return { kind, text: '', second: '' };
    case 'html':
      return { kind, text: '' };
    default:
      return { kind };
  }
}

/** Which blocks take a token in their main text field. */
const TAKES_TOKEN: EmailBlockKind[] = ['heading', 'text', 'button', 'columns', 'html'];

export function EmailComposer({
  html,
  variables,
  onChange,
  disabled = false,
}: {
  html: string;
  /** The template's allowlist — the only paths the server will substitute. */
  variables: string[];
  onChange: (html: string) => void;
  disabled?: boolean;
}) {
  const uid = useId();
  const parsed = htmlToBlocks(html);
  const [blocks, setBlocks] = useState<EmailBlock[]>(parsed ?? []);
  const [focused, setFocused] = useState(0);
  const [wide, setWide] = useState(true);

  // A body written somewhere else is not rearranged into blocks that do not
  // match it; it is left as HTML and said so.
  const foreign = html.trim() !== '' && parsed === null;

  function commit(next: EmailBlock[]) {
    setBlocks(next);
    onChange(blocksToHtml(next));
  }

  function update(index: number, change: Partial<EmailBlock>) {
    commit(blocks.map((block, i) => (i === index ? { ...block, ...change } : block)));
  }

  function move(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= blocks.length) return;
    const next = blocks.slice();
    const [moved] = next.splice(index, 1);
    next.splice(target, 0, moved!);
    commit(next);
  }

  function insertToken(token: string) {
    const block = blocks[focused];
    if (!block || !TAKES_TOKEN.includes(block.kind)) return;
    update(focused, { text: `${block.text ?? ''}{{ ${token} }}` });
  }

  if (foreign) {
    return (
      <div className="space-y-3">
        <Alert variant="info">
          This body was not written in the composer, so it is shown as HTML rather than being
          rearranged into blocks that might not match it. Replacing it with blocks will replace
          the body.
        </Alert>
        <Field label="Body (HTML)" htmlFor={`${uid}-raw`}>
          <Textarea
            id={`${uid}-raw`}
            rows={12}
            disabled={disabled}
            value={html}
            onChange={(event) => onChange(event.target.value)}
          />
        </Field>
        <Button type="button" variant="outline" disabled={disabled} onClick={() => commit([])}>
          Start again with blocks
        </Button>
      </div>
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_14rem]">
      <div className="min-w-0 space-y-4">
        {blocks.length === 0 ? (
          <p className="rounded-card border border-dashed border-line px-4 py-8 text-center text-sm text-ink-muted">
            No content here. Add a block from the right.
          </p>
        ) : (
          <ol className="space-y-3">
            {blocks.map((block, index) => (
              <li
                key={index}
                className={cn(
                  'space-y-3 rounded-card border border-line p-3',
                  focused === index && 'border-action',
                )}
                onFocusCapture={() => setFocused(index)}
              >
                <div className="flex items-center justify-between gap-2">
                  <Badge>{BLOCK_PALETTE.find((item) => item.kind === block.kind)?.label}</Badge>
                  <div className="flex gap-1">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      aria-label={`Move block ${index + 1} up`}
                      disabled={disabled || index === 0}
                      onClick={() => move(index, -1)}
                    >
                      <ArrowUp className="size-4" aria-hidden="true" />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      aria-label={`Move block ${index + 1} down`}
                      disabled={disabled || index === blocks.length - 1}
                      onClick={() => move(index, 1)}
                    >
                      <ArrowDown className="size-4" aria-hidden="true" />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      aria-label={`Remove block ${index + 1}`}
                      disabled={disabled}
                      onClick={() => commit(blocks.filter((_, i) => i !== index))}
                    >
                      <Trash2 className="size-4" aria-hidden="true" />
                    </Button>
                  </div>
                </div>

                {block.kind === 'heading' || block.kind === 'button' ? (
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field
                      label={block.kind === 'button' ? 'Button label' : 'Heading'}
                      htmlFor={`${uid}-text-${index}`}
                    >
                      <Input
                        id={`${uid}-text-${index}`}
                        disabled={disabled}
                        value={block.text ?? ''}
                        onChange={(event) => update(index, { text: event.target.value })}
                      />
                    </Field>
                    {block.kind === 'button' ? (
                      <Field label="Links to" htmlFor={`${uid}-href-${index}`}>
                        <Input
                          id={`${uid}-href-${index}`}
                          disabled={disabled}
                          value={block.href ?? ''}
                          onChange={(event) => update(index, { href: event.target.value })}
                        />
                      </Field>
                    ) : null}
                  </div>
                ) : null}

                {block.kind === 'text' || block.kind === 'html' ? (
                  <Field
                    label={block.kind === 'html' ? 'HTML' : 'Text'}
                    htmlFor={`${uid}-text-${index}`}
                    hint={
                      block.kind === 'html'
                        ? 'Sanitised by the server before anything is sent.'
                        : 'A blank line starts a new paragraph.'
                    }
                  >
                    <Textarea
                      id={`${uid}-text-${index}`}
                      rows={block.kind === 'html' ? 6 : 4}
                      disabled={disabled}
                      value={block.text ?? ''}
                      onChange={(event) => update(index, { text: event.target.value })}
                    />
                  </Field>
                ) : null}

                {block.kind === 'columns' ? (
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field label="Left column" htmlFor={`${uid}-text-${index}`}>
                      <Textarea
                        id={`${uid}-text-${index}`}
                        rows={4}
                        disabled={disabled}
                        value={block.text ?? ''}
                        onChange={(event) => update(index, { text: event.target.value })}
                      />
                    </Field>
                    <Field label="Right column" htmlFor={`${uid}-second-${index}`}>
                      <Textarea
                        id={`${uid}-second-${index}`}
                        rows={4}
                        disabled={disabled}
                        value={block.second ?? ''}
                        onChange={(event) => update(index, { second: event.target.value })}
                      />
                    </Field>
                  </div>
                ) : null}

                {block.kind === 'image' ? (
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field label="Image URL" htmlFor={`${uid}-src-${index}`}>
                      <Input
                        id={`${uid}-src-${index}`}
                        disabled={disabled}
                        value={block.src ?? ''}
                        onChange={(event) => update(index, { src: event.target.value })}
                      />
                    </Field>
                    <Field
                      label="Alt text"
                      htmlFor={`${uid}-alt-${index}`}
                      hint="What the image says, for a reader who cannot see it."
                    >
                      <Input
                        id={`${uid}-alt-${index}`}
                        disabled={disabled}
                        value={block.alt ?? ''}
                        onChange={(event) => update(index, { alt: event.target.value })}
                      />
                    </Field>
                  </div>
                ) : null}
              </li>
            ))}
          </ol>
        )}

        <section className="space-y-2">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-sm font-medium">Preview</h3>
            <div className="flex gap-1">
              <Button
                type="button"
                variant={wide ? 'secondary' : 'ghost'}
                size="sm"
                aria-pressed={wide}
                aria-label="Desktop preview"
                onClick={() => setWide(true)}
              >
                <Monitor className="size-4" aria-hidden="true" />
              </Button>
              <Button
                type="button"
                variant={wide ? 'ghost' : 'secondary'}
                size="sm"
                aria-pressed={!wide}
                aria-label="Phone preview"
                onClick={() => setWide(false)}
              >
                <Smartphone className="size-4" aria-hidden="true" />
              </Button>
            </div>
          </div>
          <div className={cn('mx-auto', wide ? 'w-full' : 'w-[390px] max-w-full')}>
            <TemplateHtmlPreview
              html={blocks.map(blockToHtml).join('\n')}
              title="Email composer preview"
            />
          </div>
          <p className="text-xs text-ink-muted">
            Tokens are shown as written here. The server substitutes them from the allowlist when
            the message is actually sent.
          </p>
        </section>
      </div>

      <aside className="space-y-4">
        <div className="space-y-2">
          <h3 className="text-sm font-medium">Content</h3>
          <div className="grid grid-cols-2 gap-2">
            {BLOCK_PALETTE.map((item) => (
              <Button
                key={item.kind}
                type="button"
                variant="outline"
                size="sm"
                disabled={disabled}
                onClick={() => {
                  commit([...blocks, blankBlock(item.kind)]);
                  setFocused(blocks.length);
                }}
              >
                {item.label}
              </Button>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <h3 className="text-sm font-medium">Tokens</h3>
          {variables.length === 0 ? (
            <p className="text-xs text-ink-muted">
              None yet. Add the variables this template may use below the composer, then insert
              them here.
            </p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {variables.map((token) => (
                <Button
                  key={token}
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="font-mono text-2xs"
                  disabled={disabled || !blocks[focused] || !TAKES_TOKEN.includes(blocks[focused]!.kind)}
                  onClick={() => insertToken(token)}
                >
                  {token}
                </Button>
              ))}
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
