import { useState } from "react";
import { Gauge, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { rateDifficulty } from "@/lib/api";

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
