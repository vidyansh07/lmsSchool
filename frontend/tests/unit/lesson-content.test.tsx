import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { LessonBody } from '@/components/lesson-content';
import type { LessonContent } from '@/types/api';

vi.mock('@/lib/courses', () => ({
  getVideoPlayback: vi.fn().mockResolvedValue({
    provider: 'external_url',
    playback_url: null,
    duration_seconds: null,
    status: 'ready',
  }),
}));

function lesson(overrides: Partial<LessonContent> = {}): LessonContent {
  return {
    id: 'lesson-1',
    title: 'A lesson',
    slug: 'a-lesson',
    description: '',
    content_type: 'text',
    duration_minutes: 10,
    position: 0,
    status: 'published',
    is_preview: false,
    is_required: true,
    resource_count: 0,
    text_content: '',
    external_url: '',
    video: null,
    resources: [],
    module_id: 'module-1',
    course_id: 'course-1',
    ...overrides,
  };
}

describe('LessonBody', () => {
  it('renders text content as plain text, not as markup', () => {
    render(
      <LessonBody
        lesson={lesson({ text_content: 'Line one\n<b>not bold</b>' })}
      />,
    );
    // The tag is shown literally, which is the point: author content is never
    // interpreted as HTML.
    expect(screen.getByText(/not bold/)).toBeInTheDocument();
    expect(document.querySelector('b')).toBeNull();
  });

  it('opens external links with noopener', () => {
    render(
      <LessonBody
        lesson={lesson({ content_type: 'external_link', external_url: 'https://example.test/x' })}
      />,
    );
    const link = screen.getByRole('link', { name: /open the resource/i });
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
    expect(link).toHaveAttribute('target', '_blank');
  });

  it('warns when a document lesson has no file attached', () => {
    render(<LessonBody lesson={lesson({ content_type: 'document' })} />);
    expect(screen.getByText(/no attached file/i)).toBeInTheDocument();
  });

  it('lists resources with a download link only when downloadable', () => {
    render(
      <LessonBody
        lesson={lesson({
          resources: [
            {
              id: 'r1',
              title: 'Handout',
              description: '',
              kind: 'file',
              original_filename: 'handout.pdf',
              content_type: 'application/pdf',
              size_bytes: 2048,
              external_url: '',
              position: 0,
              is_downloadable: true,
              download_url: '/api/v1/resources/r1/download/',
            },
            {
              id: 'r2',
              title: 'Locked',
              description: '',
              kind: 'file',
              original_filename: 'locked.pdf',
              content_type: 'application/pdf',
              size_bytes: 100,
              external_url: '',
              position: 1,
              is_downloadable: false,
              download_url: null,
            },
          ],
        })}
      />,
    );

    expect(screen.getByRole('link', { name: /download/i })).toHaveAttribute(
      'href',
      '/api/v1/resources/r1/download/',
    );
    expect(screen.getByText(/not downloadable/i)).toBeInTheDocument();
  });
});
