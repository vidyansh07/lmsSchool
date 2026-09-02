import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { CourseCard } from '@/components/course-card';
import type { CourseListRow } from '@/types/api';

const course: CourseListRow = {
  id: 'c1',
  code: 'GRS-C-00001',
  slug: 'linux-essentials',
  title: 'Linux Essentials',
  short_description: 'Start here.',
  category_name: 'Linux',
  category_slug: 'linux',
  difficulty: 'beginner',
  estimated_duration_minutes: 150,
  status: 'draft',
  visibility: 'public',
  thumbnail_url: null,
  module_count: 3,
  lesson_count: 12,
  published_at: null,
  created_at: '2026-01-01T00:00:00Z',
};

describe('CourseCard', () => {
  it('shows the course identity and counts', () => {
    render(<CourseCard course={course} href="/courses/linux-essentials" />);
    expect(screen.getByRole('link', { name: 'Linux Essentials' })).toHaveAttribute(
      'href',
      '/courses/linux-essentials',
    );
    expect(screen.getByText('GRS-C-00001')).toBeInTheDocument();
    expect(screen.getByText('3 modules')).toBeInTheDocument();
    expect(screen.getByText('12 lessons')).toBeInTheDocument();
    expect(screen.getByText('2h 30m')).toBeInTheDocument();
  });

  it('hides the status badge on the student catalogue', () => {
    render(<CourseCard course={course} href="/courses/linux-essentials" />);
    expect(screen.queryByText('Draft')).not.toBeInTheDocument();
  });

  it('shows the status badge in the authoring list', () => {
    render(<CourseCard course={course} href="/admin/courses/c1" showStatus />);
    expect(screen.getByText('Draft')).toBeInTheDocument();
  });
});
