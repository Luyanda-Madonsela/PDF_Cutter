import { useRef, useState } from "react";
import { X } from "lucide-react";
import { pageUrl } from "@/lib/api";

export const boxKey = (b) => b.join(",");
const clamp = (v) => Math.max(0, Math.min(1000, Math.round(v)));
const pos = ([, y0, x0, y1, x1], pad = 0) => ({ top: `${y0 / 10 - pad}%`, left: `${x0 / 10 - pad}%`, height: `${(y1 - y0) / 10 + 2 * pad}%`, width: `${(x1 - x0) / 10 + 2 * pad}%` });

export const ErasePage = ({ jobId, page, parts, proposals, selected, onToggle, manual, onAdd, onRemove }) => {
  const ref = useRef(null);
  const [drag, setDrag] = useState(null);
  const at = (e) => {
    const r = ref.current.getBoundingClientRect();
    return [clamp(((e.clientY - r.top) / r.height) * 1000), clamp(((e.clientX - r.left) / r.width) * 1000)];
  };
  const down = (e) => { if (e.target !== e.currentTarget) return; e.currentTarget.setPointerCapture(e.pointerId); const p = at(e); setDrag([p, p]); };
  const move = (e) => drag && setDrag([drag[0], at(e)]);
  const up = () => {
    if (!drag) return;
    const [[ya, xa], [yb, xb]] = drag;
    setDrag(null);
    const b = [page, Math.min(ya, yb), Math.min(xa, xb), Math.max(ya, yb), Math.max(xa, xb)];
    if (b[3] - b[1] >= 4 && b[4] - b[2] >= 4) onAdd(b);
  };
  const live = drag && [page, Math.min(drag[0][0], drag[1][0]), Math.min(drag[0][1], drag[1][1]), Math.max(drag[0][0], drag[1][0]), Math.max(drag[0][1], drag[1][1])];

  return (
    <div className="space-y-1">
      <p className="font-mono text-[11px] text-[var(--pc-text2)]">Page {page + 1}: drag on the page to mark an area to erase. Click an AI box to include or exclude it.</p>
      <div ref={ref} data-testid={`erase-canvas-${page}`} onPointerDown={down} onPointerMove={move} onPointerUp={up}
        className="relative bg-white rounded overflow-hidden select-none touch-none cursor-crosshair">
        <img src={pageUrl(jobId, page)} alt={`Page ${page + 1}`} className="w-full block pointer-events-none" draggable={false} />
        {parts.map((p, i) => <div key={i} className="absolute inset-x-0 border-y-2 border-dashed border-sky-400 pointer-events-none" style={{ top: `${p.y0 / 10}%`, height: `${(p.y1 - p.y0) / 10}%` }} />)}
        {proposals.map((b) => {
          const on = selected.has(boxKey(b));
          return <button key={boxKey(b)} data-testid={`erase-box-${boxKey(b)}`} onClick={() => onToggle(b)} title={on ? "Will be erased" : "Will be kept"}
            className={`absolute border-2 transition-colors ${on ? "border-red-500 bg-red-500/30" : "border-slate-400 border-dashed bg-transparent"}`} style={pos(b, 0.4)} />;
        })}
        {manual.map((b) => (
          <div key={boxKey(b)} data-testid={`erase-manual-${boxKey(b)}`} className="absolute border-2 border-[var(--pc-amber)] bg-[var(--pc-amber)]/35 pointer-events-none" style={pos(b)}>
            <button data-testid={`erase-manual-remove-${boxKey(b)}`} onClick={() => onRemove(b)} title="Remove this area"
              className="pointer-events-auto absolute -top-2.5 -right-2.5 h-5 w-5 grid place-items-center rounded-full bg-[#0B0F19] text-[var(--pc-amber)] border border-[var(--pc-amber)]">
              <X className="h-3 w-3" />
            </button>
          </div>
        ))}
        {live && <div className="absolute border-2 border-dashed border-[var(--pc-amber)] bg-[var(--pc-amber)]/20 pointer-events-none" style={pos(live)} />}
      </div>
    </div>
  );
};
