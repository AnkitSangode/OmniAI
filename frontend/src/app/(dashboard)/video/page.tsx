
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

type VideoTask = {
  id: string;
  source_filename: string;
  content_type: string | null;
  duration_seconds: number | null;
  width: number | null;
  height: number | null;
  frame_rate: number | null;
  video_codec: string | null;
  audio_codec: string | null;
  metadata_json: Record<string, unknown> | null;
  transcript: string | null;
  summary: string | null;
  captions: string | null;
  transcription_provider: string | null;
  transcription_model: string | null;
  status: string;
  error_message: string | null;
  video_url: string | null;
  created_at: string;
};

type VideoHistoryResponse = {
  items: VideoTask[];
  total: number;
};

const MAX_FILE_SIZE = 100 * 1024 * 1024;

const ACCEPTED_TYPES = [
  "video/mp4",
  "video/quicktime",
  "video/x-msvideo",
  "video/x-matroska",
  "video/webm",
  "video/x-m4v",
];

// Convert unknown API values into safe, renderable text.
function toDisplayText(value: unknown): string {
  if (typeof value === "string") return value;

  if (value === null || value === undefined) return "";

  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  if (Array.isArray(value)) {
    return value.map(toDisplayText).join("\n");
  }

  if (typeof value === "object") {
    const item = value as Record<string, unknown>;

    if (typeof item.msg === "string") {
      const location = Array.isArray(item.loc)
        ? item.loc.map(String).join(" → ")
        : "";

      return location ? `${location}: ${item.msg}` : item.msg;
    }

    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return "Unable to display this response.";
    }
  }

  return "Unexpected API response.";
}

// Normalize Axios and FastAPI errors.
function getErrorMessage(error: unknown): string {
  const err = error as {
    response?: {
      data?: {
        detail?: unknown;
        message?: unknown;
      };
    };
    message?: string;
  };

  const detail = err.response?.data?.detail;
  const message = err.response?.data?.message;

  if (detail !== undefined && detail !== null) {
    return toDisplayText(detail);
  }

  if (message !== undefined && message !== null) {
    return toDisplayText(message);
  }

  return err.message || "Something went wrong. Please try again.";
}

function formatDuration(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return "—";

  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.floor(seconds % 60);

  return `${minutes}:${String(remainingSeconds).padStart(2, "0")}`;
}

function formatDate(value: string): string {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return "Unknown date";

  return date.toLocaleString();
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    completed: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    partially_completed:
      "bg-amber-500/10 text-amber-400 border-amber-500/20",
    processing: "bg-blue-500/10 text-blue-400 border-blue-500/20",
    failed: "bg-red-500/10 text-red-400 border-red-500/20",
    pending: "bg-zinc-500/10 text-zinc-400 border-zinc-500/20",
  };

  return (
    <span
      className={`inline-flex rounded-full border px-3 py-1 text-xs font-medium ${
        styles[status] || styles.pending
      }`}
    >
      {status.replaceAll("_", " ")}
    </span>
  );
}

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5">
      <div className="mb-4">
        <h2 className="text-lg font-semibold text-white">{title}</h2>

        {description && (
          <p className="mt-1 text-sm text-zinc-400">{description}</p>
        )}
      </div>

      {children}
    </section>
  );
}

export default function WorkspacePage() {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [videoPreview, setVideoPreview] = useState<string | null>(null);

  const [currentTask, setCurrentTask] = useState<VideoTask | null>(null);
  const [history, setHistory] = useState<VideoTask[]>([]);
  const [totalHistory, setTotalHistory] = useState(0);

  const [isProcessing, setIsProcessing] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const [isLoadingVideo, setIsLoadingVideo] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Load previously processed videos.
  const loadHistory = useCallback(async () => {
    setIsLoadingHistory(true);

    try {
      const response = await api.get<VideoHistoryResponse>(
        "/video/history"
      );

      setHistory(response.data.items || []);
      setTotalHistory(response.data.total || 0);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsLoadingHistory(false);
    }
  }, []);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  // Revoke temporary browser URLs when the preview changes.
  useEffect(() => {
    return () => {
      if (videoPreview?.startsWith("blob:")) {
        URL.revokeObjectURL(videoPreview);
      }
    };
  }, [videoPreview]);

  // Validate and select an uploaded video.
  const handleFileSelection = (file: File | undefined) => {
    if (!file) return;

    setError(null);

    if (!ACCEPTED_TYPES.includes(file.type)) {
      setError(
        "Unsupported video format. Please upload MP4, MOV, AVI, MKV or WebM."
      );
      return;
    }

    if (file.size > MAX_FILE_SIZE) {
      setError("The maximum allowed video size is 100 MB.");
      return;
    }

    setSelectedFile(file);
    setCurrentTask(null);
    setVideoPreview(URL.createObjectURL(file));
  };

  // Upload and process the selected video.
  const handleProcessVideo = async () => {
    if (!selectedFile) {
      setError("Please select a video before processing.");
      return;
    }

    setIsProcessing(true);
    setError(null);
    setCurrentTask(null);

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);

      const response = await api.post<VideoTask>(
        "/video/process",
        formData,
        {
          // Local Whisper processing can take several minutes.
          // The shared Axios interceptor removes the JSON Content-Type
          // header for FormData requests.
          timeout: 300000,
        }
      );

      setCurrentTask(response.data);

      await loadHistory();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsProcessing(false);
    }
  };

  // Load a historical video using authenticated Axios.
  const openHistoryVideo = async (task: VideoTask) => {
    setIsLoadingVideo(true);
    setError(null);

    try {
      const response = await api.get(
        `/video/${task.id}/file`,
        {
          responseType: "blob",
        }
      );

      const objectUrl = URL.createObjectURL(response.data);

      setVideoPreview(objectUrl);
      setSelectedFile(null);
      setCurrentTask(task);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsLoadingVideo(false);
    }
  };

  // Download a historical video.
  const downloadHistoryVideo = async (task: VideoTask) => {
    try {
      const response = await api.get(
        `/video/${task.id}/file`,
        {
          responseType: "blob",
        }
      );

      const objectUrl = URL.createObjectURL(response.data);
      const link = document.createElement("a");

      link.href = objectUrl;
      link.download = task.source_filename;

      document.body.appendChild(link);
      link.click();
      link.remove();

      URL.revokeObjectURL(objectUrl);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  // Copy transcript to clipboard.
  const copyTranscript = async () => {
    if (!currentTask?.transcript) return;

    try {
      await navigator.clipboard.writeText(currentTask.transcript);

      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Unable to copy transcript.");
    }
  };

  // Reset workspace for a new upload.
  const startNewUpload = () => {
    setSelectedFile(null);
    setCurrentTask(null);
    setVideoPreview(null);
    setError(null);
    setCopied(false);

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  return (
    <div className="space-y-8 pb-10">
      {/* Header */}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-3xl font-bold text-white">
            Video AI Workspace
          </h1>

          <p className="mt-2 text-sm text-zinc-400">
            Upload videos, extract audio, transcribe speech and generate
            AI-powered summaries and captions.
          </p>
        </div>

        <button
          onClick={startNewUpload}
          className="rounded-lg border border-zinc-700 px-4 py-2 text-sm font-medium text-zinc-200 transition hover:bg-zinc-800"
        >
          + New upload
        </button>
      </div>

      {/* Error message */}
      {error && (
        <div
          role="alert"
          className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300"
        >
          <p className="whitespace-pre-wrap">
            {toDisplayText(error)}
          </p>
        </div>
      )}

      {/* Upload section */}
      <Section
        title="Upload video"
        description="Supported formats: MP4, MOV, AVI, MKV and WebM. Maximum size: 100 MB."
      >
        <div
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            handleFileSelection(event.dataTransfer.files[0]);
          }}
          className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-zinc-700 bg-zinc-950/50 px-6 py-10 text-center transition hover:border-zinc-500"
        >
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-zinc-800 text-2xl">
            <span aria-hidden="true">▶</span>
          </div>

          <p className="font-medium text-white">
            Drag and drop your video here
          </p>

          <p className="mt-1 text-sm text-zinc-500">
            Or select a file from your computer
          </p>

          <input
            ref={fileInputRef}
            type="file"
            accept="video/*"
            className="hidden"
            onChange={(event) =>
              handleFileSelection(event.target.files?.[0])
            }
          />

          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="mt-5 rounded-lg bg-white px-5 py-2.5 text-sm font-semibold text-black transition hover:bg-zinc-200"
          >
            Choose video
          </button>

          {selectedFile && (
            <div className="mt-5 rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-3 text-left">
              <p className="text-sm font-medium text-white">
                {selectedFile.name}
              </p>

              <p className="mt-1 text-xs text-zinc-400">
                {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB
              </p>
            </div>
          )}
        </div>

        {selectedFile && (
          <button
            onClick={handleProcessVideo}
            disabled={isProcessing}
            className="mt-5 w-full rounded-lg bg-indigo-600 px-5 py-3 font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isProcessing ? "Processing video..." : "Process video"}
          </button>
        )}

        {isProcessing && (
          <p className="mt-3 text-center text-sm text-zinc-400">
            Extracting metadata and audio, then transcribing speech.
            This may take a few minutes.
          </p>
        )}
      </Section>

      {/* Video preview */}
      {videoPreview && (
        <Section
          title="Video preview"
          description={
            currentTask?.source_filename || selectedFile?.name
          }
        >
          {isLoadingVideo ? (
            <p className="text-sm text-zinc-400">
              Loading video...
            </p>
          ) : (
            <video
              key={videoPreview}
              src={videoPreview}
              controls
              className="max-h-[480px] w-full rounded-lg bg-black"
            />
          )}
        </Section>
      )}

      {/* Processing results */}
      {currentTask && (
        <>
          <Section
            title="Processing overview"
            description="Results from the video processing pipeline."
          >
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="font-medium text-white">
                  {currentTask.source_filename}
                </p>

                <p className="mt-1 text-xs text-zinc-500">
                  Processed {formatDate(currentTask.created_at)}
                </p>
              </div>

              <StatusBadge status={currentTask.status} />
            </div>

            {currentTask.status === "partially_completed" && (
              <div className="mb-5 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4">
                <p className="font-medium text-amber-300">
                  Core video processing completed with optional AI stages unavailable.
                </p>

                <p className="mt-1 text-sm text-amber-200/80">
                  Your video metadata and transcript were saved successfully.
                  Summary and caption generation could not be completed.
                </p>
              </div>
            )}

            {currentTask.error_message && (
              <div className="mb-5 rounded-lg border border-zinc-700 bg-zinc-950 p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-zinc-400">
                  Processing details
                </p>

                <p className="mt-2 whitespace-pre-wrap text-sm text-zinc-300">
                  {toDisplayText(currentTask.error_message)}
                </p>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {[
                {
                  label: "Duration",
                  value: formatDuration(currentTask.duration_seconds),
                },
                {
                  label: "Resolution",
                  value:
                    currentTask.width && currentTask.height
                      ? `${currentTask.width} × ${currentTask.height}`
                      : "—",
                },
                {
                  label: "Frame rate",
                  value: currentTask.frame_rate
                    ? `${currentTask.frame_rate} FPS`
                    : "—",
                },
                {
                  label: "Video codec",
                  value: currentTask.video_codec || "—",
                },
                {
                  label: "Audio codec",
                  value: currentTask.audio_codec || "—",
                },
                {
                  label: "Transcription",
                  value: currentTask.transcription_provider || "—",
                },
                {
                  label: "Transcription model",
                  value: currentTask.transcription_model || "—",
                },
              ].map((item) => (
                <div
                  key={item.label}
                  className="rounded-lg border border-zinc-800 bg-zinc-950 p-4"
                >
                  <p className="text-xs text-zinc-500">
                    {item.label}
                  </p>

                  <p className="mt-2 break-words text-sm font-semibold text-white">
                    {item.value}
                  </p>
                </div>
              ))}
            </div>
          </Section>

          {/* Transcript */}
          <Section
            title="Transcript"
            description="Speech-to-text output generated by the transcription provider."
          >
            {currentTask.transcript ? (
              <>
                <div className="rounded-lg bg-zinc-950 p-4">
                  <p className="whitespace-pre-wrap text-sm leading-7 text-zinc-200">
                    {currentTask.transcript}
                  </p>
                </div>

                <button
                  onClick={copyTranscript}
                  className="mt-3 rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-300 transition hover:bg-zinc-800"
                >
                  {copied ? "Copied!" : "Copy transcript"}
                </button>
              </>
            ) : (
              <p className="text-sm text-zinc-500">
                No transcript is available for this video.
              </p>
            )}
          </Section>

          {/* Summary */}
          <Section
            title="AI summary"
            description="A concise summary generated from the video transcript."
          >
            {currentTask.summary ? (
              <p className="whitespace-pre-wrap text-sm leading-7 text-zinc-200">
                {currentTask.summary}
              </p>
            ) : (
              <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-4">
                <p className="text-sm text-zinc-400">
                  Summary is not available.
                </p>

                <p className="mt-1 text-xs text-zinc-500">
                  This optional stage requires a working LLM provider through LiteLLM.
                </p>
              </div>
            )}
          </Section>

          {/* Captions */}
          <Section
            title="Generated captions"
            description="Caption output generated from the transcript."
          >
            {currentTask.captions ? (
              <div className="rounded-lg bg-zinc-950 p-4">
                <pre className="whitespace-pre-wrap break-words font-mono text-sm leading-7 text-zinc-200">
                  {currentTask.captions}
                </pre>
              </div>
            ) : (
              <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-4">
                <p className="text-sm text-zinc-400">
                  Captions are not available.
                </p>

                <p className="mt-1 text-xs text-zinc-500">
                  Caption generation requires a working LLM provider through LiteLLM.
                </p>
              </div>
            )}
          </Section>
        </>
      )}

      {/* Video history */}
      <Section
        title="Video history"
        description={`${totalHistory} previously processed video(s).`}
      >
        {isLoadingHistory ? (
          <p className="text-sm text-zinc-400">
            Loading video history...
          </p>
        ) : history.length === 0 ? (
          <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-6 text-center">
            <p className="text-sm text-zinc-400">
              No processed videos yet.
            </p>

            <p className="mt-1 text-xs text-zinc-500">
              Your processed videos will appear here.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {history.map((task) => (
              <div
                key={task.id}
                className="flex flex-col justify-between gap-4 rounded-lg border border-zinc-800 bg-zinc-950 p-4 sm:flex-row sm:items-center"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-white">
                    {task.source_filename}
                  </p>

                  <p className="mt-1 text-xs text-zinc-500">
                    {formatDate(task.created_at)}
                    {" · "}
                    {formatDuration(task.duration_seconds)}
                  </p>

                  <div className="mt-2">
                    <StatusBadge status={task.status} />
                  </div>
                </div>

                <div className="flex shrink-0 gap-2">
                  <button
                    onClick={() => openHistoryVideo(task)}
                    disabled={isLoadingVideo}
                    className="rounded-lg border border-zinc-700 px-3 py-2 text-xs font-medium text-zinc-300 transition hover:bg-zinc-800 disabled:opacity-50"
                  >
                    Play
                  </button>

                  <button
                    onClick={() => downloadHistoryVideo(task)}
                    className="rounded-lg border border-zinc-700 px-3 py-2 text-xs font-medium text-zinc-300 transition hover:bg-zinc-800"
                  >
                    Download
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        <button
          onClick={loadHistory}
          disabled={isLoadingHistory}
          className="mt-4 rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-300 transition hover:bg-zinc-800 disabled:opacity-50"
        >
          {isLoadingHistory ? "Refreshing..." : "Refresh history"}
        </button>
      </Section>
    </div>
  );
}
