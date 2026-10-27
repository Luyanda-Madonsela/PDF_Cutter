import { useEffect, useState } from "react";
import { Cpu, Loader2, PlugZap } from "lucide-react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { getAiSettings, getOpenrouterModels, saveAiSettings, testAi } from "@/lib/api";
import { PC } from "@/constants/testIds";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { AiUsage } from "./AiUsage";

const field = "w-full rounded-md bg-[var(--pc-surface2)] border border-[var(--pc-border)] px-3 py-2 text-sm font-mono focus:outline-none focus:border-[var(--pc-amber)]";
const KEY_HELP = {
  gemini: "aistudio.google.com/apikey", openai: "platform.openai.com/api-keys", anthropic: "console.anthropic.com/settings/keys",
  openrouter: "openrouter.ai/keys", compatible: "only if your server needs one",
};

const AiForm = ({ st, onSaved }) => {
  const [provider, setProvider] = useState(st.provider);
  const [model, setModel] = useState(st.models[provider] || st.providers[provider]?.default_model || "");
  const [key, setKey] = useState("");
  const [baseUrl, setBaseUrl] = useState(st.base_url || "");
  const [busy, setBusy] = useState("");
  const [openrouterModels, setOpenrouterModels] = useState([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [modelsError, setModelsError] = useState("");
  const [modelsAttempt, setModelsAttempt] = useState(0);
  const selectedOpenrouterModel = openrouterModels.find((entry) => entry.id === model);
  const selectedModelSupportsImages = provider !== "openrouter" || selectedOpenrouterModel?.supports_image === true;
  useEffect(() => { setModel(st.models[provider] || st.providers[provider]?.default_model || ""); setKey(""); }, [provider, st.models, st.providers]);
  useEffect(() => {
    if (provider !== "openrouter") return undefined;
    let active = true;
    setLoadingModels(true);
    setModelsError("");
    getOpenrouterModels()
      .then((result) => { if (active) setOpenrouterModels(result.models); })
      .catch((error) => { if (active) setModelsError(error.response?.data?.detail || "Could not load OpenRouter models"); })
      .finally(() => { if (active) setLoadingModels(false); });
    return () => { active = false; };
  }, [provider, modelsAttempt]);
  const own = provider !== "emergent";
  const run = async (k, fn) => { setBusy(k); try { await fn(); } catch (e) { toast.error(e.response?.data?.detail || "Something went wrong"); } setBusy(""); };
  const payload = () => ({ provider, ...(own ? { model, ...(key ? { key } : {}) } : {}), ...(provider === "compatible" ? { base_url: baseUrl } : {}) });
  const save = () => run("save", async () => { onSaved(await saveAiSettings(payload())); toast.success("AI settings saved"); setKey(""); });
  const test = () => run("test", async () => {
    onSaved(await saveAiSettings(payload()));
    const r = await testAi();
    toast.success(`${r.model} replied OK${r.fallback ? " (no key yet, so the Emergent key was used)" : ""}`);
  });

  return (
    <div className="space-y-3">
      <label className="text-xs font-mono text-[var(--pc-muted)]" htmlFor="ai-provider-select">Provider</label>
      <select id="ai-provider-select" data-testid="ai-provider-select" value={provider} onChange={(e) => setProvider(e.target.value)} className={field}>
        {Object.entries(st.providers).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
      </select>
      {own && (
        <>
          <label className="text-xs font-mono text-[var(--pc-muted)]" htmlFor="ai-model-input">Model</label>
          {provider === "openrouter" ? (
            <>
              <select id="ai-model-input" data-testid="ai-model-input" value={model} onChange={(e) => setModel(e.target.value)} className={field}>
                <option value="">{loadingModels ? "Loading OpenRouter models…" : "Select an OpenRouter model"}</option>
                {model && !selectedOpenrouterModel && <option value={model}>{model} (capability unknown)</option>}
                {openrouterModels.map((entry) => (
                  <option key={entry.id} value={entry.id} disabled={!entry.supports_image}>
                    {entry.name} — {entry.id}{entry.supports_image ? "" : " (text only; unsupported)"}
                  </option>
                ))}
              </select>
              {!loadingModels && !modelsError && provider === "openrouter" && model && !selectedModelSupportsImages && (
                <p role="alert" className="text-xs text-amber-400">
                  {selectedOpenrouterModel
                    ? "This model cannot process images. PaperCut needs a vision model; text-only OpenRouter models are unavailable for document processing."
                    : "This model's image support could not be verified. Refresh the model list and select a model marked as supporting images."}
                </p>
              )}
              {modelsError && (
                <p role="alert" className="text-xs text-red-400">
                  {modelsError} <button type="button" className="underline" onClick={() => setModelsAttempt((attempt) => attempt + 1)}>Retry</button>
                </p>
              )}
            </>
          ) : (
            <input id="ai-model-input" data-testid="ai-model-input" value={model} onChange={(e) => setModel(e.target.value)} placeholder={st.providers[provider].default_model || "e.g. qwen2.5vl"} className={field} />
          )}
          <label className="text-xs font-mono text-[var(--pc-muted)]" htmlFor="ai-key-input">API key {st.keys[provider] ? `(saved ${st.keys[provider]})` : ""}: {KEY_HELP[provider]}</label>
          <input id="ai-key-input" data-testid="ai-key-input" type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)}
            placeholder={st.keys[provider] ? "Leave empty to keep the saved key" : "Paste your key"} className={field} />
        </>
      )}
      {provider === "compatible" && (
        <>
          <label className="text-xs font-mono text-[var(--pc-muted)]" htmlFor="ai-baseurl-input">Server URL (must be reachable from the internet)</label>
          <input id="ai-baseurl-input" data-testid="ai-baseurl-input" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://my-ollama.example.com/v1" className={field} />
        </>
      )}
      <p className="text-xs text-[var(--pc-muted)]">The model must be able to read images. OpenRouter is the default provider; add its API key in settings or configure OPENROUTER_API_KEY in backend/.env.</p>
      <div className="flex gap-2 flex-wrap pt-1">
        <button data-testid="ai-save-button" disabled={!!busy || !selectedModelSupportsImages} onClick={save} className="pc-btn-primary text-sm">{busy === "save" && <Loader2 className="h-4 w-4 animate-spin" />} Save</button>
        <button data-testid="ai-test-button" disabled={!!busy || !selectedModelSupportsImages} onClick={test} className="pc-btn-secondary text-sm">
          {busy === "test" ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlugZap className="h-4 w-4" />} Save & test
        </button>
      </div>
    </div>
  );
};

export const AiBadge = () => {
  const [st, setSt] = useState(null);
  const [open, setOpen] = useState(false);
  useEffect(() => { getAiSettings().then(setSt).catch(() => {}); }, []);
  if (!st) return null;
  const a = st.active;
  return (
    <>
      <button data-testid={PC.modelBadge} onClick={() => setOpen(true)} title="AI model settings"
        className="hidden md:flex items-center gap-2 px-3 py-1 rounded-full border border-[var(--pc-border)] font-mono text-xs text-[var(--pc-text2)] hover:text-[var(--pc-text)] hover:bg-white/5 transition-colors">
        <span className={`h-2 w-2 rounded-full animate-pulse ${a.fallback ? "bg-[var(--pc-amber)]" : "bg-[var(--pc-emerald)]"}`} />
        <span data-testid="ai-active-model" className="max-w-[160px] truncate">{a.model}</span>
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid="ai-settings-dialog" className="bg-[var(--pc-surface)] border-[var(--pc-border)] text-[var(--pc-text)] max-w-lg">
          <DialogHeader>
            <DialogTitle className="font-heading flex items-center gap-2"><Cpu className="h-5 w-5 text-[var(--pc-amber)]" /> AI model</DialogTitle>
            <DialogDescription data-testid="ai-settings-status" className="text-[var(--pc-text2)]">
              Now using {st.providers[a.provider].label}: {a.model}{a.fallback ? ` (no ${st.providers[st.provider].label} key yet, so the Emergent key is used)` : ""}.
            </DialogDescription>
          </DialogHeader>
          <Tabs defaultValue="model">
            <TabsList className="bg-[var(--pc-surface2)]">
              <TabsTrigger data-testid="ai-tab-model" value="model">Model</TabsTrigger>
              <TabsTrigger data-testid="ai-tab-usage" value="usage">Usage & cost</TabsTrigger>
            </TabsList>
            <TabsContent value="model"><AiForm st={st} onSaved={setSt} /></TabsContent>
            <TabsContent value="usage"><AiUsage /></TabsContent>
          </Tabs>
        </DialogContent>
      </Dialog>
    </>
  );
};
