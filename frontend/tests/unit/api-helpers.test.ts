import { describe, expect, it } from 'vitest';

import { ApiError, errorMessage, fieldErrors, queryString } from '@/lib/api';

describe('fieldErrors', () => {
  it('maps API field details onto form fields', () => {
    const error = new ApiError(400, 'validation_error', 'Invalid.', 'req-1', {
      email: ['Enter a valid email address.'],
      role: ['This field is not accepted.'],
    });
    expect(fieldErrors(error)).toEqual({
      email: 'Enter a valid email address.',
      role: 'This field is not accepted.',
    });
  });

  it('falls back to a form-level message when there are no field details', () => {
    const error = new ApiError(403, 'permission_denied', 'Administrator role required.', 'r');
    expect(fieldErrors(error)).toEqual({ __all__: 'Administrator role required.' });
  });

  it('never leaks a non-ApiError message to the user', () => {
    expect(fieldErrors(new Error('ECONNREFUSED 10.0.0.1'))).toEqual({
      __all__: 'Something went wrong. Please try again.',
    });
  });
});

describe('fieldErrors with DRF error shapes', () => {
  it('reports non_field_errors as the form-level message', () => {
    const error = new ApiError(400, 'validation_error', 'The submitted data is invalid.', 'r', {
      non_field_errors: ['This activity can no longer be completed.'],
    });
    expect(fieldErrors(error)).toEqual({ __all__: 'This activity can no longer be completed.' });
  });

  it('lifts a nested serializer field so the form that renders it sees it', () => {
    const error = new ApiError(400, 'validation_error', 'Invalid.', 'r', {
      email: ['An account with this email already exists.'],
      profile: { skills: ['Ensure this field has no more than 30 elements.'] },
    } as unknown as Record<string, string[]>);
    expect(fieldErrors(error)).toEqual({
      email: 'An account with this email already exists.',
      skills: 'Ensure this field has no more than 30 elements.',
      profile: 'Ensure this field has no more than 30 elements.',
    });
  });

  it('takes the first sentence from a list of row errors, never "[object Object]"', () => {
    const error = new ApiError(400, 'validation_error', 'Invalid.', 'r', {
      installments: [{}, { amount: ['Ensure this value is greater than 0.'] }],
    } as unknown as Record<string, string[]>);
    expect(fieldErrors(error)).toEqual({ installments: 'Ensure this value is greater than 0.' });
  });

  it('turns a throttle into a sentence instead of a "retry_after_seconds" field', () => {
    const error = new ApiError(429, 'rate_limited', 'Too many requests.', 'r', {
      retry_after_seconds: 57.3,
    } as unknown as Record<string, string[]>);
    expect(fieldErrors(error)).toEqual({
      __all__: 'Too many attempts. Wait 58 seconds and try again.',
    });
    expect(errorMessage(error)).toBe('Too many attempts. Wait 58 seconds and try again.');
  });
});

describe('queryString', () => {
  it('omits empty values so filters clear cleanly', () => {
    expect(queryString({ page: 2, search: '', role: 'trainer', ordering: undefined })).toBe(
      '?page=2&role=trainer',
    );
  });

  it('returns an empty string when nothing is set', () => {
    expect(queryString({ search: '', page: undefined })).toBe('');
  });
});
