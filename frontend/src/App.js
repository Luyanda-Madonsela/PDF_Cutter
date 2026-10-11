import { useCallback, useEffect, useState } from "react";
import "@/App.css";
import { Toaster, toast } from "sonner";
import { Header } from "@/components/papercut/Header";
import { UploadPanel } from "@/components/papercut/UploadPanel";
import { ProgressPanel } from "@/components/papercut/ProgressPanel";
import { ResultsPanel } from "@/components/papercut/ResultsPanel";
import { QueuePanel } from "@/components/papercut/QueuePanel";
import { uploadPdf, getJob, listJobs, deleteJob, retryJob } from "@/lib/api";

const ACTIVE = ["queued", "processing"];
const UPLOAD_CONCURRENCY = 3;

function App() {
  const [job, setJob] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [counts, setCounts] = useState({});
  const [bulk, setBulk] = useState(null);

  const refreshJobs = useCallback(() => listJobs().then((d) => { setJobs(d.jobs); setCounts(d.counts); }).catch(() => {}), []);
  useEffect(() => { refreshJobs(); }, [refreshJobs]);

  const queueActive = (counts.queued || 0) + (counts.processing || 0) > 0;
  useEffect(() => {
    if (!queueActive) return;
    const t = setInterval(refreshJobs, 3000);
    return () => clearInterval(t);
  }, [queueActive, refreshJobs]);

  const jobActive = job && (ACTIVE.includes(job.status) || ACTIVE.includes(job.paired?.status));
  useEffect(() => {
    if (!jobActive) return;
    const t = setInterval(async () => {
      const j = await getJob(job.id).catch(() => null);
      if (!j) return;
      if (ACTIVE.includes(job.status) && j.status === "done") toast.success(`${j.questions.length} questions extracted`);
      setJob(j);
    }, 2500);
    return () => clearInterval(t);
  }, [jobActive, job?.id, job?.status]);

  const handleUpload = async (files) => {
    const state = { total: files.length, done: 0, failed: 0 };
    setBulk({ ...state });
    let first = null;
    const queue = [...files];
    const worker = async () => {
      while (queue.length) {
        const f = queue.shift();
        try { const j = await uploadPdf(f); first = first || j; }
        catch (e) { state.failed++; toast.error(`${f.name}: ${e.response?.data?.detail || "upload failed"}`); }
        state.done++;
        setBulk({ ...state });
      }
    };
    await Promise.all(Array.from({ length: Math.min(UPLOAD_CONCURRENCY, files.length) }, worker));
    refreshJobs();
    if (files.length === 1 && first) setJob(first);
    else toast.success(`${state.done - state.failed} PDFs queued for processing`);
    setBulk(null);
  };

  const attachMemo = async (file) => {
    try { await uploadPdf(file, null, job.id); toast.success("Memo queued — it will be paired automatically"); setJob(await getJob(job.id)); refreshJobs(); }
    catch (e) { toast.error(e.response?.data?.detail || "Upload failed"); }
  };

  const openJob = (id) => getJob(id).then(setJob).catch(() => toast.error("Could not open job"));
  const handleDelete = async (id) => { await deleteJob(id); if (job?.id === id) setJob(null); refreshJobs(); };
  const handleRetry = async (id) => { await retryJob(id); refreshJobs(); if (job?.id === id) openJob(id); };
  const onJobChange = (j) => { setJob(j); refreshJobs(); };

  return (
    <div className="min-h-screen bg-[var(--pc-bg)] text-[var(--pc-text)] font-body pc-grid-bg">
      <Toaster theme="dark" position="bottom-right" />
      <Header />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 grid grid-cols-1 lg:grid-cols-12 gap-8">
        <div className="lg:col-span-9 space-y-8 min-w-0">
          {!job && (
            <div className="pc-rise">
              <h1 className="font-heading text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight leading-[1.05]">
                Every question,<br /><span className="text-[var(--pc-amber)]">cut clean.</span>
              </h1>
              <p className="mt-4 max-w-xl text-sm sm:text-base text-[var(--pc-text2)]">
                Drop in South African past papers and memos. AI reads the cover to name everything, finds each sub-question (1.1, 1.2 …), crops and stitches it, and pairs every question with its memo answer in a labelled ZIP.
              </p>
            </div>
          )}
          {!job && <UploadPanel onUpload={handleUpload} bulk={bulk} />}
          {job && job.status !== "done" && <ProgressPanel job={job} />}
          {job && job.status !== "done" && <button data-testid="retry-new-pdf-button" onClick={() => setJob(null)} className="pc-btn-secondary">Back to upload</button>}
          {job?.status === "done" && <ResultsPanel job={job} onReset={() => setJob(null)} onJobChange={onJobChange} onAttachMemo={attachMemo} onOpenJob={openJob} />}
        </div>
        <div className="lg:col-span-3">
          <QueuePanel jobs={jobs} counts={counts} activeId={job?.id} onSelect={openJob} onDelete={handleDelete} onRetry={handleRetry} />
        </div>
      </main>
    </div>
  );
}

export default App;
