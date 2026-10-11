import { useEffect, useState } from "react";
import { Gauge, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { rateDifficulty, rateAll, rateAllStatus } from "@/lib/api";

export const RateDifficultyButton = ({ set, onSetChange }) => {
  const [busy, setBusy] = useState(false);
  const r = set.rating;
  const running = r?.status === "running";
  if (!set.qp_id) return null;
  const go = async () => {
    setBusy(true);
    try { onSetChange(await rateDifficulty(set.id)); toast.success("Rating question difficulty"); }
    catch (e) { toast.error(e.response?.data?.detail || "Could not rate difficulty"); }
    setBusy(false);
  };
  return (
    <span className="inline-flex items-center gap-2">
      <button data-testid="rate-difficulty-button" disabled={busy || running} onClick={go} className="pc-btn-secondary !py-1 text-xs disabled:opacity-60">
        {busy || running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Gauge className="h-3.5 w-3.5" />}
        {running ? `Rating ${r.done}/${r.total}` : "Rate difficulty"}
      </button>
      {r?.status === "error" && <span data-testid="rate-difficulty-error" className="text-[11px] font-mono text-red-400 max-w-xs truncate" title={r.error}>{r.error}</span>}
    </span>
  );
};

export const RateAllButton = () => {
  const [st, setSt] = useState(null);
  const running = st?.status === "running";
  useEffect(() => { rateAllStatus().then(setSt).catch(() => {}); }, []);
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => rateAllStatus().then(setSt).catch(() => {}), 4000);
    return () => clearInterval(t);
  }, [running]);
  const go = async () => {
    if (!window.confirm("Re-rate the difficulty of every finished set? This replaces all current ratings, including ones you changed by hand.")) return;
    try { setSt(await rateAll()); toast.success("Re-rating difficulty for all sets"); }
    catch (e) { toast.error(e.response?.data?.detail || "Could not start rating"); }
  };
  return (
    <>
      <button data-testid="rate-all-button" disabled={running} onClick={go}
        className="w-full mb-3 inline-flex items-center justify-center gap-2 px-3 py-1.5 rounded-md border border-[var(--pc-border)] text-xs font-mono text-[var(--pc-text2)] hover:text-[var(--pc-text)] hover:bg-[var(--pc-surface2)] transition-colors disabled:opacity-60">
        {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Gauge className="h-3.5 w-3.5" />}
        {running ? `Rating sets ${st.done}/${st.total}` : "Re-rate all difficulty"}
      </button>
      {st?.status === "error" && <p data-testid="rate-all-error" className="-mt-2 mb-3 text-[11px] font-mono text-red-400">{st.error}</p>}
    </>
  );
};
