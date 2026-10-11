import { useEffect, useState } from "react";
import { FolderTree, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { skeletonOptions, buildSkeleton } from "@/lib/api";

const GROUPS = [["cambridge", "Cambridge"], ["ib", "IB Diploma"], ["nbt", "NBT"]];

export const DriveSkeleton = () => {
  const [opt, setOpt] = useState(null);
  const [picked, setPicked] = useState(new Set());
  const [from, setFrom] = useState(2015);
  const [to, setTo] = useState(2027);
  const load = () => skeletonOptions().then(setOpt).catch(() => {});
  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (opt?.status?.status !== "running") return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [opt?.status?.status]);
  if (!opt) return null;
  const years = Math.max(0, to - from + 1);
  const count = opt.qualifications.filter((q) => picked.has(q.code)).reduce((n, q) => n + q.folders_per_year * years, 0);
  const toggle = (c) => setPicked((s) => { const n = new Set(s); n.has(c) ? n.delete(c) : n.add(c); return n; });
  const build = async () => {
    try { const r = await buildSkeleton([...picked], from, to); toast.success(`Creating ${r.total} folders in Drive`); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Could not start"); }
  };
  const st = opt.status;
  return (
    <div data-testid="drive-skeleton-panel" className="border-t border-[var(--pc-border)] pt-4 space-y-3">
      <div className="text-sm font-semibold flex items-center gap-2"><FolderTree className="h-4 w-4 text-[var(--pc-amber)]" /> Build folder skeleton</div>
      <div className="max-h-40 overflow-auto space-y-2 pr-1">
        {GROUPS.map(([g, label]) => (
          <div key={g}>
            <div className="text-[11px] font-mono uppercase text-[var(--pc-muted)]">{label}</div>
            <div className="flex flex-wrap gap-1.5 mt-1">
              {opt.qualifications.filter((q) => q.curriculum === g).map((q) => (
                <button key={q.code} type="button" data-testid={`skeleton-qual-${q.code}`} onClick={() => toggle(q.code)} title={q.label}
                  className={`px-2 py-0.5 rounded text-[11px] font-mono border transition-colors ${picked.has(q.code) ? "bg-[var(--pc-amber)] text-[#0B0F19] border-[var(--pc-amber)]" : "border-[var(--pc-border)] text-[var(--pc-text2)]"}`}>
                  {q.code}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-2 text-sm flex-wrap">
        Years
        <input data-testid="skeleton-year-from" type="number" value={from} onChange={(e) => setFrom(Number(e.target.value))} className="w-20 rounded bg-[var(--pc-surface2)] border border-[var(--pc-border)] px-2 py-1 font-mono text-xs" />
        to
        <input data-testid="skeleton-year-to" type="number" value={to} onChange={(e) => setTo(Number(e.target.value))} className="w-20 rounded bg-[var(--pc-surface2)] border border-[var(--pc-border)] px-2 py-1 font-mono text-xs" />
        <button data-testid="skeleton-build-button" disabled={!picked.size || !years || st?.status === "running"} onClick={build} className="pc-btn-secondary !py-1 text-xs">
          Create {count} folders
        </button>
      </div>
      {st && (
        <p data-testid="skeleton-status" className={`text-xs font-mono flex items-center gap-2 ${st.status === "error" ? "text-red-400" : "text-[var(--pc-text2)]"}`}>
          {st.status === "running" && <Loader2 className="h-3 w-3 animate-spin" />}
          {st.status === "running" ? `Creating folders ${st.done}/${st.total}` : st.status === "done" ? `Last build finished: ${st.total} folders` : `Build failed: ${st.error}`}
        </p>
      )}
      <p className="text-[11px] text-[var(--pc-muted)]">Folders that already exist are reused, never duplicated. New papers also create their folders automatically.</p>
    </div>
  );
};
