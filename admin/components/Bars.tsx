import { fmtInt, fmtPct, label } from "@/lib/format";
import type { Row } from "@/lib/types";

// Ranked horizontal bars; value and share are printed, so the bar is reinforcement, not the only cue.
export default function Bars({ rows, unit, empty = "Henüz veri yok" }: { rows: Row[]; unit: string; empty?: string }) {
  if (!rows.length) return <p className="muted small">{empty}</p>;
  const max = Math.max(...rows.map((r) => r.value));
  const total = rows.reduce((s, r) => s + r.value, 0);
  return (
    <ol className="bars">
      {rows.map((r) => (
        <li key={r.name} title={`${label(r.name)}: ${fmtInt(r.value)} ${unit}`}>
          <span className="bar-name">{label(r.name)}</span>
          <span className="bar-val">{fmtInt(r.value)} <span className="muted">· {fmtPct(r.value / total)}</span></span>
          <span className="bar-track"><span className="bar-fill" style={{ width: `${(r.value / max) * 100}%` }} /></span>
        </li>
      ))}
    </ol>
  );
}

// Share of a whole across a few categories: one stacked bar with a labelled legend.
export function Split({ rows }: { rows: Row[] }) {
  if (!rows.length) return <p className="muted small">Henüz veri yok</p>;
  const total = rows.reduce((s, r) => s + r.value, 0);
  const shown = rows.slice(0, 3);
  const other = rows.slice(3).reduce((s, r) => s + r.value, 0);
  const parts = other ? [...shown, { name: "Diğer", value: other }] : shown;
  return (
    <div>
      <div className="split" role="img" aria-label={parts.map((p) => `${label(p.name)} ${fmtPct(p.value / total)}`).join(", ")}>
        {parts.map((p, i) => (
          <span key={p.name} className={`split-part s${i + 1}`} style={{ flexGrow: p.value }} title={`${label(p.name)}: ${fmtInt(p.value)}`} />
        ))}
      </div>
      <ul className="legend">
        {parts.map((p, i) => (
          <li key={p.name}><span className={`swatch s${i + 1}`} />{label(p.name)} <strong>{fmtPct(p.value / total)}</strong> <span className="muted">({fmtInt(p.value)})</span></li>
        ))}
      </ul>
    </div>
  );
}
