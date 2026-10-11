import { useRef, useState } from "react";
import { X } from "lucide-react";
import { pageUrl } from "@/lib/api";

export const boxKey = (b) => b.join(",");
const clamp = (v) => Math.max(0, Math.min(1000, Math.round(v)));
const pos = ([, y0, x0, y1, x1], pad = 0) => ({ top: `${y0 / 10 - pad}%`, left: `${x0 / 10 - pad}%`, height: `${(y1 - y0) / 10 + 2 * pad}%`, width: `${(x1 - x0) / 10 + 2 * pad}%` });

const HANDLES = [["n", "top-0 left-1/2 cursor-ns-resize"], ["s", "top-full left-1/2 cursor-ns-resize"], ["w", "top-1/2 left-0 cursor-ew-resize"],
  ["e", "top-1/2 left-full cursor-ew-resize"], ["nw", "top-0 left-0 cursor-nwse-resize"], ["ne", "top-0 left-full cursor-nesw-resize"],
  ["sw", "top-full left-0 cursor-nesw-resize"], ["se", "top-full left-full cursor-nwse-resize"]];

const resize = ([p, y0, x0, y1, x1], mode, dy, dx) => {
  if (mode === "move") {
    const ddy = Math.max(-y0, Math.min(1000 - y1, dy)), ddx = Math.max(-x0, Math.min(1000 - x1, dx));
    return [p, y0 + ddy, x0 + ddx, y1 + ddy, x1 + ddx];
  }
  const b = [p, y0, x0, y1, x1];
  if (mode.includes("n")) b[1] = Math.min(clamp(y0 + dy), y1 - 4);
  if (mode.includes("s")) b[3] = Math.max(clamp(y1 + dy), y0 + 4);
  if (mode.includes("w")) b[2] = Math.min(clamp(x0 + dx), x1 - 4);
  if (mode.includes("e")) b[4] = Math.max(clamp(x1 + dx), x0 + 4);
  return b;
};

export const ErasePage = ({ jobId, page, parts, proposals, selected, onToggle, manual, onAdd, onRemove, onUpdate }) => {
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
  const edit = (i, box, mode) => (e) => {
    e.preventDefault();
    e.stopPropagation();
    const [sy, sx] = at(e);
    const move = (ev) => { const [y, x] = at(ev); onUpdate(i, resize(box, mode, y - sy, x - sx)); };
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };
  const live = drag && [page, Math.min(drag[0][0], drag[1][0]), Math.min(drag[0][1], drag[1][1]), Math.max(drag[0][0], drag[1][0]), Math.max(drag[0][1], drag[1][1])];

  return (
    <div className="space-y-1">
      <p className="font-mono text-[11px] text-[var(--pc-text2)]">Page {page + 1}: drag on the page to mark an area to erase, then drag your box or its handles to move or resize it. Click an AI box to include or exclude it.</p>
      <div ref={ref} data-testid={`erase-canvas-${page}`} onPointerDown={down} onPointerMove={move} onPointerUp={up}
        className="relative bg-white rounded overflow-hidden select-none touch-none cursor-crosshair">
        <img src={pageUrl(jobId, page)} alt={`Page ${page + 1}`} className="w-full block pointer-events-none" draggable={false} />
        {parts.map((p, i) => <div key={i} className="absolute inset-x-0 border-y-2 border-dashed border-sky-400 pointer-events-none" style={{ top: `${p.y0 / 10}%`, height: `${(p.y1 - p.y0) / 10}%` }} />)}
        {proposals.map((b) => {
          const on = selected.has(boxKey(b));
          return <button key={boxKey(b)} data-testid={`erase-box-${boxKey(b)}`} onClick={() => onToggle(b)} title={on ? "Will be erased" : "Will be kept"}
            className={`absolute border-2 transition-colors ${on ? "border-red-500 bg-red-500/30" : "border-slate-400 border-dashed bg-transparent"}`} style={pos(b, 0.4)} />;
        })}
        {manual.map(({ b, i }) => (
          <div key={i} data-testid={`erase-manual-${i}`} onPointerDown={edit(i, b, "move")} title="Drag to move, drag the corners or edges to resize"
            className="absolute border-2 border-[var(--pc-amber)] bg-[var(--pc-amber)]/35 cursor-move" style={pos(b)}>
            {HANDLES.map(([m, cls]) => (
              <span key={m} data-testid={`erase-manual-handle-${m}-${i}`} onPointerDown={edit(i, b, m)}
                className={`absolute h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-sm bg-[var(--pc-amber)] border border-[#0B0F19] ${cls}`} />
            ))}
            <button data-testid={`erase-manual-remove-${i}`} onPointerDown={(e) => e.stopPropagation()} onClick={() => onRemove(i)} title="Remove this area"
              className="absolute -top-3 -right-6 h-5 w-5 grid place-items-center rounded-full bg-[#0B0F19] text-[var(--pc-amber)] border border-[var(--pc-amber)]">
              <X className="h-3 w-3" />
            </button>
          </div>
        ))}
        {live && <div className="absolute border-2 border-dashed border-[var(--pc-amber)] bg-[var(--pc-amber)]/20 pointer-events-none" style={pos(live)} />}
      </div>
    </div>
  );
};
