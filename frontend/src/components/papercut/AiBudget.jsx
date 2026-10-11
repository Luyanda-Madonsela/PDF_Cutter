import { useEffect, useState } from "react";
import { toast } from "sonner";
import { getBudget, setBudget } from "@/lib/api";

export const AiBudget = () => {
  const [b, setB] = useState(null);
  const [val, setVal] = useState("");
  useEffect(() => { getBudget().then((r) => { setB(r); setVal(r.monthly_limit ?? ""); }).catch(() => {}); }, []);
  if (!b) return null;
  const save = async (limit) => {
    try {
      const r = await setBudget(limit);
      setB(r); setVal(r.monthly_limit ?? "");
      toast.success(limit == null ? "Spending limit removed" : `Monthly limit set to $${Number(limit).toFixed(2)}`);
    } catch (e) { toast.error(e.response?.data?.detail || "Could not save the limit"); }
  };
  const pct = b.monthly_limit ? Math.min(100, (b.spent / b.monthly_limit) * 100) : 0;
  return (
    <div data-testid="ai-budget-panel" className="rounded-md border border-[var(--pc-border)] p-3 space-y-2">
      <div className="flex items-center justify-between text-xs font-mono">
        <span className="text-[var(--pc-text2)]">Monthly spending limit ({b.month})</span>
        <span data-testid="ai-budget-spent" className={b.reached ? "text-red-400" : "text-[var(--pc-text2)]"}>
          ${b.spent.toFixed(2)}{b.monthly_limit != null ? ` / $${b.monthly_limit.toFixed(2)}` : " spent, no limit"}
        </span>
      </div>
      {b.monthly_limit != null && (
        <div className="h-1.5 rounded bg-[var(--pc-surface2)] overflow-hidden">
          <div className={`h-full ${pct >= 90 ? "bg-red-500" : "bg-[var(--pc-amber)]"}`} style={{ width: `${pct}%` }} />
        </div>
      )}
      <div className="flex items-center gap-2">
        <span className="text-sm">$</span>
        <input data-testid="ai-budget-input" type="number" min="0" step="0.5" value={val} onChange={(e) => setVal(e.target.value)} placeholder="e.g. 20"
          className="w-28 rounded-md bg-[var(--pc-surface2)] border border-[var(--pc-border)] px-2 py-1 text-sm font-mono" />
        <button data-testid="ai-budget-save" disabled={val === ""} onClick={() => save(Number(val))} className="pc-btn-primary !py-1 text-xs">Set limit</button>
        {b.monthly_limit != null && <button data-testid="ai-budget-clear" onClick={() => save(null)} className="pc-btn-secondary !py-1 text-xs">Remove</button>}
      </div>
      {b.paused_jobs > 0 && <p data-testid="ai-budget-paused" className="text-xs text-[var(--pc-amber)]">{b.paused_jobs} documents are paused until the limit is raised or the month resets.</p>}
      {b.monthly_limit != null && b.unpriced_models.length > 0 && <p className="text-xs text-red-400">No price set for: {b.unpriced_models.join(", ")}. These models are blocked while the limit is on.</p>}
      <p className="text-[11px] text-[var(--pc-muted)]">Before each page, PaperCut checks this month's spending plus the cost of the next page (with a safety margin). If that would go over the limit, it stops and nothing more is spent. Models without a price are blocked.</p>
    </div>
  );
};
