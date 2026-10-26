/**
 * Marking what a form needs and what it can do without.
 *
 * Required already carried a red asterisk, and that alone leaves every other
 * field ambiguous: on a form of thirty questions an unmarked one reads as
 * "not needed" or as "somebody forgot the asterisk", and those two cost very
 * different amounts to get wrong. So both ends are marked, and a field
 * carrying neither is a mistake somebody can see.
 *
 * The part worth pinning is where the marker sits. Inside the label it joins
 * the field's own name — "Fee agreed Optional" — so every query for that
 * field has to know about the decoration, and the accessible name carries a
 * word that is not part of the question. Beside it, nothing changes but the
 * pixels.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { FormRow } from '@/components/classpro/form-row';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';

describe('Field', () => {
  it('marks a required field, and leaves its name alone', () => {
    render(
      <Field label="Email" htmlFor="email" required>
        <Input />
      </Field>,
    );

    expect(screen.getByLabelText('Email')).toBeRequired();
    expect(screen.queryByText('Optional')).not.toBeInTheDocument();
  });

  it('marks an optional field, and leaves its name alone', () => {
    render(
      <Field label="Fee agreed" htmlFor="fee" optional>
        <Input />
      </Field>,
    );

    // The query still finds it by the question itself, not by the question
    // plus the word hung beside it.
    expect(screen.getByLabelText('Fee agreed')).toBeInTheDocument();
    expect(screen.getByText('Optional')).toBeInTheDocument();
  });

  it('says one thing or the other, never both', () => {
    render(
      <Field label="Phone" htmlFor="phone" required optional>
        <Input />
      </Field>,
    );

    // Required wins: a field the form will refuse to submit without is not
    // optional, whatever the caller passed.
    expect(screen.getByLabelText('Phone')).toBeRequired();
    expect(screen.queryByText('Optional')).not.toBeInTheDocument();
  });
});

describe('FormRow', () => {
  it('marks optional without joining the label', () => {
    render(
      <FormRow label="Roll No." htmlFor="roll" optional>
        <Input id="roll" />
      </FormRow>,
    );

    expect(screen.getByLabelText('Roll No.')).toBeInTheDocument();
    expect(screen.getByText('Optional')).toBeInTheDocument();
  });

  it('keeps the asterisk for required and adds nothing else', () => {
    render(
      <FormRow label="Mobile" htmlFor="mobile" required>
        <Input id="mobile" />
      </FormRow>,
    );

    expect(screen.getByLabelText('Mobile')).toBeInTheDocument();
    expect(screen.queryByText('Optional')).not.toBeInTheDocument();
  });

  it('marks nothing when asked for nothing, which is how a gap stays visible', () => {
    render(
      <FormRow label="Picture">
        <Input />
      </FormRow>,
    );

    expect(screen.queryByText('Optional')).not.toBeInTheDocument();
  });
});
