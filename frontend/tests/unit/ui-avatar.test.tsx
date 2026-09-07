import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';

describe('Avatar', () => {
  it('shows the fallback before the image has loaded', () => {
    render(
      <Avatar>
        <AvatarImage src="/jane.png" alt="Jane Doe" />
        <AvatarFallback>JD</AvatarFallback>
      </Avatar>,
    );
    expect(screen.getByText('JD')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Jane Doe' })).toHaveClass('hidden');
  });

  it('shows the image and hides the fallback once it loads', () => {
    render(
      <Avatar>
        <AvatarImage src="/jane.png" alt="Jane Doe" />
        <AvatarFallback>JD</AvatarFallback>
      </Avatar>,
    );
    fireEvent.load(screen.getByRole('img', { name: 'Jane Doe' }));
    expect(screen.getByRole('img', { name: 'Jane Doe' })).not.toHaveClass('hidden');
    expect(screen.queryByText('JD')).not.toBeInTheDocument();
  });

  it('keeps the fallback visible if the image fails to load', () => {
    render(
      <Avatar>
        <AvatarImage src="/broken.png" alt="Jane Doe" />
        <AvatarFallback>JD</AvatarFallback>
      </Avatar>,
    );
    fireEvent.error(screen.getByRole('img', { name: 'Jane Doe' }));
    expect(screen.getByText('JD')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Jane Doe' })).toHaveClass('hidden');
  });

  it('renders a fallback-only avatar with no image at all', () => {
    render(
      <Avatar>
        <AvatarFallback>JD</AvatarFallback>
      </Avatar>,
    );
    expect(screen.getByText('JD')).toBeInTheDocument();
  });

  it('applies the requested size to the root', () => {
    const { container } = render(
      <Avatar size="lg" data-testid="root">
        <AvatarFallback>JD</AvatarFallback>
      </Avatar>,
    );
    expect(container.firstElementChild).toHaveClass('size-12');
  });

  it('throws a clear error when used outside <Avatar>', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<AvatarFallback>JD</AvatarFallback>)).toThrow(/must be rendered inside <Avatar>/);
    spy.mockRestore();
  });
});
