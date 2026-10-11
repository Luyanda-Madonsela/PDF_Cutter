import { useEffect, useState } from "react";
import { Search, Loader2, Download, ScanSearch, Check } from "lucide-react";
import { toast } from "sonner";
import { driveSearch, driveImport, driveScan, driveImportStatus } from "@/lib/api";

const RUNNING = ["queued", "scanning", "importing"];

const ImportStatus = ({ st }) => {
  if (!st || st.status === "idle") return null;
  const text = {
    queued: "Starting…", scanning: `Scanning Drive… ${st.found || 0} new PDFs found`,
    importing: `Importing ${st.done || 0}/${st.total || 0} (${st.imported || 0} new, ${st.failed || 0} failed)`,
    done: `Last import: ${st.imported || 0} PDFs added, ${st.failed || 0} failed. They're being sorted into paper sets.`,
    error: `Import failed: ${st.error}`, interrupted: "Last import was interrupted. Start it again",
  }[st.status];
  return (
    <div data-testid="drive-import-status" className={`text-xs font-mono flex items-center gap-2 ${st.status === "error" ? "text-red-400" : "text-[var(--pc-text2)]"}`}>
      {RUNNING.includes(st.status) && <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--pc-amber)]" />} {text}
    </div>
  );
};

const FileRow = ({ f, checked, onToggle }) => (
  <label data-testid={`drive-file-${f.id}`} className={`flex items-center gap-3 px-3 py-2 rounded-md border border-[var(--pc-border)] text-sm ${f.imported ? "opacity-50" : "cursor-pointer hover:bg-[var(--pc-surface2)]"}`}>
    <input type="checkbox" disabled={f.imported} checked={checked} onChange={onToggle} data-testid={`drive-file-check-${f.id}`} className="accent-[var(--pc-amber)]" />
    <span className="truncate flex-1 min-w-0">{f.name}</span>
    <span className="hidden sm:block font-mono text-[11px] text-[var(--pc-muted)] truncate max-w-[30%]">{f.folder}</span>
    {f.imported && <span className="font-mono text-[11px] text-[var(--pc-emerald)] flex items-center gap-1"><Check className="h-3 w-3" />imported</span>}
  </label>
);

export const DriveImport = ({ onImported }) => {
  const [q, setQ] = useState("");
  const [res, setRes] = useState(null);
  const [picked, setPicked] = useState(new Set());
  const [busy, setBusy] = useState(false);
  const [st, setSt] = useState(null);
  const [limit, setLimit] = useState(200);

  const poll = () => driveImportStatus().then(setSt).catch(() => {});
  useEffect(() => { poll(); }, []);
  useEffect(() => {
    if (!RUNNING.includes(st?.status)) return;
    const t = setInterval(() => { poll(); onImported(); }, 4000);
    return () => clearInterval(t);
  }, [st?.status, onImported]);

  const search = async (token) => {
    setBusy(true);
    try {
      const r = await driveSearch(q, token);
      setRes((old) => (token && old ? { ...r, files: [...old.files, ...r.files] } : r));
    } catch (e) { toast.error(e.response?.data?.detail || "Drive search failed"); }
    setBusy(false);
  };
  const toggle = (id) => setPicked((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const run = async (fn, msg) => { try { await fn(); toast.success(msg); setPicked(new Set()); poll(); } catch (e) { toast.error(e.response?.data?.detail || "Could not start import"); } };

  return (
    <div data-testid="drive-import-panel" className="pc-card p-6 sm:p-8 pc-rise space-y-5">
      <div className="pc-overline">Import PDFs from Google Drive</div>
      <form onSubmit={(e) => { e.preventDefault(); search(); }} className="flex gap-2">
        <input data-testid="drive-search-input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by file name, e.g. Mathematics P1 Nov 2019"
          className="flex-1 min-w-0 rounded-md bg-[var(--pc-surface2)] border border-[var(--pc-border)] px-3 py-2 text-sm focus:outline-none focus:border-[var(--pc-amber)]" />
        <button data-testid="drive-search-button" disabled={busy} className="pc-btn-primary text-sm">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />} Search</button>
      </form>
      {res && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs font-mono text-[var(--pc-muted)]">
            <span data-testid="drive-search-count">{res.files.length} PDFs{res.next_page_token ? "+" : ""}</span>
            <button data-testid="drive-select-all" type="button" onClick={() => setPicked(new Set(res.files.filter((f) => !f.imported).map((f) => f.id)))} className="hover:text-[var(--pc-text)]">Select all new</button>
          </div>
          <div className="max-h-[45vh] overflow-auto space-y-1.5">
            {res.files.map((f) => <FileRow key={f.id} f={f} checked={picked.has(f.id)} onToggle={() => toggle(f.id)} />)}
          </div>
          {res.next_page_token && <button data-testid="drive-load-more" type="button" disabled={busy} onClick={() => search(res.next_page_token)} className="pc-btn-secondary text-xs">Load more</button>}
          <button data-testid="drive-import-selected-button" disabled={!picked.size || RUNNING.includes(st?.status)} onClick={() => run(() => driveImport([...picked]), `Importing ${picked.size} PDFs`)} className="pc-btn-primary text-sm">
            <Download className="h-4 w-4" /> Import {picked.size} selected
          </button>
        </div>
      )}
      <div className="border-t border-[var(--pc-border)] pt-5 flex items-center gap-3 flex-wrap">
        <span className="text-sm text-[var(--pc-text2)]">Or scan all of Drive for PDFs that haven't been split yet. Up to</span>
        <select data-testid="drive-scan-limit" value={limit} onChange={(e) => setLimit(Number(e.target.value))} className="rounded-md bg-[var(--pc-surface2)] border border-[var(--pc-border)] px-2 py-1 text-sm">
          {[50, 200, 500, 1000].map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
        <button data-testid="drive-scan-button" disabled={RUNNING.includes(st?.status)} onClick={() => run(() => driveScan(limit), "Scanning Drive")} className="pc-btn-secondary text-sm">
          <ScanSearch className="h-4 w-4" /> Scan & import
        </button>
      </div>
      <ImportStatus st={st} />
    </div>
  );
};
