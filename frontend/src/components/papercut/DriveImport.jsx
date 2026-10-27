import { useEffect, useState } from "react";
import { Search, Loader2, Download, ScanSearch, Check, HardDrive, ShieldCheck, FolderOpen, ArrowUpRight } from "lucide-react";
import { toast } from "sonner";
import { driveSearch, driveImport, driveScan, driveImportStatus, driveStatus, driveConnect } from "@/lib/api";

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
  const [connection, setConnection] = useState(null);
  const [connectionError, setConnectionError] = useState(false);
  const [connecting, setConnecting] = useState(false);

  const poll = () => driveImportStatus().then(setSt).catch(() => {});
  const loadConnection = () => {
    setConnectionError(false);
    return driveStatus()
      .then(setConnection)
      .catch((e) => {
        setConnectionError(true);
        toast.error(e.response?.data?.detail || "Could not check Google Drive connection");
      });
  };
  useEffect(() => { loadConnection(); }, []);
  useEffect(() => {
    const updateConnection = (event) => {
      setConnection(event.detail);
      setConnectionError(false);
    };
    window.addEventListener("drive-status-updated", updateConnection);
    return () => window.removeEventListener("drive-status-updated", updateConnection);
  }, []);
  useEffect(() => { if (connection?.connected) poll(); }, [connection?.connected]);
  useEffect(() => {
    if (!RUNNING.includes(st?.status)) return;
    const t = setInterval(() => { poll(); onImported(); }, 4000);
    return () => clearInterval(t);
  }, [st?.status, onImported]);

  const connect = async () => {
    setConnecting(true);
    try {
      const { authorization_url } = await driveConnect();
      window.location.assign(authorization_url);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Could not start Google Drive connection");
      setConnecting(false);
    }
  };

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

  if (!connection && !connectionError) {
    return (
      <section data-testid="drive-connect-screen" aria-busy="true" className="pc-card p-8 sm:p-12 pc-rise">
        <div className="mx-auto max-w-md text-center space-y-4">
          <div className="mx-auto h-14 w-14 rounded-2xl bg-[var(--pc-surface2)] border border-[var(--pc-border)] grid place-items-center">
            <Loader2 className="h-6 w-6 animate-spin text-[var(--pc-amber)]" />
          </div>
          <p className="font-mono text-sm text-[var(--pc-text2)]">Checking your Google Drive connection…</p>
        </div>
      </section>
    );
  }

  if (connectionError) return null;

  if (!connection.connected) {
    return (
      <section data-testid="drive-connect-screen" className="pc-card overflow-hidden pc-rise">
        <div className="grid lg:grid-cols-[1.25fr_0.75fr]">
          <div className="p-7 sm:p-10 lg:p-12">
            <div className="pc-overline">Google Drive integration</div>
            <div className="mt-6 flex items-center gap-4">
              <div className="h-14 w-14 rounded-2xl bg-[#0F9D58]/15 border border-[#0F9D58]/30 grid place-items-center shrink-0">
                <HardDrive className="h-7 w-7 text-[#34A853]" />
              </div>
              <div>
                <h1 className="font-heading text-3xl sm:text-4xl font-extrabold tracking-tight">Bring your papers together.</h1>
              </div>
            </div>
            <p className="mt-5 max-w-xl text-[var(--pc-text2)] leading-relaxed">
              Connect Google Drive to import past papers directly into PaperCut, or send finished sets back to your Drive.
            </p>
            <button data-testid="drive-main-connect-button" disabled={connecting} onClick={connect} className="pc-btn-primary mt-7 text-sm">
              {connecting ? <Loader2 className="h-4 w-4 animate-spin" /> : <HardDrive className="h-4 w-4" />}
              {connecting ? "Connecting…" : "Connect Google Drive"}
              {!connecting && <ArrowUpRight className="h-4 w-4" />}
            </button>
            <div className="mt-4 flex items-start gap-2 text-xs text-[var(--pc-muted)]">
              <ShieldCheck className="h-4 w-4 shrink-0 text-[var(--pc-emerald)]" />
              <p>You’ll be redirected to Google to choose an account and approve access. PaperCut never sees your Google password.</p>
            </div>
          </div>

          <div className="border-t lg:border-t-0 lg:border-l border-[var(--pc-border)] bg-[var(--pc-surface2)]/40 p-7 sm:p-10">
            <h2 className="font-heading text-lg font-bold">What you can do</h2>
            <ul className="mt-6 space-y-5">
              <li className="flex gap-3">
                <span className="h-9 w-9 rounded-lg bg-[var(--pc-amber)]/10 text-[var(--pc-amber)] grid place-items-center shrink-0"><FolderOpen className="h-4 w-4" /></span>
                <span><strong className="block text-sm">Find PDFs in Drive</strong><span className="text-xs text-[var(--pc-text2)]">Search by name or scan for new papers to import.</span></span>
              </li>
              <li className="flex gap-3">
                <span className="h-9 w-9 rounded-lg bg-[var(--pc-emerald)]/10 text-[var(--pc-emerald)] grid place-items-center shrink-0"><HardDrive className="h-4 w-4" /></span>
                <span><strong className="block text-sm">Keep your files in sync</strong><span className="text-xs text-[var(--pc-text2)]">Send completed paper sets to your chosen Drive folder.</span></span>
              </li>
            </ul>
            <div className="mt-7 border-t border-[var(--pc-border)] pt-5 text-xs text-[var(--pc-muted)]">
              You can disconnect at any time from the Drive button in the top bar.
            </div>
          </div>
        </div>
      </section>
    );
  }

  return (
    <div data-testid="drive-import-panel" className="pc-card p-6 sm:p-8 pc-rise space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--pc-emerald)]/25 bg-[var(--pc-emerald)]/5 px-4 py-3">
        <div className="flex items-center gap-2 text-sm text-[var(--pc-emerald)]">
          <Check className="h-4 w-4" />
          <span>Google Drive connected{connection.connected_by ? ` · ${connection.connected_by}` : ""}</span>
        </div>
        <span className="font-mono text-xs text-[var(--pc-muted)] truncate">{connection.root}</span>
      </div>
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
