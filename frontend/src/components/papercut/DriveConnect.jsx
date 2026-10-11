import { useEffect, useState } from "react";
import { HardDrive, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { driveStatus, driveConnect, driveDisconnect, saveDriveSettings } from "@/lib/api";

const NOTICES = {
  connected: ["success", "Google Drive connected"],
  error: ["error", "Google Drive connection failed. Check the redirect URI in Google Cloud and try again"],
  scope: ["error", "Google Drive access was not granted. Please tick the Drive permission"],
};

const DriveDialog = ({ st, setSt, open, onOpenChange }) => {
  const [link, setLink] = useState(st.root_link || "");
  const [path, setPath] = useState(st.root_path || "");
  const [busy, setBusy] = useState("");
  useEffect(() => { if (open) { setLink(st.root_link || ""); setPath(st.root_path || ""); } }, [open, st.root_link, st.root_path]);
  const run = async (k, fn) => { setBusy(k); try { await fn(); } catch (e) { toast.error(e.response?.data?.detail || "Something went wrong"); } setBusy(""); };
  const save = () => run("save", async () => {
    await saveDriveSettings(link, path);
    setSt(await driveStatus());
    toast.success(r.checked ? "Folder found and saved" : "Saved. It will be checked once Drive is connected");
  });
  const connect = () => run("connect", async () => { window.location.href = (await driveConnect()).authorization_url; });
  const disconnect = () => run("disconnect", async () => { await driveDisconnect(); setSt({ ...st, connected: false }); });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="drive-settings-dialog" className="bg-[var(--pc-surface)] border-[var(--pc-border)] text-[var(--pc-text)] max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-heading">Google Drive</DialogTitle>
          <DialogDescription data-testid="drive-settings-status" className="text-[var(--pc-text2)]">
            {st.connected ? `Connected by ${st.connected_by}. Finished sets upload automatically.` : "Not connected. Sets will not upload until you connect."}
          </DialogDescription>
        </DialogHeader>
        <label className="text-xs font-mono text-[var(--pc-muted)]" htmlFor="drive-link-input">Main folder link (paste from Drive)</label>
        <input id="drive-link-input" data-testid="drive-link-input" value={link} onChange={(e) => setLink(e.target.value)} placeholder="https://drive.google.com/drive/folders/..."
          className="w-full rounded-md bg-[var(--pc-surface2)] border border-[var(--pc-border)] px-3 py-2 text-sm font-mono focus:outline-none focus:border-[var(--pc-amber)]" />
        <label className="text-xs font-mono text-[var(--pc-muted)]" htmlFor="drive-root-input">Sub-folder that holds the Year folders</label>
        <input id="drive-root-input" data-testid="drive-root-input" value={path} onChange={(e) => setPath(e.target.value)} placeholder="CAPS & IEB Past Papers"
          className="w-full rounded-md bg-[var(--pc-surface2)] border border-[var(--pc-border)] px-3 py-2 text-sm font-mono focus:outline-none focus:border-[var(--pc-amber)]" />
        <p className="text-xs text-[var(--pc-muted)]">Papers go into {"{Year}/Grade N/{Subject}/{Session}/{Province}"} inside the sub-folder. Catalogues go into its Catalogues folder. Leave the link empty to start from My Drive.</p>
        <div className="flex gap-2 flex-wrap pt-2">
          <button data-testid="drive-root-save-button" disabled={!!busy || (!path.trim() && !link.trim())} onClick={save} className="pc-btn-primary text-sm">
            {busy === "save" && <Loader2 className="h-4 w-4 animate-spin" />} Save folder
          </button>
          {st.connected
            ? <button data-testid="drive-disconnect-button" disabled={!!busy} onClick={disconnect} className="pc-btn-secondary text-sm">Disconnect</button>
            : <button data-testid="drive-dialog-connect-button" disabled={!!busy} onClick={connect} className="pc-btn-secondary text-sm">
                {busy === "connect" ? <Loader2 className="h-4 w-4 animate-spin" /> : <HardDrive className="h-4 w-4" />} Connect Drive
              </button>}
        </div>
      </DialogContent>
    </Dialog>
  );
};

export const DriveConnect = () => {
  const [st, setSt] = useState(null);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const p = new URLSearchParams(window.location.search).get("drive");
    if (p && NOTICES[p]) {
      toast[NOTICES[p][0]](NOTICES[p][1]);
      window.history.replaceState(null, "", window.location.pathname);
    }
    driveStatus().then(setSt).catch(() => {});
  }, []);
  if (!st) return null;
  const tone = st.connected ? "border-[var(--pc-emerald)]/50 text-[var(--pc-emerald)]" : "border-[var(--pc-amber)]/60 text-[var(--pc-amber)]";
  return (
    <>
      <button data-testid={st.connected ? "drive-connected-button" : "drive-connect-button"} onClick={() => setOpen(true)} title={st.root}
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border font-mono text-xs hover:bg-white/5 transition-colors ${tone}`}>
        <HardDrive className="h-3.5 w-3.5" /> {st.connected ? "Drive" : "Connect Drive"}
      </button>
      <DriveDialog st={st} setSt={setSt} open={open} onOpenChange={setOpen} />
    </>
  );
};
