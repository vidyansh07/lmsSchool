'use client';

/**
 * Apply, save and remove named filter presets for a list screen.
 *
 * The persistence itself lives in `use-saved-filters.ts` (storage-key
 * convention documented there); this component is just the chip row and the
 * "save current filters" affordance a screen wires up on top of it.
 */
import { useState, type FormEvent } from 'react';
import { Bookmark, Plus, X } from 'lucide-react';

import { useSavedFilters } from '@/hooks/use-saved-filters';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

export function SavedFilters<Filters>({
  scope,
  currentFilters,
  onApply,
}: {
  /** A short, stable name for this screen, e.g. `"admin-users"`. */
  scope: string;
  /** The filters that would be saved if the person names them right now. */
  currentFilters: Filters;
  onApply: (filters: Filters) => void;
}) {
  const { savedFilters, save, remove } = useSavedFilters<Filters>(scope);
  const [isNaming, setIsNaming] = useState(false);
  const [name, setName] = useState('');

  function submitName(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    save(name, currentFilters);
    setName('');
    setIsNaming(false);
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {savedFilters.map((preset) => (
        <span
          key={preset.id}
          className="inline-flex items-center gap-1 rounded-full border border-border bg-muted py-0.5 pl-2.5 pr-1 text-xs"
        >
          <button
            type="button"
            onClick={() => onApply(preset.filters)}
            className="inline-flex items-center gap-1 font-medium hover:text-primary"
          >
            <Bookmark className="size-3" aria-hidden="true" />
            {preset.name}
          </button>
          <button
            type="button"
            onClick={() => remove(preset.id)}
            aria-label={`Remove saved filter ${preset.name}`}
            className="rounded-full p-0.5 text-muted-foreground hover:bg-border hover:text-foreground"
          >
            <X className="size-3" aria-hidden="true" />
          </button>
        </span>
      ))}

      {isNaming ? (
        <form onSubmit={submitName} className="inline-flex items-center gap-1.5">
          <Input
            autoFocus
            aria-label="Name this filter"
            placeholder="Filter name"
            value={name}
            className="h-7 w-36 text-xs"
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Escape') {
                event.preventDefault();
                setIsNaming(false);
                setName('');
              }
            }}
          />
          <Button type="submit" size="sm" variant="outline" className="h-7 px-2 text-xs">
            Save
          </Button>
        </form>
      ) : (
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-7 gap-1 px-2 text-xs text-muted-foreground"
          onClick={() => setIsNaming(true)}
        >
          <Plus className="size-3" aria-hidden="true" />
          Save current filters
        </Button>
      )}
    </div>
  );
}
