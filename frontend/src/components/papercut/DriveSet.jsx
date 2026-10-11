import { useState } from "react";
import { CloudUpload, ExternalLink, Loader2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { sendToDrive, getSet } from "@/lib/api";

export const DriveBadge = ({ drive, compact }) => {
  if (!drive) return null;
  if (drive.status === "done") {
    return (
      <a data-testid="drive-sent-badge" href={drive.folder_url} target="_blank" rel="noreferrer" title={drive.folder_path} onClick={(e) => e.stopPropagation()}
        className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-[var(--pc-emerald)]/15 text-[var(--pc-emerald)] font-mono text-[11px] hover:underline">
        <CloudUpload className="h-3 w-3" /> {compact ? "Drive" : "Sent to Drive"} {!compact && <ExternalLink className="h-3 w-3" />}
      </a>
    );
  }
  if (drive.status === "error") {
    return <span data-testid="drive-error-badge" title={drive.error} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-red-500/15 text-red-400 font-mono text-[11px]"><AlertTriangle className="h-3 w-3" /> Drive failed</span>;
  }
  return (
    <span data-testid="drive-uploading-badge" className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-[var(--pc-amber)]/15 text-[var(--pc-amber)] font-mono text-[11px]">
      <Loader2 className="h-3 w-3 animate-spin" /> {drive.total ? `Drive ${drive.uploaded || 0}/${drive.total}` : "Drive queued"}
    </span>
  );
};

export const DriveSetPanel = ({ set, onSetChange }) => {
  const [busy, setBusy] = useState(false);
  if (set.status !== "done") return null;
  const d = set.drive;
  const running = d && ["queued", "uploading"].includes(d.status);
  const send = async () => {
    setBusy(true);
    try { await sendToDrive(set.id); onSetChange(await getSet(set.id)); toast.success("Uploading to Google Drive"); }
    catch (e) { toast.error(e.response?.data?.detail || "Could not send to Drive"); }
    setBusy(false);
  };
  return (
    <div data-testid="drive-set-panel" className="flex items-center gap-2 flex-wrap text-xs">
      <DriveBadge drive={d} />
      {d?.status === "done" && <span className="font-mono text-[var(--pc-muted)] break-all">{d.uploaded} files{d.skipped ? ` (${d.skipped} PDFs already there)` : ""}</span>}
      {d?.status === "error" && <span data-testid="drive-error-text" className="text-red-400 break-all">{d.error}</span>}
      <button data-testid="drive-send-button" disabled={busy || running} onClick={send} className="pc-btn-secondary !py-1 text-xs disabled:opacity-40">
        <CloudUpload className="h-3.5 w-3.5" /> {d?.status === "done" ? "Send again" : "Send to Drive"}
      </button>
    </div>
  );
};
