import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { getAiUsage, setAiPrice } from "@/lib/api";

const fmt = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(2)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}k` : String(n));
const usd = (v) => (v == null ? "—" : `$${v < 0.01 && v > 0 ? v.toFixed(4) : v.toFixed(2)}`);

const PriceEdit = ({ m, onSaved }) => {
  const [inp, setInp] = useState(m.price?.[0] ?? "");
  const [out, setOut] = useState(m.price?.[1] ?? "");
  const save = async () => {
    try { onSaved(await setAiPrice(m.model, Number(inp), Number(out))); toast.success("Price saved"); }
    catch (e) { toast.error(e.response?.data?.detail || "Could not save price"); }
  };
  const cls = "w-14 rounded bg-[var(--pc-surface2)] border border-[var(--pc-border)] px-1 py-0.5 text-[11px] font-mono";
  return (
    <span className="inline-flex items-center gap-1">
      <input data-testid={`ai-price-in-${m.model}`} className={cls} value={inp} onChange={(e) => setInp(e.target.value)} title="USD per 1M input tokens" />
      <input data-testid={`ai-price-out-${m.model}`} className={cls} value={out} onChange={(e) => setOut(e.target.value)} title="USD per 1M output tokens" />
      <button data-testid={`ai-price-save-${m.model}`} onClick={save} disabled={inp === "" || out === ""} className="text-[11px] font-mono text-[var(--pc-amber)] hover:underline disabled:opacity-40">set</button>
    </span>
  );
};

export const AiUsage = () => {
  const [days, setDays] = useState(30);
  const [u, setU] = useState(null);
  useEffect(() => { getAiUsage(days).then(setU).catch(() => toast.error("Could not load usage")); }, [days]);
  if (!u) return <Loader2 className="h-5 w-5 animate-spin text-[var(--pc-amber)]" />;
  return (
    <div data-testid="ai-usage-panel" className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div data-testid="ai-usage-total-cost" className="font-heading text-2xl font-bold">{usd(u.total_cost)}</div>
          <div data-testid="ai-usage-total-calls" className="text-xs font-mono text-[var(--pc-muted)]">{u.total_calls} pages read</div>
        </div>
        <select data-testid="ai-usage-days" value={days} onChange={(e) => setDays(Number(e.target.value))} className="rounded-md bg-[var(--pc-surface2)] border border-[var(--pc-border)] px-2 py-1 text-sm">
          {[1, 7, 30, 90, 365].map((d) => <option key={d} value={d}>{d === 1 ? "Today" : `Last ${d} days`}</option>)}
        </select>
      </div>
      {u.models.length === 0 ? <p className="text-sm text-[var(--pc-muted)]">No AI calls in this period.</p> : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-[var(--pc-muted)] font-mono text-left">
              <tr><th className="py-1 pr-2">Model</th><th className="pr-2">Pages</th><th className="pr-2">Tokens in / out</th><th className="pr-2">Cost</th><th>$ per 1M in / out</th></tr>
            </thead>
            <tbody>
              {u.models.map((m) => (
                <tr key={`${m.provider}-${m.model}`} data-testid={`ai-usage-row-${m.model}`} className="border-t border-[var(--pc-border)]">
                  <td className="py-1.5 pr-2"><div className="font-mono">{m.model}</div><div className="text-[10px] text-[var(--pc-muted)]">{m.paid_by}</div></td>
                  <td className="pr-2 font-mono">{m.calls}</td>
                  <td className="pr-2 font-mono">{fmt(m.input_tokens)} / {fmt(m.output_tokens)}</td>
                  <td className="pr-2 font-mono">{usd(m.cost)}</td>
                  <td><PriceEdit m={m} onSaved={() => getAiUsage(days).then(setU)} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-[11px] text-[var(--pc-muted)]">Costs are estimates based on list prices per 1M tokens, so check your provider's bill for exact amounts. "—" means no price is set for that model yet. Tracking started on 11 Oct 2026.</p>
    </div>
  );
};
