'use client';

/**
 * The administrator's activity review.
 *
 * Scorecards on top — one per staff member active in the period, busiest
 * first, each leading with the figures that role is measured by — and the
 * feed below: the audit log as sentences, newest first, with the noise
 * (sign-ins, listings, downloads, refusals) already taken out by the server.
 * Click a person to read only their feed; click a kind to read only that
 * work. Nothing here is computed on the client: the figures, the sentences
 * and the links are the server's, so the screen and an export agree.
 */

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, ArrowUpRight, IndianRupee, Users } from 'lucide-react';

import { DataTable, type DataTableColumn } from '@/components/data-table';
import { ExportMenu } from '@/components/export-menu';
import { Pagination } from '@/components/pagination';
import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input, Select } from '@/components/ui/input';
import { ApiError } from '@/lib/api';
import { getActivityFeed, getActivityScorecards } from '@/lib/activity';
import { Capability } from '@/lib/capabilities';
import { formatCurrency, formatDateTime, formatRelative } from '@/lib/format';
import { ACTIVITY_KIND_LABEL, ACTIVITY_KIND_VARIANT, ROLE_LABEL } from '@/lib/labels';
import { cn } from '@/lib/utils';
import type {
  ActivityFeedEntry,
  ActivityKind,
  ActivityScorecard,
  ActivityScorecards,
  Paginated,
  UserRole,
} from '@/types/api';

type Period = 'today' | 'week' | 'month' | 'custom';

const PERIODS: { id: Period; label: string }[] = [
  { id: 'today', label: 'Today' },
  { id: 'week', label: 'This week' },
  { id: 'month', label: 'This month' },
  { id: 'custom', label: 'Custom' },
];

const STAFF_ROLES: UserRole[] = ['manager', 'counsellor', 'trainer', 'admin'];

function isoToday(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

/** The first of the month, for a custom range that starts sensibly. */
function isoMonthStart(): string {
  return `${isoToday().slice(0, 8)}01`;
}

function Scorecard({
  card,
  selected,
  onSelect,
}: {
  card: ActivityScorecard;
  selected: boolean;
  onSelect: () => void;
}) {
  const collected = Number(card.fees_collected);
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        'w-full rounded-xl border bg-surface p-4 text-left shadow-[var(--shadow-card)] transition-colors',
        selected
          ? 'border-primary ring-2 ring-primary/20'
          : 'border-border hover:border-primary/50',
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-semibold text-foreground">{card.name}</p>
          <p className="truncate text-xs text-muted-foreground">
            {ROLE_LABEL[card.role]}
            {card.branch_name ? ` · ${card.branch_name}` : ''}
          </p>
        </div>
        <Badge variant="neutral">{card.total_actions} actions</Badge>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2">
        {card.figures.slice(0, 4).map((figure) => (
          <div key={figure.key}>
            <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">
              {figure.label}
            </dt>
            <dd className="text-lg font-semibold tabular-nums">{figure.value}</dd>
          </div>
        ))}
      </dl>
      {collected > 0 ? (
        <p className="mt-3 flex items-center gap-1.5 text-sm text-emerald">
          <IndianRupee className="size-4" aria-hidden="true" />
          {formatCurrency(card.fees_collected)} collected
        </p>
      ) : null}
      <p className="mt-2 text-xs text-muted-foreground">
        Last active {card.last_active_at ? formatRelative(card.last_active_at) : 'never'}
      </p>
    </button>
  );
}

export function ActivityReview() {
  const [period, setPeriod] = useState<Period>('today');
  const [since, setSince] = useState(isoMonthStart());
  const [until, setUntil] = useState(isoToday());
  const [role, setRole] = useState<'' | UserRole>('');
  const [kind, setKind] = useState<'' | ActivityKind>('');
  const [actor, setActor] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);

  // Request identity, not loading flags: each fetch is keyed by its inputs and
  // the result carries the key it answered. "Loading" is the key not matching
  // yet, computed during render — no state is written inside an effect body.
  const range = useMemo(
    () => (period === 'custom' ? { since, until } : null),
    [period, since, until],
  );
  const cardsKey = JSON.stringify([period, range, role]);
  const [cardsState, setCardsState] = useState<{
    key: string;
    data: ActivityScorecards | null;
    error: ApiError | null;
  }>({ key: '', data: null, error: null });
  const [cardsAttempt, setCardsAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getActivityScorecards({ period, ...(range ?? {}), ...(role ? { role } : {}) })
      .then((data) => {
        if (!cancelled) setCardsState({ key: cardsKey, data, error: null });
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setCardsState({
            key: cardsKey,
            data: null,
            error: cause instanceof ApiError ? cause : null,
          });
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cardsKey, cardsAttempt]);

  const cards = cardsState.key === cardsKey ? cardsState.data : null;
  const cardsError = cardsState.key === cardsKey ? cardsState.error : null;
  const loadCards = useCallback(() => setCardsAttempt((value) => value + 1), []);

  const bounds = cards ? { since: cards.since, until: cards.until } : (range ?? {});
  const feedKey = JSON.stringify([bounds, actor, role, kind, search.trim(), page]);
  const [feedState, setFeedState] = useState<{
    key: string;
    data: Paginated<ActivityFeedEntry> | null;
    error: ApiError | null;
  }>({ key: '', data: null, error: null });
  const [feedAttempt, setFeedAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getActivityFeed({
      ...bounds,
      ...(actor ? { actor } : {}),
      ...(role ? { role } : {}),
      ...(kind ? { kind } : {}),
      ...(search.trim() ? { search: search.trim() } : {}),
      page,
      page_size: 25,
    })
      .then((data) => {
        if (!cancelled) setFeedState({ key: feedKey, data, error: null });
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setFeedState({
            key: feedKey,
            data: null,
            error: cause instanceof ApiError ? cause : null,
          });
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [feedKey, feedAttempt]);

  // While a new page loads, the last answer stays on screen, dimmed.
  const feed = feedState.data;
  const feedError = feedState.key === feedKey ? feedState.error : null;
  const feedLoading = feedState.key !== feedKey;
  const loadFeed = useCallback(() => setFeedAttempt((value) => value + 1), []);

  const selectedCard = cards?.cards.find((card) => card.user_id === actor);

  const feedColumns: DataTableColumn<ActivityFeedEntry>[] = [
    {
      key: 'created_at',
      header: 'When',
      render: (row) => (
        <span className="whitespace-nowrap text-muted-foreground">
          <span title={formatDateTime(row.created_at)}>{formatRelative(row.created_at)}</span>
          <span className="block text-xs">{formatDateTime(row.created_at)}</span>
        </span>
      ),
    },
    {
      key: 'actor',
      header: 'Who',
      render: (row) => (
        <>
          <button
            type="button"
            className="text-left font-medium hover:text-primary"
            onClick={() => {
              if (row.actor_id) {
                setActor(row.actor_id);
                setPage(1);
              }
            }}
          >
            {row.actor_label}
          </button>
          <span className="block text-xs text-muted-foreground">
            {row.actor_role ? ROLE_LABEL[row.actor_role] : 'System'}
            {row.actor_branch ? ` · ${row.actor_branch}` : ''}
          </span>
        </>
      ),
    },
    {
      key: 'action',
      header: 'What',
      render: (row) => (
        <>
          <span className="font-medium">{row.action_label}</span>
          <span className="block text-sm text-muted-foreground">{row.summary}</span>
        </>
      ),
    },
    {
      key: 'kind',
      header: 'Kind',
      render: (row) => (
        <Badge variant={ACTIVITY_KIND_VARIANT[row.kind]}>{ACTIVITY_KIND_LABEL[row.kind]}</Badge>
      ),
    },
    {
      key: 'open',
      header: 'Open',
      align: 'right',
      render: (row) =>
        row.href ? (
          <Button asChild size="sm" variant="ghost" className="text-muted-foreground">
            <Link href={row.href} aria-label={`Open ${row.resource_type}`}>
              <ArrowUpRight className="size-4" aria-hidden="true" />
            </Link>
          </Button>
        ) : null,
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Activity review</h1>
          <p className="text-sm text-muted-foreground">
            Who did what, and when. Scorecards for the period, and the record underneath.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div
            role="group"
            aria-label="Period"
            className="flex rounded-lg border border-border p-0.5"
          >
            {PERIODS.map((option) => (
              <Button
                key={option.id}
                type="button"
                size="sm"
                variant={period === option.id ? 'primary' : 'ghost'}
                onClick={() => {
                  setPeriod(option.id);
                  setPage(1);
                }}
              >
                {option.label}
              </Button>
            ))}
          </div>
          {period === 'custom' ? (
            <>
              <Input
                type="date"
                aria-label="From"
                value={since}
                max={until}
                onChange={(event) => setSince(event.target.value)}
                className="w-40"
              />
              <Input
                type="date"
                aria-label="To"
                value={until}
                min={since}
                max={isoToday()}
                onChange={(event) => setUntil(event.target.value)}
                className="w-40"
              />
            </>
          ) : null}
          <Select
            aria-label="Role"
            value={role}
            onChange={(event) => {
              setRole(event.target.value as '' | UserRole);
              setActor('');
              setPage(1);
            }}
            className="w-44"
          >
            <option value="">Every role</option>
            {STAFF_ROLES.map((option) => (
              <option key={option} value={option}>
                {ROLE_LABEL[option]}s
              </option>
            ))}
          </Select>
        </div>
      </div>

      <section aria-labelledby="scorecards-heading" className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 id="scorecards-heading" className="flex items-center gap-2 text-lg font-semibold">
            <Users className="size-5 text-primary" aria-hidden="true" />
            People
          </h2>
          {cards ? (
            <p className="text-sm text-muted-foreground">
              {cards.since === cards.until ? cards.since : `${cards.since} to ${cards.until}`} ·{' '}
              {cards.cards.length} active
            </p>
          ) : null}
        </div>
        {cardsError ? (
          <ErrorState
            title="Could not load the scorecards"
            message={cardsError.message}
            requestId={cardsError.requestId || undefined}
            onRetry={loadCards}
          />
        ) : cards === null ? (
          <LoadingState label="Counting the period…" rows={2} />
        ) : cards.cards.length === 0 ? (
          <EmptyState
            title="Nobody was active in this period"
            description="Widen the period, or check that people are signing in."
          />
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {cards.cards.map((card) => (
              <Scorecard
                key={card.user_id}
                card={card}
                selected={actor === card.user_id}
                onSelect={() => {
                  setActor((current) => (current === card.user_id ? '' : card.user_id));
                  setPage(1);
                }}
              />
            ))}
          </div>
        )}
      </section>

      <Card className="animate-rise-in">
        <CardHeader className="gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2">
              <Activity className="size-5 text-primary" aria-hidden="true" />
              The record
              {selectedCard ? <Badge variant="blue">{selectedCard.name}</Badge> : null}
            </CardTitle>
            <CardDescription>
              Changes only, newest first. Sign-ins, listings and downloads are left out.
            </CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            <Select
              aria-label="Kind of work"
              value={kind}
              onChange={(event) => {
                setKind(event.target.value as '' | ActivityKind);
                setPage(1);
              }}
              className="w-44"
            >
              <option value="">All work</option>
              {(Object.keys(ACTIVITY_KIND_LABEL) as ActivityKind[]).map((option) => (
                <option key={option} value={option}>
                  {ACTIVITY_KIND_LABEL[option]}
                </option>
              ))}
            </Select>
            <Input
              aria-label="Search the record"
              placeholder="Name, code or id"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
              className="w-56"
            />
            {actor ? (
              <Button type="button" size="sm" variant="ghost" onClick={() => setActor('')}>
                Everyone
              </Button>
            ) : null}
            <ExportMenu
              reportKey="activity"
              filters={{
                ...bounds,
                actor: actor || undefined,
                role: role || undefined,
                kind: kind || undefined,
              }}
              count={feed?.count ?? null}
            />
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {feedError ? (
            <ErrorState
              title="Could not load the record"
              message={feedError.message}
              requestId={feedError.requestId || undefined}
              onRetry={loadFeed}
            />
          ) : feedLoading && feed === null ? (
            <LoadingState label="Reading the record…" rows={6} />
          ) : feed && feed.results.length === 0 ? (
            <EmptyState
              title="Nothing recorded"
              description="No change matches these filters in this period."
            />
          ) : feed ? (
            <>
              {/* A new page loading keeps the last answer on screen, dimmed,
                  rather than flashing a skeleton over data already read —
                  `isLoading` stays false here (the branches above already
                  handle the true first-load and error cases), so `DataTable`
                  only ever renders the real rows in this branch. */}
              <div className={feedLoading ? 'opacity-60' : undefined}>
                <DataTable
                  columns={feedColumns}
                  rows={feed.results}
                  getRowId={(row) => row.id}
                  caption="Activity record"
                  densityStorageKey="grras.activity-feed-density"
                />
              </div>
              <Pagination
                page={feed.page}
                totalPages={feed.total_pages}
                count={feed.count}
                pageSize={feed.page_size}
                onPageChange={setPage}
              />
            </>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

export default function ActivityPage() {
  return (
    <RequireAuth capability={Capability.auditView}>
      <ActivityReview />
    </RequireAuth>
  );
}
