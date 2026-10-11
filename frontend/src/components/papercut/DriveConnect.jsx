import { useEffect, useState } from "react";
import { HardDrive, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { driveStatus, driveConnect, driveDisconnect } from "@/lib/api";

const NOTICES = {
  connected: ["success", "Google Drive connected"],
  error: ["error", "Google Drive connection failed. Check the redirect URI in Google Cloud and try again"],
  scope: ["error", "Google Drive access was not granted. Please tick the Drive permission"],
};

export const DriveConnect = () => {
  const [st, setSt] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const p = new URLSearchParams(window.location.search).get("drive");
    if (p && NOTICES[p]) {
      toast[NOTICES[p][0]](NOTICES[p][1]);
      window.history.replaceState(null, "", window.location.pathname);
    }
    driveStatus().then(setSt).catch(() => {});
  }, []);
  if (!st) return null;
  const connect = async () => { setBusy(true); try { window.location.href = (await driveConnect()).authorization_url; } catch { toast.error("Could not start Google sign-in"); setBusy(false); } };
  const disconnect = async () => {
    if (!window.confirm(`Disconnect Google Drive (connected by ${st.connected_by})? Automatic uploads will stop.`)) return;
    await driveDisconnect(); setSt({ ...st, connected: false });
  };
  return st.connected ? (
    <button data-testid="drive-connected-button" onClick={disconnect} title={`Uploads go to ${st.root}. Connected by ${st.connected_by}. Click to disconnect`}
      className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-[var(--pc-emerald)]/50 text-[var(--pc-emerald)] font-mono text-xs">
      <HardDrive className="h-3.5 w-3.5" /> Drive
    </button>
  ) : (
    <button data-testid="drive-connect-button" onClick={connect} disabled={busy}
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-[var(--pc-amber)]/60 text-[var(--pc-amber)] font-mono text-xs hover:bg-[var(--pc-amber)]/10 transition-colors">
      {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <HardDrive className="h-3.5 w-3.5" />} Connect Drive
    </button>
  );
};
