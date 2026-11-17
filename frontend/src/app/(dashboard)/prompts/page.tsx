"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BookOpen,
  Check,
  ChevronDown,
  Clock3,
  Code2,
  Copy,
  FilePlus2,
  History,
  Loader2,
  Pencil,
  Plus,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import { promptService } from "@/services/prompt.service";
import type { Prompt, PromptDetail, PromptPayload, PromptVersion } from "@/types/prompt";

type EditorMode = "create" | "edit";

function errorMessage(error: unknown, fallback: string) {
  const responseMessage = (
    error as { response?: { data?: { detail?: string } } }
  )?.response?.data?.detail;
  return responseMessage || (error instanceof Error ? error.message : fallback);
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export default function PromptLibraryPage() {
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [selected, setSelected] = useState<PromptDetail | null>(null);
  const [versions, setVersions] = useState<PromptVersion[]>([]);
  const [activeVersion, setActiveVersion] = useState<PromptVersion | null>(null);
  const [search, setSearch] = useState("");
  const [mode, setMode] = useState<EditorMode>("create");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [content, setContent] = useState("");
  const [editorOpen, setEditorOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [copied, setCopied] = useState(false);

  const loadPrompt = useCallback(async (promptId: string) => {
    setDetailLoading(true);
    setError("");
    try {
      const [detail, history] = await Promise.all([
        promptService.get(promptId),
        promptService.listVersions(promptId),
      ]);
      setSelected(detail);
      setVersions(history);
      setActiveVersion(detail.latest_version);
    } catch (err) {
      setError(errorMessage(err, "Unable to load this prompt."));
    } finally {
      setDetailLoading(false);
    }
  }, []);


  const loadPrompts = useCallback(async (preferredId?: string) => {
    setLoading(true);
    setError("");
    try {
      const result = await promptService.list();
      setPrompts(result.items);
      const nextId = preferredId;
      if (nextId && result.items.some((item) => item.id === nextId)) {
        await loadPrompt(nextId);
      } else if (result.items.length) {
        await loadPrompt(result.items[0].id);
      } else {
        setSelected(null);
        setVersions([]);
        setActiveVersion(null);
      }
    } catch (err) {
      setError(errorMessage(err, "Unable to load your prompt library."));
    } finally {
      setLoading(false);
    }
  }, [loadPrompt]);


  useEffect(() => {
    void loadPrompts();
  }, [loadPrompts]);

  const filteredPrompts = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return prompts;
    return prompts.filter((prompt) =>
      `${prompt.name} ${prompt.description ?? ""}`.toLowerCase().includes(query)
    );
  }, [prompts, search]);

  const openCreate = () => {
    setMode("create");
    setName("");
    setDescription("");
    setContent("");
    setEditorOpen(true);
    setError("");
  };

  const openEdit = () => {
    if (!selected || !activeVersion) return;
    setMode("edit");
    setName(selected.name);
    setDescription(selected.description ?? "");
    setContent(activeVersion.content);
    setEditorOpen(true);
    setError("");
  };

  const savePrompt = async () => {
    if (!name.trim() || !content.trim()) {
      setError("A prompt name and prompt content are required.");
      return;
    }
    const payload: PromptPayload = {
      name: name.trim(),
      description: description.trim() || null,
      content,
    };
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const result = mode === "create"
        ? await promptService.create(payload)
        : await promptService.update(selected!.id, payload);
      setEditorOpen(false);
      setNotice(mode === "create" ? "Prompt created." : `Saved as version ${result.current_version}.`);
      await loadPrompts(result.id);
    } catch (err) {
      setError(errorMessage(err, "Unable to save this prompt."));
    } finally {
      setSaving(false);
    }
  };

  const chooseVersion = async (version: PromptVersion) => {
    if (!selected) return;
    setDetailLoading(true);
    setError("");
    try {
      const result = await promptService.getVersion(selected.id, version.version_number);
      setActiveVersion(result);
      setHistoryOpen(false);
    } catch (err) {
      setError(errorMessage(err, "Unable to load the selected version."));
    } finally {
      setDetailLoading(false);
    }
  };

  const copyContent = async () => {
    if (!activeVersion) return;
    try {
      await navigator.clipboard.writeText(activeVersion.content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setError("Clipboard access is unavailable in this browser.");
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-7">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <div className="mb-2 flex items-center gap-2 text-sm text-violet-300">
            <BookOpen className="h-4 w-4" /> Prompt engineering workspace
          </div>
          <h1 className="text-3xl font-semibold tracking-tight text-white">Prompt Library</h1>
          <p className="mt-2 max-w-2xl text-sm text-zinc-400">
            Save reusable prompts, refine them safely, and inspect every version of their history.
          </p>
        </div>
        <button onClick={openCreate} className="inline-flex items-center justify-center gap-2 rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-violet-500">
          <Plus className="h-4 w-4" /> New prompt
        </button>
      </div>

      {notice && <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">{notice}</div>}
      {error && <div role="alert" className="flex items-start justify-between gap-3 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300"><span>{error}</span><button onClick={() => setError("")} aria-label="Dismiss error"><X className="h-4 w-4" /></button></div>}

      <div className="grid min-h-155 gap-5 xl:grid-cols-[320px_minmax(0,1fr)]">
        <section className="overflow-hidden rounded-2xl border border-white/10 bg-[#101014]">
          <div className="border-b border-white/10 p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-white">Your prompts</h2>
              <span className="rounded-full bg-white/5 px-2.5 py-1 text-xs text-zinc-400">{prompts.length}</span>
            </div>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
              <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search prompts..." className="w-full rounded-lg border border-white/10 bg-black/20 py-2.5 pl-9 pr-3 text-sm text-white outline-none placeholder:text-zinc-600 focus:border-violet-500/60" />
            </div>
          </div>
          <div className="max-h-135 space-y-1 overflow-y-auto p-2">
            {loading ? <div className="flex items-center justify-center gap-2 py-12 text-sm text-zinc-500"><Loader2 className="h-4 w-4 animate-spin" /> Loading prompts</div> : filteredPrompts.length ? filteredPrompts.map((prompt) => (
              <button key={prompt.id} onClick={() => void loadPrompt(prompt.id)} className={`w-full rounded-xl p-3 text-left transition ${selected?.id === prompt.id ? "bg-violet-500/15 ring-1 ring-violet-500/30" : "hover:bg-white/4"}`}>
                <div className="flex items-start justify-between gap-2">
                  <span className="line-clamp-1 text-sm font-medium text-zinc-100">{prompt.name}</span>
                  <span className="shrink-0 rounded-md bg-white/5 px-1.5 py-0.5 text-[10px] text-zinc-400">v{prompt.current_version}</span>
                </div>
                <p className="mt-1.5 line-clamp-2 text-xs leading-5 text-zinc-500">{prompt.description || "No description added"}</p>
                <p className="mt-2 text-[10px] text-zinc-600">Updated {formatDate(prompt.updated_at)}</p>
              </button>
            )) : <div className="px-4 py-12 text-center"><FilePlus2 className="mx-auto h-7 w-7 text-zinc-700" /><p className="mt-3 text-sm text-zinc-400">{search ? "No matching prompts" : "Your library is empty"}</p><p className="mt-1 text-xs text-zinc-600">{search ? "Try a different search." : "Create a prompt to start building your library."}</p></div>}
          </div>
        </section>

        <section className="min-w-0 overflow-hidden rounded-2xl border border-white/10 bg-[#101014]">
          {selected ? <>
            <div className="flex flex-col justify-between gap-4 border-b border-white/10 p-5 sm:flex-row sm:items-start">
              <div className="min-w-0">
                <div className="mb-2 flex items-center gap-2 text-xs text-violet-300"><Sparkles className="h-3.5 w-3.5" /> Saved prompt</div>
                <h2 className="truncate text-xl font-semibold text-white">{selected.name}</h2>
                <p className="mt-1 text-sm text-zinc-500">{selected.description || "No description"}</p>
                <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-zinc-500">
                  <span className="rounded-md bg-violet-500/10 px-2 py-1 text-violet-300">Current v{selected.current_version}</span>
                  <span className="inline-flex items-center gap-1"><Clock3 className="h-3.5 w-3.5" /> Updated {formatDate(selected.updated_at)}</span>
                </div>
              </div>
              <div className="flex shrink-0 flex-wrap gap-2">
                <button onClick={() => setHistoryOpen(true)} className="inline-flex items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-xs text-zinc-300 hover:bg-white/5"><History className="h-3.5 w-3.5" /> History</button>
                <button onClick={openEdit} disabled={!activeVersion} className="inline-flex items-center gap-2 rounded-lg bg-violet-600 px-3 py-2 text-xs font-medium text-white hover:bg-violet-500 disabled:opacity-50"><Pencil className="h-3.5 w-3.5" /> Edit prompt</button>
              </div>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-5 py-3">
              <div className="flex items-center gap-2 text-xs text-zinc-400"><Code2 className="h-4 w-4" /> Prompt content <span className="rounded bg-white/5 px-2 py-1">Version {activeVersion?.version_number ?? "—"}</span>{activeVersion && activeVersion.version_number !== selected.current_version && <span className="text-amber-300">Historical version</span>}</div>
              <button onClick={() => void copyContent()} disabled={!activeVersion} className="inline-flex items-center gap-2 rounded-lg border border-white/10 px-3 py-1.5 text-xs text-zinc-300 hover:bg-white/5 disabled:opacity-50">{copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}{copied ? "Copied" : "Copy"}</button>
            </div>
            <div className="min-h-90 p-5">
              {detailLoading ? <div className="flex items-center gap-2 py-10 text-sm text-zinc-500"><Loader2 className="h-4 w-4 animate-spin" /> Loading version...</div> : <pre className="min-h-80 whitespace-pre-wrap wrap-break-word rounded-xl border border-white/5 bg-black/25 p-5 font-mono text-sm leading-7 text-zinc-300">{activeVersion?.content}</pre>}
            </div>
            <div className="border-t border-white/10 px-5 py-3 text-xs text-zinc-600">Created {formatDate(selected.created_at)} · {versions.length} version{versions.length === 1 ? "" : "s"} stored</div>
          </> : <div className="flex min-h-155 flex-col items-center justify-center px-6 text-center"><div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-violet-500/10"><BookOpen className="h-7 w-7 text-violet-300" /></div><h2 className="mt-5 text-lg font-medium text-white">Select a prompt</h2><p className="mt-2 max-w-sm text-sm leading-6 text-zinc-500">Choose a prompt from your library to inspect its content and version history, or create a new one.</p><button onClick={openCreate} className="mt-5 inline-flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2.5 text-sm text-white hover:bg-violet-500"><Plus className="h-4 w-4" /> Create prompt</button></div>}
        </section>
      </div>

      {editorOpen && <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/75 p-4 backdrop-blur-sm" onMouseDown={(event) => { if (event.target === event.currentTarget && !saving) setEditorOpen(false); }}>
        <div className="my-8 w-full max-w-2xl rounded-2xl border border-white/10 bg-[#141419] shadow-2xl">
          <div className="flex items-center justify-between border-b border-white/10 px-5 py-4"><div><h2 className="font-semibold text-white">{mode === "create" ? "Create prompt" : "Edit prompt"}</h2><p className="mt-1 text-xs text-zinc-500">{mode === "create" ? "A new prompt starts at version 1." : "Saving creates a new immutable version."}</p></div><button disabled={saving} onClick={() => setEditorOpen(false)} className="rounded-lg p-2 text-zinc-500 hover:bg-white/5 hover:text-white"><X className="h-4 w-4" /></button></div>
          <div className="space-y-4 p-5">
            <label className="block space-y-2"><span className="text-xs font-medium text-zinc-300">Prompt name <span className="text-red-400">*</span></span><input maxLength={120} value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Product description generator" className="w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2.5 text-sm text-white outline-none placeholder:text-zinc-600 focus:border-violet-500/60" /></label>
            <label className="block space-y-2"><span className="text-xs font-medium text-zinc-300">Description</span><input maxLength={500} value={description} onChange={(event) => setDescription(event.target.value)} placeholder="What is this prompt used for?" className="w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2.5 text-sm text-white outline-none placeholder:text-zinc-600 focus:border-violet-500/60" /></label>
            <label className="block space-y-2"><span className="text-xs font-medium text-zinc-300">Prompt content <span className="text-red-400">*</span></span><textarea rows={12} value={content} onChange={(event) => setContent(event.target.value)} placeholder="Write your reusable prompt here..." className="w-full resize-y rounded-lg border border-white/10 bg-black/20 px-3 py-3 font-mono text-sm leading-6 text-zinc-200 outline-none placeholder:font-sans placeholder:text-zinc-600 focus:border-violet-500/60" /></label>
            <div className="flex items-center justify-between gap-3 border-t border-white/10 pt-4"><p className="text-xs text-zinc-600">Prompts are private to your account.</p><div className="flex gap-2"><button disabled={saving} onClick={() => setEditorOpen(false)} className="rounded-lg border border-white/10 px-4 py-2 text-sm text-zinc-300 hover:bg-white/5">Cancel</button><button disabled={saving || !name.trim() || !content.trim()} onClick={() => void savePrompt()} className="inline-flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-50">{saving && <Loader2 className="h-4 w-4 animate-spin" />}{mode === "create" ? "Create prompt" : "Save new version"}</button></div></div>
          </div>
        </div>
      </div>}

      {historyOpen && selected && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm" onMouseDown={(event) => { if (event.target === event.currentTarget) setHistoryOpen(false); }}>
        <div className="w-full max-w-lg overflow-hidden rounded-2xl border border-white/10 bg-[#141419] shadow-2xl">
          <div className="flex items-center justify-between border-b border-white/10 px-5 py-4"><div><h2 className="font-semibold text-white">Version history</h2><p className="mt-1 text-xs text-zinc-500">{selected.name}</p></div><button onClick={() => setHistoryOpen(false)} className="rounded-lg p-2 text-zinc-500 hover:bg-white/5 hover:text-white"><X className="h-4 w-4" /></button></div>
          <div className="max-h-[60vh] space-y-2 overflow-y-auto p-3">{versions.map((version) => <button key={version.id} onClick={() => void chooseVersion(version)} className={`flex w-full items-center justify-between gap-3 rounded-xl border p-3 text-left transition ${activeVersion?.version_number === version.version_number ? "border-violet-500/40 bg-violet-500/10" : "border-white/5 hover:bg-white/4"}`}><div className="flex items-center gap-3"><div className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/5 text-xs font-semibold text-zinc-300">v{version.version_number}</div><div><p className="text-sm font-medium text-zinc-200">Version {version.version_number}{version.version_number === selected.current_version ? " · Current" : ""}</p><p className="mt-1 text-xs text-zinc-500">{formatDate(version.created_at)}</p></div></div>{activeVersion?.version_number === version.version_number ? <Check className="h-4 w-4 text-violet-300" /> : <ChevronDown className="h-4 w-4 -rotate-90 text-zinc-600" />}</button>)}</div>
          <div className="border-t border-white/10 px-5 py-3 text-xs text-zinc-600">Select a version to view its saved content. To base a new version on an older one, select it and choose Edit prompt.</div>
        </div>
      </div>}
    </div>
  );
}
