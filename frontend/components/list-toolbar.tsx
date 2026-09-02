'use client';

import { useEffect, useState, type ReactNode } from 'react';

import { Input } from '@/components/ui/input';

/**
 * Search box plus filter slot for a list page.
 *
 * The search input is debounced so typing does not fire a request per keystroke.
 */
export function ListToolbar({
  search,
  onSearchChange,
  placeholder = 'Search…',
  children,
}: {
  search: string;
  onSearchChange: (value: string) => void;
  placeholder?: string;
  children?: ReactNode;
}) {
  const [value, setValue] = useState(search);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (value !== search) onSearchChange(value);
    }, 300);
    return () => clearTimeout(timer);
  }, [value, search, onSearchChange]);

  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="min-w-[16rem] flex-1">
        <label htmlFor="list-search" className="mb-1.5 block text-sm font-medium">
          Search
        </label>
        <Input
          id="list-search"
          type="search"
          placeholder={placeholder}
          value={value}
          onChange={(event) => setValue(event.target.value)}
        />
      </div>
      {children}
    </div>
  );
}
