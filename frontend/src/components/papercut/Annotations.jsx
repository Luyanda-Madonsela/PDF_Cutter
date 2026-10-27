import { useEffect, useMemo, useRef, useState } from "react";
import { Brush, Check, Eraser, Type, Undo2 } from "lucide-react";
import { toast } from "sonner";
import { imageUrl, saveAnnotations } from "@/lib/api";

const COLORS = ["#e11d48", "#2563eb", "#16a34a", "#f59e0b", "#111827"];

export const Annotations = ({ doc, question, onSetChange }) => {
  const [annotations, setAnnotations] = useState(question.annotations || []);
  const [mode, setMode] = useState("draw");
  const [color, setColor] = useState(COLORS[0]);
  const [note, setNote] = useState("");
  const [selected, setSelected] = useState(null);
  const [saving, setSaving] = useState(false);
  const [drawing, setDrawing] = useState(false);
  const svg = useRef(null);

  useEffect(() => {
    setAnnotations(question.annotations || []);
    setSelected(null);
  }, [question.id, question.annotations]);

  const viewHeight = useMemo(
    () => question.width && question.height ? 1000 * question.height / question.width : 1000,
    [question.width, question.height],
  );
  const dirty = JSON.stringify(annotations) !== JSON.stringify(question.annotations || []);

  const pointAt = (event) => {
    const bounds = svg.current.getBoundingClientRect();
    return [
      Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width)),
      Math.max(0, Math.min(1, (event.clientY - bounds.top) / bounds.height)),
    ];
  };
  const begin = (event) => {
    if (mode !== "draw") {
      if (mode === "text" && note.trim()) {
        const [x, y] = pointAt(event);
        setAnnotations((current) => [...current, { type: "text", x, y, text: note.trim(), color }]);
        setSelected(annotations.length);
      }
      return;
    }
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    const [x, y] = pointAt(event);
    setAnnotations((current) => [...current, { type: "path", points: [[x, y]], color }]);
    setSelected(annotations.length);
    setDrawing(true);
  };
  const extend = (event) => {
    if (!drawing) return;
    const [x, y] = pointAt(event);
    setAnnotations((current) => current.map((item, index) => index === selected && item.type === "path"
      ? { ...item, points: [...item.points, [x, y]] } : item));
  };
  const finish = () => setDrawing(false);
  const editText = () => {
    const item = annotations[selected];
    if (item?.type !== "text") return;
    const text = window.prompt("Edit annotation", item.text);
    if (text === null) return;
    setAnnotations((current) => current.map((annotation, index) => index === selected ? { ...annotation, text } : annotation));
  };
  const save = async () => {
    setSaving(true);
    try {
      onSetChange(await saveAnnotations(doc.id, question.id, annotations));
      toast.success("Annotations saved");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Could not save annotations");
    } finally {
      setSaving(false);
    }
  };
  const image = `${imageUrl(doc.id, question.id)}?v=${question.storage_path.slice(-12)}`;

  return (
    <div data-testid={`annotations-${question.id}`} className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" aria-pressed={mode === "draw"} onClick={() => setMode("draw")} className={`pc-btn-secondary !py-1.5 text-xs ${mode === "draw" ? "!border-[var(--pc-amber)]" : ""}`}><Brush className="h-3.5 w-3.5" /> Draw</button>
        <button type="button" aria-pressed={mode === "text"} onClick={() => setMode("text")} className={`pc-btn-secondary !py-1.5 text-xs ${mode === "text" ? "!border-[var(--pc-amber)]" : ""}`}><Type className="h-3.5 w-3.5" /> Type note</button>
        {mode === "text" && <input aria-label="Annotation text" value={note} maxLength={300} onChange={(event) => setNote(event.target.value)} placeholder="Write a note, then click the image" className="min-w-48 flex-1 rounded border border-[var(--pc-border)] bg-[var(--pc-surface2)] px-2 py-1.5 text-xs" />}
        <label className="flex items-center gap-1 text-xs text-[var(--pc-text2)]">Color
          <select aria-label="Annotation color" value={color} onChange={(event) => setColor(event.target.value)} className="rounded border border-[var(--pc-border)] bg-[var(--pc-surface2)] p-1">
            {COLORS.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        <button type="button" disabled={selected === null} onClick={editText} className="pc-btn-secondary !py-1.5 text-xs disabled:opacity-40"><Type className="h-3.5 w-3.5" /> Edit selected note</button>
        <button type="button" disabled={selected === null} onClick={() => { setAnnotations((current) => current.filter((_, i) => i !== selected)); setSelected(null); }} className="pc-btn-secondary !py-1.5 text-xs disabled:opacity-40"><Eraser className="h-3.5 w-3.5" /> Delete selected</button>
        <button type="button" disabled={!annotations.length} onClick={() => { setAnnotations((current) => current.slice(0, -1)); setSelected(null); }} className="pc-btn-secondary !py-1.5 text-xs disabled:opacity-40"><Undo2 className="h-3.5 w-3.5" /> Undo</button>
        <button type="button" disabled={!dirty || saving} onClick={save} className="pc-btn-primary !py-1.5 text-xs disabled:opacity-40"><Check className="h-3.5 w-3.5" /> {saving ? "Saving…" : "Save notes"}</button>
      </div>
      <p className="text-xs text-[var(--pc-muted)]">Your notes are saved as a separate editable overlay; the original image is unchanged.</p>
      <div className="max-h-[60vh] overflow-auto rounded-md bg-white">
        <div className="relative w-full">
          <img src={image} alt={question.label} className="block h-auto w-full" draggable="false" />
          <svg ref={svg} viewBox={`0 0 1000 ${viewHeight}`} className="absolute inset-0 h-full w-full touch-none"
            onPointerDown={begin} onPointerMove={extend} onPointerUp={finish} onPointerCancel={finish}>
            {annotations.map((item, index) => (
              item.type === "path" ? (
                <polyline key={index} points={item.points.map(([x, y]) => `${x * 1000},${y * viewHeight}`).join(" ")}
                  fill="none" stroke={item.color || COLORS[0]} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round"
                  onPointerDown={(event) => { event.stopPropagation(); setSelected(index); }} />
              ) : (
                <text key={index} x={item.x * 1000} y={item.y * viewHeight} fill={item.color || COLORS[0]} fontSize={28} fontWeight="700"
                  stroke={selected === index ? "white" : "none"} strokeWidth={selected === index ? 5 : 0} paintOrder="stroke"
                  onPointerDown={(event) => { event.stopPropagation(); setSelected(index); }}>{item.text}</text>
              )
            ))}
          </svg>
        </div>
      </div>
    </div>
  );
};
