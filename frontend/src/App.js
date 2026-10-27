import { useCallback, useEffect, useState } from "react";
import "@/App.css";
import { Toaster, toast } from "sonner";
import { Header } from "@/components/papercut/Header";
import { UploadPanel } from "@/components/papercut/UploadPanel";
import { SingleUpload } from "@/components/papercut/SingleUpload";
import { SetView } from "@/components/papercut/SetView";
import { QueuePanel } from "@/components/papercut/QueuePanel";
import { CataloguesPanel } from "@/components/papercut/CataloguesPanel";
import { DriveImport } from "@/components/papercut/DriveImport";
import { DriveConnect } from "@/components/papercut/DriveConnect";
import { createSet, uploadDoc, listSets, getSet, deleteSet, deleteJob, retryJob, stopJob, ACTIVE_DOC } from "@/lib/api";

const UPLOAD_CONCURRENCY = 3;

function App() {
  const [mode, setMode] = useState(() => localStorage.getItem("pc-mode") || "single");
  const [set, setSet] = useState(null);
  const [sets, setSets] = useState([]);
  const [counts, setCounts] = useState({});
  const [setsLoaded, setSetsLoaded] = useState(false);
  const [setsError, setSetsError] = useState("");
  const [bulk, setBulk] = useState(null);
  const [selectedSetId, setSelectedSetId] = useState(() => localStorage.getItem("pc-selected-set"));

  const changeMode = (m) => { setMode(m); localStorage.setItem("pc-mode", m); };
  const refresh = useCallback(() => listSets()
    .then((d) => { setSets(d.sets); setCounts(d.counts); setSetsError(""); })
    .catch((error) => { setSetsError(error.response?.data?.detail || "Could not load paper sets. Check the connection and try refreshing."); })
    .finally(() => setSetsLoaded(true)), []);
  useEffect(() => { refresh(); }, [refresh]);

  useEffect(() => {
    if (!selectedSetId) return;
    let current = true;
    getSet(selectedSetId).then((value) => { if (current) setSet(value); }).catch((error) => {
      if (!current) return;
      if (error.response?.status === 404) {
        localStorage.removeItem("pc-selected-set");
        setSelectedSetId(null);
        setSet(null);
      }
    });
    return () => { current = false; };
  }, [selectedSetId]);

  const driveBusy = (s) => ["queued", "uploading"].includes(s?.drive?.status);
  const queueActive = (counts.sorting || 0) + (counts.processing || 0) > 0 || sets.some(driveBusy);
  useEffect(() => {
    if (!queueActive) return;
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, [queueActive, refresh]);

  const setActive = set && (set.documents.some((d) => ACTIVE_DOC.includes(d.status) && d.status !== "waiting") || driveBusy(set) || set.rating?.status === "running");
  useEffect(() => {
    if (!setActive) return;
    const t = setInterval(() => getSet(set.id).then(setSet).catch(() => {}), 2500);
    return () => clearInterval(t);
  }, [setActive, set?.id]);

  const submitSingle = async (files) => {
    try {
      const s = await createSet(files);
      localStorage.setItem("pc-selected-set", s.id);
      setSelectedSetId(s.id);
      setSet(s);
      refresh();
      toast.success("Paper set queued");
      return true;
    }
    catch (e) { toast.error(e.response?.data?.detail || "Upload failed"); return false; }
  };

  const uploadBulk = async (files) => {
    const state = { total: files.length, done: 0, failed: 0 };
    setBulk({ ...state });
    const queue = [...files];
    const worker = async () => {
      while (queue.length) {
        const f = queue.shift();
        try { await uploadDoc(f); } catch (e) { state.failed++; toast.error(`${f.name}: ${e.response?.data?.detail || "upload failed"}`); }
        state.done++;
        setBulk({ ...state });
      }
    };
    await Promise.all(Array.from({ length: Math.min(UPLOAD_CONCURRENCY, files.length) }, worker));
    refresh();
    toast.success(`${state.done - state.failed} PDFs queued — they'll be sorted into paper sets`);
    setBulk(null);
  };

  const openSet = (id) => {
    localStorage.setItem("pc-selected-set", id);
    setSelectedSetId(id);
    return getSet(id).then(setSet).catch(() => toast.error("Could not open set"));
  };
  const reload = () => { if (set) openSet(set.id); refresh(); };
  const docHandlers = {
    onRetry: async (id) => { await retryJob(id); reload(); },
    onStop: async (id) => {
      try { await stopJob(id); toast.success("Stopped. Press Retry when you want it to run again"); } catch (e) { toast.error(e.response?.data?.detail || "Could not stop"); }
      reload();
    },
    onDelete: async (id) => { await deleteJob(id); reload(); },
    onAdd: async (type, files) => {
      try { for (const f of files) await uploadDoc(f, { setId: set.id, docType: type }); toast.success("Added to set"); }
      catch (e) { toast.error(e.response?.data?.detail || "Upload failed"); }
      reload();
    },
  };
  const resetSet = () => { localStorage.removeItem("pc-selected-set"); setSelectedSetId(null); setSet(null); };
  const removeSet = async (id) => {
    await deleteSet(id);
    if (set?.id === id) resetSet();
    refresh();
  };
  const onSetChange = (s) => { if (s?.documents) setSet(s); refresh(); };

  return (
    <div className="min-h-screen bg-[var(--pc-bg)] text-[var(--pc-text)] font-body pc-grid-bg">
      <Toaster theme="dark" position="bottom-right" />
      <Header mode={mode} onMode={changeMode} />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 grid grid-cols-1 lg:grid-cols-12 gap-8">
        <div className="lg:col-span-9 space-y-8 min-w-0">
          {!set && (
            <h1 className="font-heading text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight leading-[1.05] pc-rise">
              Every question,<br /><span className="text-[var(--pc-amber)]">cut clean.</span>
            </h1>
          )}
          {!set && (mode === "single" ? <SingleUpload onSubmit={submitSingle} /> : <UploadPanel onUpload={uploadBulk} bulk={bulk} />)}
          {!set && mode === "single" && (
            <>
              <DriveConnect inline />
              <DriveImport onImported={refresh} />
            </>
          )}
          {set && <SetView set={set} onReset={resetSet} onSetChange={onSetChange} docHandlers={docHandlers} />}
        </div>
        <div className="lg:col-span-3 space-y-6">
          <QueuePanel sets={sets} counts={counts} activeId={set?.id} onSelect={openSet} onDelete={removeSet} onRefresh={reload}
            error={setsError} loading={!setsLoaded} />
          <CataloguesPanel refreshKey={`${counts.done || 0}-${set?.status}`} />
        </div>
      </main>
    </div>
  );
}

export default App;
