/**
 * A tiny inline trend line for a KPI tile — deliberately not a charting
 * library. A sparkline has no axes, no legend and no tooltip to justify one;
 * it exists to answer "roughly, which way is this going", and a dozen lines
 * of inline SVG answers that with zero bundle cost and nothing to keep in
 * sync with a chart library's own theming.
 *
 * Renders nothing (not a broken axis, not a dash) for an empty series — an
 * empty `<svg>` is a defensible "no data yet"; a chart drawn from zero points
 * is not.
 */
export function Sparkline({
  values,
  width = 96,
  height = 28,
  label,
  className,
}: {
  values: number[];
  width?: number;
  height?: number;
  /** Accessible summary, since the line itself carries no text a screen reader can read. */
  label?: string;
  className?: string;
}) {
  const finite = values.filter((value) => Number.isFinite(value));
  if (finite.length === 0) return null;

  // A single point has no line to draw, but still deserves a mark rather than
  // a blank box — otherwise "one data point" and "no data" look identical.
  if (finite.length === 1) {
    const value = finite[0] as number;
    return (
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className={className}
        role={label ? 'img' : 'presentation'}
        aria-label={label}
      >
        <circle cx={width / 2} cy={height / 2} r={2.5} fill="currentColor" />
        <title>{label ?? `Single value: ${value}`}</title>
      </svg>
    );
  }

  const min = Math.min(...finite);
  const max = Math.max(...finite);
  const range = max - min || 1;
  const stepX = width / (finite.length - 1);

  const points = finite.map((value, index) => {
    const x = index * stepX;
    // SVG's y axis grows downward, so the highest value gets the smallest y.
    const y = height - ((value - min) / range) * height;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      role={label ? 'img' : 'presentation'}
      aria-label={label}
    >
      <title>{label ?? `Trend across ${finite.length} points`}</title>
      <polyline
        points={points.join(' ')}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
