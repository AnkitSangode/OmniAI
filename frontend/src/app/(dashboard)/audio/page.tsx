
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

type AudioTask = {
  id: string;
  task_type: string;
  input_text: string | null;
  transcript: string | null;
  provider: string;
  model: string;
  status: string;
  audio_url: string | null;
  source_filename: string | null;
  content_type: string | null;
  duration_seconds: number | null;
  created_at: string;
};

type AudioHistory = {
  items: AudioTask[];
  total: number;
};

function getErrorMessage(error: unknown, fallback: string): string {
  if (
    typeof error === "object" &&
    error !== null &&
    "response" in error
  ) {
    const response = (
      error as {
        response?: {
          data?: { detail?: string };
        };
      }
    ).response;

    if (response?.data?.detail) {
      return response.data.detail;
    }
  }

  if (error instanceof Error) {
    return error.message;
  }

  return fallback;
}

// Handles API paths returned either with or without the /api/v1 prefix.
function normalizeApiPath(path: string): string {
  if (/^https?:\/\//i.test(path)) {
    return path;
  }

  const baseURL = api.defaults.baseURL;

  if (!baseURL) {
    return path;
  }

  const basePath = new URL(baseURL).pathname.replace(/\/+$/, "");
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;

  if (
    basePath &&
    normalizedPath.startsWith(`${basePath}/`)
  ) {
    return normalizedPath.slice(basePath.length);
  }

  return normalizedPath;
}

export default function AudioWorkspacePage() {
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");

  const [tasks, setTasks] = useState<AudioTask[]>([]);
  const [total, setTotal] = useState(0);

  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);

  const [activeTask, setActiveTask] = useState<AudioTask | null>(null);

  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  // Keep Blob URLs cached without revoking them during normal state updates.
  const audioUrls = useRef<Record<string, string>>({});

  // Revoke cached URLs only when the workspace unmounts.
  useEffect(() => {
    return () => {
      Object.values(audioUrls.current).forEach((url) => {
        URL.revokeObjectURL(url);
      });

      audioUrls.current = {};
    };
  }, []);

  // Load audio history.
  const loadHistory = useCallback(async () => {
    try {
      setHistoryLoading(true);

      const response = await api.get<AudioHistory>("/audio/history", {
        params: {
          offset: 0,
          limit: 50,
        },
      });

      setTasks(response.data.items);
      setTotal(response.data.total);
      setError("");
    } catch (err) {
      setError(
        getErrorMessage(err, "Unable to load audio history.")
      );
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  // Retrieve an authenticated audio file and cache its Blob URL.
  const getAudioBlobUrl = async (task: AudioTask): Promise<string | null> => {
    if (!task.audio_url) {
      return null;
    }

    const cachedUrl = audioUrls.current[task.id];

    if (cachedUrl) {
      return cachedUrl;
    }

    const response = await api.get(
      normalizeApiPath(task.audio_url),
      {
        responseType: "blob",
      }
    );

    const url = URL.createObjectURL(response.data);

    audioUrls.current[task.id] = url;

    return url;
  };

  // Speech-to-Text.
  const handleTranscription = async () => {
    if (!file) {
      setError("Please select an audio file first.");
      return;
    }

    setLoading(true);
    setError("");
    setSuccess("");
    setActiveTask(null);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await api.post<AudioTask>(
        "/audio/transcribe",
        formData,
        {
          headers: {
            "Content-Type": "multipart/form-data",
          },
          timeout: 0,
        }
      );

      setActiveTask(response.data);
      setSuccess("Audio transcription completed.");
      setFile(null);

      await loadHistory();
    } catch (err) {
      setError(
        getErrorMessage(err, "Audio transcription failed.")
      );
    } finally {
      setLoading(false);
    }
  };

  // Text-to-Speech.
  const handleSpeechGeneration = async () => {
    if (!text.trim()) {
      setError("Please enter some text first.");
      return;
    }

    setLoading(true);
    setError("");
    setSuccess("");
    setActiveTask(null);

    try {
      const response = await api.post<AudioTask>(
        "/audio/speech",
        {
          text: text.trim(),
        },
        {
          timeout: 0,
        }
      );

      setActiveTask(response.data);
      setSuccess("Speech generation completed.");
      setText("");

      await loadHistory();
    } catch (err) {
      setError(
        getErrorMessage(err, "Speech generation failed.")
      );
    } finally {
      setLoading(false);
    }
  };

  // Play an authenticated audio file.
  const playAudio = async (task: AudioTask) => {
    try {
      setError("");

      const url = await getAudioBlobUrl(task);

      if (!url) {
        throw new Error("No audio file is available.");
      }

      const audio = new Audio(url);
      await audio.play();
    } catch (err) {
      setError(
        getErrorMessage(err, "Unable to play audio.")
      );
    }
  };

  // Download an authenticated audio file.
  const downloadAudio = async (task: AudioTask) => {
    try {
      setError("");

      const url = await getAudioBlobUrl(task);

      if (!url) {
        throw new Error("No audio file is available.");
      }

      const anchor = document.createElement("a");

      anchor.href = url;
      anchor.download =
        task.task_type === "transcription"
          ? task.source_filename || `omniai-${task.id}.wav`
          : `omniai-${task.id}.wav`;

      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
    } catch (err) {
      setError(
        getErrorMessage(err, "Audio download failed.")
      );
    }
  };

  const isMockProvider = (provider: string) =>
    provider.toLowerCase().includes("mock");

  return (
    <section className="space-y-8 pb-10 text-zinc-100">
      {/* Page heading */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">
          Audio AI Workspace
        </h1>

        <p className="mt-2 text-sm text-zinc-400">
          Convert speech into text and generate audio from written text.
        </p>
      </div>

      {/* Error message */}
      {error && (
        <div
          role="alert"
          className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300"
        >
          {error}
        </div>
      )}

      {/* Success message */}
      {success && (
        <div
          role="status"
          className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-300"
        >
          {success}
        </div>
      )}

      {/* Main workspace */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Speech to Text */}
        <section className="rounded-2xl border border-zinc-800 bg-zinc-900/60 p-6">
          <div className="mb-5">
            <h2 className="text-xl font-semibold">
              Speech to Text
            </h2>

            <p className="mt-1 text-sm text-zinc-400">
              Upload an audio file to generate its transcription.
            </p>
          </div>

          <label
            htmlFor="audio-file"
            className="mb-2 block text-sm font-medium text-zinc-300"
          >
            Audio file
          </label>

          <input
            id="audio-file"
            type="file"
            accept="audio/*"
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setError("");
            }}
            className="block w-full rounded-lg border border-zinc-700 bg-zinc-950 p-3 text-sm text-zinc-300 file:mr-4 file:rounded-md file:border-0 file:bg-zinc-800 file:px-3 file:py-2 file:text-zinc-200"
          />

          {file && (
            <p className="mt-2 text-xs text-zinc-400">
              Selected: {file.name} (
              {(file.size / 1024 / 1024).toFixed(2)} MB)
            </p>
          )}

          <button
            onClick={handleTranscription}
            disabled={loading || !file}
            className="mt-5 w-full rounded-lg bg-indigo-600 px-4 py-3 font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Processing..." : "Transcribe Audio"}
          </button>
        </section>

        {/* Text to Speech */}
        <section className="rounded-2xl border border-zinc-800 bg-zinc-900/60 p-6">
          <div className="mb-5">
            <h2 className="text-xl font-semibold">
              Text to Speech
            </h2>

            <p className="mt-1 text-sm text-zinc-400">
              Enter text to generate spoken audio.
            </p>
          </div>

          <label
            htmlFor="speech-text"
            className="mb-2 block text-sm font-medium text-zinc-300"
          >
            Text input
          </label>

          <textarea
            id="speech-text"
            value={text}
            onChange={(event) => setText(event.target.value)}
            maxLength={5000}
            rows={5}
            placeholder="Enter the text you want to convert into audio..."
            className="w-full resize-y rounded-lg border border-zinc-700 bg-zinc-950 p-3 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-indigo-500"
          />

          <div className="mt-2 text-right text-xs text-zinc-500">
            {text.length}/5000 characters
          </div>

          <button
            onClick={handleSpeechGeneration}
            disabled={loading || !text.trim()}
            className="mt-2 w-full rounded-lg bg-indigo-600 px-4 py-3 font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Processing..." : "Generate Speech"}
          </button>
        </section>
      </div>

      {/* Latest result */}
      {activeTask && (
        <section className="rounded-2xl border border-indigo-500/30 bg-indigo-500/5 p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold">
                Latest Result
              </h2>

              <p className="mt-1 text-xs text-zinc-400">
                {activeTask.provider} · {activeTask.model} ·{" "}
                {activeTask.status}
              </p>
            </div>

            {isMockProvider(activeTask.provider) && (
              <span className="rounded-full bg-amber-500/10 px-3 py-1 text-xs text-amber-300">
                Mock provider
              </span>
            )}
          </div>

          {activeTask.transcript && (
            <div className="mt-5">
              <h3 className="mb-2 text-sm font-medium text-zinc-300">
                Transcription
              </h3>

              <p className="whitespace-pre-wrap rounded-lg bg-zinc-950 p-4 text-sm text-zinc-200">
                {activeTask.transcript}
              </p>

              <button
                onClick={() =>
                  void navigator.clipboard.writeText(
                    activeTask.transcript || ""
                  )
                }
                className="mt-2 rounded-lg border border-zinc-700 px-3 py-2 text-xs hover:bg-zinc-800"
              >
                Copy transcript
              </button>
            </div>
          )}

          {activeTask.input_text && (
            <div className="mt-5">
              <h3 className="mb-2 text-sm font-medium text-zinc-300">
                Input text
              </h3>

              <p className="rounded-lg bg-zinc-950 p-4 text-sm text-zinc-200">
                {activeTask.input_text}
              </p>
            </div>
          )}

          {activeTask.audio_url && (
            <div className="mt-5 flex flex-wrap gap-3">
              <button
                onClick={() => void playAudio(activeTask)}
                className="rounded-lg bg-zinc-800 px-4 py-2 text-sm hover:bg-zinc-700"
              >
                Play Audio
              </button>

              <button
                onClick={() => void downloadAudio(activeTask)}
                className="rounded-lg border border-zinc-700 px-4 py-2 text-sm hover:bg-zinc-800"
              >
                Download Audio
              </button>
            </div>
          )}
        </section>
      )}

      {/* Audio history */}
      <section className="rounded-2xl border border-zinc-800 bg-zinc-900/60 p-6">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">
              Audio History
            </h2>

            <p className="mt-1 text-sm text-zinc-400">
              Your previous audio tasks.
            </p>
          </div>

          <button
            onClick={() => void loadHistory()}
            disabled={historyLoading}
            className="rounded-lg border border-zinc-700 px-3 py-2 text-sm hover:bg-zinc-800 disabled:opacity-50"
          >
            {historyLoading ? "Refreshing..." : "Refresh"}
          </button>
        </div>

        {historyLoading ? (
          <p className="text-sm text-zinc-400">
            Loading history...
          </p>
        ) : tasks.length === 0 ? (
          <p className="rounded-lg bg-zinc-950 p-5 text-center text-sm text-zinc-500">
            No audio tasks yet. Upload audio or generate speech to get started.
          </p>
        ) : (
          <div className="space-y-3">
            {tasks.map((task) => (
              <div
                key={task.id}
                className="flex flex-col gap-3 rounded-xl border border-zinc-800 bg-zinc-950 p-4 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">
                      {task.task_type === "transcription"
                        ? "Speech to Text"
                        : "Text to Speech"}
                    </span>

                    <span className="rounded-full bg-zinc-800 px-2 py-1 text-xs text-zinc-300">
                      {task.status}
                    </span>

                    {isMockProvider(task.provider) && (
                      <span className="rounded-full bg-amber-500/10 px-2 py-1 text-xs text-amber-300">
                        Mock
                      </span>
                    )}
                  </div>

                  <p className="mt-1 truncate text-sm text-zinc-400">
                    {task.source_filename ||
                      task.input_text ||
                      task.transcript ||
                      task.id}
                  </p>

                  <p className="mt-1 text-xs text-zinc-500">
                    {task.provider} · {task.model}
                  </p>

                  <p className="mt-1 text-xs text-zinc-500">
                    {new Date(task.created_at).toLocaleString()}
                  </p>
                </div>

                <div className="flex shrink-0 gap-2">
                  <button
                    onClick={() => setActiveTask(task)}
                    className="rounded-lg border border-zinc-700 px-3 py-2 text-xs hover:bg-zinc-800"
                  >
                    View
                  </button>

                  {task.audio_url && (
                    <>
                      <button
                        onClick={() => void playAudio(task)}
                        className="rounded-lg bg-zinc-800 px-3 py-2 text-xs hover:bg-zinc-700"
                      >
                        Play
                      </button>

                      <button
                        onClick={() => void downloadAudio(task)}
                        className="rounded-lg border border-zinc-700 px-3 py-2 text-xs hover:bg-zinc-800"
                      >
                        Download
                      </button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        <p className="mt-4 text-xs text-zinc-500">
          Showing {tasks.length} of {total} tasks.
        </p>
      </section>
    </section>
  );
}
