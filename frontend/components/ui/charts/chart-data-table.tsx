/**
 * The text alternative every chart in this directory ships alongside its
 * plot, per this session's own dataviz guidance: a chart must never be the
 * only way to read a value. Visually hidden (`sr-only`, the same utility
 * `components/ui/empty.tsx` and a dozen other files in this app already use)
 * but present in the DOM, so a screen reader — or this phase's own tests —
 * finds every plotted number as ordinary text, not pixels in an SVG.
 */
export function ChartDataTable({
  caption,
  columns,
  rows,
}: {
  caption: string;
  columns: string[];
  rows: Array<{ key: string; cells: string[] }>;
}) {
  return (
    <table className="sr-only">
      <caption>{caption}</caption>
      <thead>
        <tr>
          {columns.map((column) => (
            <th key={column} scope="col">
              {column}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.key}>
            {row.cells.map((cell, index) => (
              <td key={index}>{cell}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
