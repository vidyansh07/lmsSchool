import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SupportCard } from '@/components/support-card';
import type { PublicSettings } from '@/lib/settings';

const mockUseApi = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/use-api', () => ({ useApi: mockUseApi }));

/** Whatever the institution has configured, in the shape the endpoint returns. */
function settings(overrides: Partial<PublicSettings> = {}): PublicSettings {
  return {
    institution_name: 'Sunrise Academy',
    support_email: 'help@sunrise.example.test',
    support_phone: '+91 141 000 0000',
    ...overrides,
  };
}

function loaded(data: PublicSettings | null) {
  mockUseApi.mockReturnValue({ data, error: null, isLoading: false, reload: vi.fn() });
}

beforeEach(() => {
  mockUseApi.mockReset();
});

describe('SupportCard', () => {
  it('names the institution and offers the address as a mailto', () => {
    loaded(settings());
    render(<SupportCard />);

    expect(screen.getByRole('heading', { name: 'Need help?' })).toBeInTheDocument();
    expect(screen.getByText('Contact Sunrise Academy.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'help@sunrise.example.test' })).toHaveAttribute(
      'href',
      'mailto:help@sunrise.example.test',
    );
    expect(screen.getByText(/\+91 141 000 0000/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\bNaN\b/);
    expect(document.body.textContent).not.toMatch(/undefined/);
  });

  it('renders nothing at all when neither contact detail is configured', () => {
    // The card is the whole message. An empty "Need help?" shell would tell
    // somebody there is nowhere to go, which is worse than not asking.
    loaded(settings({ support_email: '', support_phone: '' }));
    const { container } = render(<SupportCard />);

    expect(container).toBeEmptyDOMElement();
  });

  it('renders only the half that is configured when just the phone is set', () => {
    loaded(settings({ support_email: '' }));
    render(<SupportCard />);

    expect(screen.getByText(/\+91 141 000 0000/)).toBeInTheDocument();
    expect(screen.queryByText(/Email:/)).not.toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('renders only the half that is configured when just the address is set', () => {
    loaded(settings({ support_phone: '' }));
    render(<SupportCard />);

    expect(screen.getByRole('link', { name: 'help@sunrise.example.test' })).toBeInTheDocument();
    expect(screen.queryByText(/Phone:/)).not.toBeInTheDocument();
  });

  it('shows nothing while the answer is still in flight, rather than a skeleton', () => {
    // A support card is not what somebody came to this page for, so it appears
    // when it has something to say and never occupies space before then.
    mockUseApi.mockReturnValue({ data: null, error: null, isLoading: true, reload: vi.fn() });
    const { container } = render(<SupportCard />);

    expect(container).toBeEmptyDOMElement();
  });

  it('stays out of the way when the request fails', () => {
    mockUseApi.mockReturnValue({
      data: null,
      error: { message: 'The request failed.' },
      isLoading: false,
      reload: vi.fn(),
    });
    const { container } = render(<SupportCard />);

    expect(container).toBeEmptyDOMElement();
  });

  it('asks the endpoint the public settings are actually served from', () => {
    // Every other test here mocks the hook, so this is the only assertion that
    // the path is the one `apps/configuration/urls.py` mounts.
    loaded(settings());
    render(<SupportCard />);

    expect(mockUseApi).toHaveBeenCalledWith('/api/v1/settings/public/');
  });
});
