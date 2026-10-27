import { useCallback, useEffect, useState } from "react";
import { Check, HardDrive, Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { DriveSkeleton } from "./DriveSkeleton";
import { driveStatus, driveConnect, driveDisconnect, saveDriveSettings } from "@/lib/api";

const NOTICES = {
  connected: ["success", "Google Drive connected"],
  error: ["error", "Google Drive connection failed. Check the redirect URI in Google Cloud and try again"],
  scope: ["error", "Google Drive access was not granted. Please tick the Drive permission"],
};

const DriveSettingsPanel = ({ st, setSt, inline = false }) => {
  const [link, setLink] = useState(st.root_link || "");
  const [path, setPath] = useState(st.root_path || "");
  const [busy, setBusy] = useState("");

  useEffect(() => {
    setLink(st.root_link || "");
    setPath(st.root_path || "");
  }, [st.root_link, st.root_path]);

  const run = async (key, action) => {
    setBusy(key);
    try {
      await action();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Something went wrong");
    } finally {
      setBusy("");
    }
  };
  const save = () => run("save", async () => {
    const result = await saveDriveSettings(link, path);
    setSt(await driveStatus());
    toast.success(result.checked ? "Folder found and saved" : "Saved. It will be checked once Drive is connected");
  });
  const connect = () => run("connect", async () => {
    window.location.assign((await driveConnect()).authorization_url);
  });
  const disconnect = () => run("disconnect", async () => {
    await driveDisconnect();
    setSt({ ...st, connected: false, connected_by: null });
    toast.success("Google Drive disconnected");
  });

  return (
    <div className={inline ? "space-y-5" : "space-y-4"}>
      <div className="flex items-center gap-2 text-sm">
        <span className={`h-2.5 w-2.5 rounded-full ${st.connected ? "bg-[var(--pc-emerald)]" : "bg-[var(--pc-muted)]"}`} />
        <span className={st.connected ? "text-[var(--pc-emerald)]" : "text-[var(--pc-text2)]"}>
          {st.connected ? `Connected${st.connected_by ? ` as ${st.connected_by}` : ""}` : "Not connected"}
        </span>
        {st.connected && <Check className="h-4 w-4 text-[var(--pc-emerald)]" />}
      </div>

      <div className="space-y-2">
        <label className="block text-xs font-mono text-[var(--pc-muted)]" htmlFor={inline ? "drive-panel-link-input" : "drive-link-input"}>
          Main Google Drive folder link
        </label>
        <input
          id={inline ? "drive-panel-link-input" : "drive-link-input"}
          data-testid={inline ? "drive-panel-link-input" : "drive-link-input"}
          value={link}
          onChange={(event) => setLink(event.target.value)}
          placeholder="https://drive.google.com/drive/folders/..."
          className="w-full rounded-md bg-[var(--pc-surface2)] border border-[var(--pc-border)] px-3 py-2 text-sm font-mono focus:outline-none focus:border-[var(--pc-amber)]"
        />
      </div>

      <div className="space-y-2">
        <label className="block text-xs font-mono text-[var(--pc-muted)]" htmlFor={inline ? "drive-panel-root-input" : "drive-root-input"}>
          Sub-folder containing the Year folders
        </label>
        <input
          id={inline ? "drive-panel-root-input" : "drive-root-input"}
          data-testid={inline ? "drive-panel-root-input" : "drive-root-input"}
          value={path}
          onChange={(event) => setPath(event.target.value)}
          placeholder="CAPS & IEB Past Papers"
          className="w-full rounded-md bg-[var(--pc-surface2)] border border-[var(--pc-border)] px-3 py-2 text-sm font-mono focus:outline-none focus:border-[var(--pc-amber)]"
        />
      </div>

      <p className="text-xs text-[var(--pc-muted)]">
        Papers and catalogues are saved under this folder. Leave the link empty to use a folder path from My Drive.
      </p>

      <div className="flex gap-2 flex-wrap">
        <button
          data-testid={inline ? "drive-panel-save-button" : "drive-root-save-button"}
          disabled={!!busy || (!path.trim() && !link.trim())}
          onClick={save}
          className="pc-btn-primary text-sm"
        >
          {busy === "save" && <Loader2 className="h-4 w-4 animate-spin" />}
          Save folder
        </button>
        {st.connected ? (
          <button data-testid={inline ? "drive-panel-disconnect-button" : "drive-disconnect-button"} disabled={!!busy} onClick={disconnect} className="pc-btn-secondary text-sm">
            {busy === "disconnect" && <Loader2 className="h-4 w-4 animate-spin" />}
            Disconnect Google
          </button>
        ) : (
          <button data-testid={inline ? "drive-panel-connect-button" : "drive-dialog-connect-button"} disabled={!!busy} onClick={connect} className="pc-btn-secondary text-sm">
            {busy === "connect" ? <Loader2 className="h-4 w-4 animate-spin" /> : <HardDrive className="h-4 w-4" />}
            Connect Google account
          </button>
        )}
      </div>
      {st.connected && <DriveSkeleton />}
    </div>
  );
};

const DriveDialog = ({ st, setSt, open, onOpenChange }) => (
  <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent data-testid="drive-settings-dialog" className="bg-[var(--pc-surface)] border-[var(--pc-border)] text-[var(--pc-text)] max-w-lg max-h-[90vh] overflow-y-auto">
      <DialogHeader>
        <DialogTitle className="font-heading">Google Drive settings</DialogTitle>
        <DialogDescription className="text-[var(--pc-text2)]">
          Connect your Google account and choose where PaperCut saves completed sets.
        </DialogDescription>
      </DialogHeader>
      <DriveSettingsPanel st={st} setSt={setSt} />
    </DialogContent>
  </Dialog>
);

export const DriveConnect = ({ inline = false }) => {
  const [st, setSt] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [open, setOpen] = useState(false);
  const updateStatus = useCallback((status) => {
    setSt(status);
    window.dispatchEvent(new CustomEvent("drive-status-updated", { detail: status }));
  }, []);

  const refreshStatus = useCallback(() => {
    setLoadError("");
    return driveStatus()
      .then(updateStatus)
      .catch((error) => {
        const message = error.response?.data?.detail || "Could not load Google Drive settings";
        setLoadError(message);
        if (!inline) toast.error(message);
      });
  }, [inline, updateStatus]);

  useEffect(() => {
    if (!inline) {
      const notice = new URLSearchParams(window.location.search).get("drive");
      if (notice && NOTICES[notice]) {
        toast[NOTICES[notice][0]](NOTICES[notice][1]);
        window.history.replaceState(null, "", window.location.pathname);
      }
    }
    refreshStatus();
    const handleStatusUpdate = (event) => {
      setSt(event.detail);
      setLoadError("");
    };
    window.addEventListener("drive-status-updated", handleStatusUpdate);
    return () => window.removeEventListener("drive-status-updated", handleStatusUpdate);
  }, [inline, refreshStatus]);

  if (inline) {
    return (
      <section data-testid="drive-connection-panel" className="pc-card p-6 sm:p-8 pc-rise space-y-5">
        <div>
          <div className="pc-overline">Google Drive</div>
          <h2 className="mt-2 font-heading text-2xl font-bold">Account and folder</h2>
          <p className="mt-2 text-sm text-[var(--pc-text2)]">
            Choose the Google account and Drive folder used for importing and saving papers.
          </p>
        </div>
        {loadError ? (
          <div role="alert" className="flex flex-wrap items-center gap-3 text-sm text-red-400">
            <span>{loadError}</span>
            <button data-testid="drive-settings-retry" onClick={refreshStatus} className="pc-btn-secondary text-sm">
              <RefreshCw className="h-4 w-4" /> Try again
            </button>
          </div>
        ) : st ? (
          <DriveSettingsPanel st={st} setSt={updateStatus} inline />
        ) : (
          <div aria-busy="true" className="flex items-center gap-2 text-sm text-[var(--pc-text2)]">
            <Loader2 className="h-4 w-4 animate-spin text-[var(--pc-amber)]" />
            Loading Google Drive settings…
          </div>
        )}
      </section>
    );
  }

  if (!st) return null;
  const tone = st.connected ? "border-[var(--pc-emerald)]/50 text-[var(--pc-emerald)]" : "border-[var(--pc-amber)]/60 text-[var(--pc-amber)]";
  return (
    <>
      <button data-testid={st.connected ? "drive-connected-button" : "drive-connect-button"} onClick={() => setOpen(true)} title={st.root}
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border font-mono text-xs hover:bg-white/5 transition-colors ${tone}`}>
        <HardDrive className="h-3.5 w-3.5" /> {st.connected ? "Google Drive" : "Connect Drive"}
      </button>
      <DriveDialog st={st} setSt={updateStatus} open={open} onOpenChange={setOpen} />
    </>
  );
};
