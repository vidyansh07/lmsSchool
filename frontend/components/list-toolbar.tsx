'use client';

import { useEffect, useId, useState, type ReactNode } from 'react';

import { Input } from '@/components/ui/input';
import { Toolbar } from '@/components/ui/toolbar';

/**
 * Search box plus filter slot for a list page.
 *
 * The search input is debounced so typing does not fire a request per keystroke.
 *
 * The input's id is generated rather than written down. It used to be the
 * literal `list-search`, so a screen with two lists rendered two elements with
 * the same id and the second label pointed at the first input — clicking it
 * focused the wrong box.
 *
 * The `gap-3` override keeps the spacing these nineteen screens already ship;
 * `Toolbar`'s own `gap-2` is the default for strips written from here on.
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
  const searchId = useId();
  const [value, setValue] = useState(search);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (value !== search) onSearchChange(value);
    }, 300);
    return () => clearTimeout(timer);
  }, [value, search, onSearchChange]);

  return (
    <Toolbar className="gap-3">
      <div className="min-w-[16rem] flex-1">
        <label htmlFor={searchId} className="mb-1.5 block text-sm font-medium">
          Search
        </label>
        <Input
          id={searchId}
          type="search"
          placeholder={placeholder}
          value={value}
          onChange={(event) => setValue(event.target.value)}
        />
      </div>
      {children}
    </Toolbar>
  );
}
