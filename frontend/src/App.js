import { useCallback, useEffect, useState } from "react";
import "@/App.css";
import { Toaster, toast } from "sonner";
import { Header } from "@/components/papercut/Header";
import { UploadPanel } from "@/components/papercut/UploadPanel";
import { ProgressPanel } from "@/components/papercut/ProgressPanel";
import { ResultsPanel } from "@/components/papercut/ResultsPanel";
import { HistoryList } from "@/components/papercut/HistoryList";
import { uploadPdf, getJob, listJobs, deleteJob } from "@/lib/api";

function App() {
  const [job, setJob] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  const refreshJobs = useCallback(() => listJobs().then(setJobs).catch(() => {}), []);
  useEffect(() => { refreshJobs(); }, [refreshJobs]);

  const running = job && (job.status === "queued" || job.status === "processing");
  useEffect(() => {
    if (!running) return;
    const t = setInterval(async () => {
      const j = await getJob(job.id).catch(() => null);
      if (!j) return;
      setJob(j);
      if (j.status === "done") { toast.success(`${j.questions.length} questions extracted`); refreshJobs(); }
      if (j.status === "error") { toast.error("Processing failed"); refreshJobs(); }
    }, 2000);
    return () => clearInterval(t);
  }, [running, job?.id, refreshJobs]);

  const handleUpload = async (file) => {
    setUploading(true);
    setUploadProgress(0);
    try {
      const j = await uploadPdf(file, setUploadProgress);
      setJob(j);
      refreshJobs();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (id) => {
    await deleteJob(id);
    if (job?.id === id) setJob(null);
    refreshJobs();
  };

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
                Upload a South African past paper. AI finds where each sub-question (1.1, 1.2 …) starts and stops, crops it, stitches questions that run across pages, and hands you a labelled, ordered ZIP.
              </p>
            </div>
          )}
          {!job && <UploadPanel onUpload={handleUpload} uploading={uploading} uploadProgress={uploadProgress} />}
          {job && job.status !== "done" && <ProgressPanel job={job} />}
          {job?.status === "error" && <button data-testid="retry-new-pdf-button" onClick={() => setJob(null)} className="pc-btn-secondary">Upload another PDF</button>}
          {job?.status === "done" && <ResultsPanel job={job} onReset={() => setJob(null)} />}
        </div>
        <div className="lg:col-span-3">
          <HistoryList jobs={jobs} activeId={job?.id} onSelect={(id) => getJob(id).then(setJob)} onDelete={handleDelete} />
        </div>
      </main>
    </div>
  );
}

export default App;
