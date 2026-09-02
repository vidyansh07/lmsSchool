import { describe, expect, it } from 'vitest';

import { ApiError, fieldErrors, queryString } from '@/lib/api';

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
