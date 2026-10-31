"use client";

import { useState } from "react";
import { fmtDay, fmtInt } from "@/lib/format";

type Point = { date: string; value: number };

const W = 640;
const H = 220;
const PAD = { top: 12, right: 12, bottom: 26, left: 40 };

function niceMax(v: number) {
  if (v <= 4) return 4;
  const mag = 10 ** Math.floor(Math.log10(v));
  return [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].map((s) => s * mag).find((s) => s >= v)!;
}

export default function LineChart({ points, label }: { points: Point[]; label: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const max = niceMax(Math.max(...points.map((p) => p.value), 0));
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (points.length < 2 ? innerW / 2 : (i / (points.length - 1)) * innerW);
  const y = (v: number) => PAD.top + innerH - (v / max) * innerH;
  const line = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join("");
  const area = `${line}L${x(points.length - 1).toFixed(1)},${y(0)}L${x(0).toFixed(1)},${y(0)}Z`;
  const ticks = [0, max / 2, max];
  const labelEvery = Math.ceil(points.length / 6);

  function onMove(e: React.PointerEvent<SVGSVGElement>) {
    const box = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * W;
    const i = Math.round(((px - PAD.left) / innerW) * (points.length - 1));
    setHover(Math.max(0, Math.min(points.length - 1, i)));
  }

  const h = hover === null ? null : points[hover];
  return (
    <figure className="chart">
      <div className="chart-plot">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
          {ticks.map((t) => (
            <g key={t}>
              <line className="grid" x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} />
              <text className="tick" x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end">{fmtInt(t)}</text>
            </g>
          ))}
          {points.map((p, i) =>
            (i % labelEvery === 0 && points.length - 1 - i >= labelEvery / 2) || i === points.length - 1 ? (
              <text key={p.date} className="tick" x={x(i)} y={H - 6} textAnchor={i === 0 ? "start" : i === points.length - 1 ? "end" : "middle"}>
                {fmtDay(p.date)}
              </text>
            ) : null,
          )}
          <path className="area" d={area} />
          <path className="line" d={line} />
          {h && hover !== null && (
            <g>
              <line className="crosshair" x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={PAD.top + innerH} />
              <circle className="dot" cx={x(hover)} cy={y(h.value)} r={5} />
            </g>
          )}
          <rect x={PAD.left} y={PAD.top} width={innerW} height={innerH} fill="transparent" />
        </svg>
        {h && hover !== null && (
          <div className="tooltip" style={{ left: `${(x(hover) / W) * 100}%`, top: `${(y(h.value) / H) * 100}%` }}>
            <span className="tooltip-date">{fmtDay(h.date)}</span>
            <strong>{fmtInt(h.value)}</strong> {label.toLowerCase()}
          </div>
        )}
      </div>
      <details className="table-view">
        <summary>Tablo olarak göster</summary>
        <table>
          <thead><tr><th>Gün</th><th className="num">{label}</th></tr></thead>
          <tbody>{points.map((p) => <tr key={p.date}><td>{fmtDay(p.date)}</td><td className="num">{fmtInt(p.value)}</td></tr>)}</tbody>
        </table>
      </details>
    </figure>
  );
}
