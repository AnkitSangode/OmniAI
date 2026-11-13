
"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL;

type Usage = {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
};

type GenerationResult = {
  request_id: string;
  model: string;
  content: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
};

export default function WorkspacePage() {
  const [prompt, setPrompt] = useState("");
  const [model, setModel] = useState("omni-primary");
  const [temperature, setTemperature] = useState(0.7);
  const [maxTokens, setMaxTokens] = useState(1024);

  const [output, setOutput] = useState("");
  const [usage, setUsage] = useState<Usage | null>(null);
  const [requestId, setRequestId] = useState("");
  const [usedModel, setUsedModel] = useState("");
  const [error, setError] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);

  const abortController = useRef<AbortController | null>(null);

  const resetOutput = () => {
    setOutput("");
    setUsage(null);
    setRequestId("");
    setUsedModel("");
    setError("");
  };

  const validatePrompt = () => {
    if (!prompt.trim()) {
      setError("Please enter a prompt before generating.");
      return false;
    }

    resetOutput();
    return true;
  };

  // Standard, non-streaming generation
  const generateText = async () => {
    if (!validatePrompt()) return;

    setIsGenerating(true);

    try {
      const response = await api.post<GenerationResult>(
        "/text/generate",
        {
          messages: [{ role: "user", content: prompt.trim() }],
          model,
          temperature,
          max_tokens: maxTokens,
        },
        { timeout: 120000 }
      );

      const result = response.data;

      setOutput(result.content);
      setRequestId(result.request_id);
      setUsedModel(result.model);
      setUsage({
        prompt_tokens: result.prompt_tokens,
        completion_tokens: result.completion_tokens,
        total_tokens: result.total_tokens,
      });
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response
          ?.data?.detail;

      setError(message || "Text generation failed. Please try again.");
    } finally {
      setIsGenerating(false);
    }
  };

  // Streaming generation
  const generateStream = async () => {
    if (!validatePrompt()) return;

    if (!API_URL) {
      setError("API URL is not configured.");
      return;
    }

    const controller = new AbortController();
    abortController.current = controller;
    setIsGenerating(true);

    try {
      const token = localStorage.getItem("omniai_access_token");

      const response = await fetch(`${API_URL}/text/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          messages: [{ role: "user", content: prompt.trim() }],
          model,
          temperature,
          max_tokens: maxTokens,
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        let message = "Streaming generation failed.";

        try {
          const data = await response.json();
          message = data.detail || message;
        } catch {
          // Keep the fallback message.
        }

        throw new Error(message);
      }

      if (!response.body) {
        throw new Error("Streaming is not supported by this response.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      let buffer = "";
      let accumulatedText = "";

      const processEvent = (event: string) => {
        const dataLines = event
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trim());

        if (!dataLines.length) return;

        const data = JSON.parse(dataLines.join("\n"));

        if (data.type === "content" && typeof data.content === "string") {
          accumulatedText += data.content;
          setOutput(accumulatedText);
        }

        if (data.type === "usage") {
          setUsage({
            prompt_tokens: data.prompt_tokens ?? 0,
            completion_tokens: data.completion_tokens ?? 0,
            total_tokens: data.total_tokens ?? 0,
          });
        }

        if (data.type === "finish") {
          if (data.model) setUsedModel(data.model);
          if (data.request_id) setRequestId(data.request_id);
        }

        if (data.type === "error") {
          throw new Error(
            data.message || "The AI generation service encountered an error."
          );
        }

        if (data.type === "done") {
          if (data.request_id) setRequestId(data.request_id);
          if (data.model) setUsedModel(data.model);
        }
      };

      while (true) {
        const { value, done } = await reader.read();

        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        const events = buffer.split(/\r?\n\r?\n/);
        buffer = events.pop() || "";

        for (const event of events) {
          if (event.trim()) processEvent(event);
        }
      }

      // Process any final event left in the buffer.
      if (buffer.trim()) {
        processEvent(buffer);
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") {
        setError("Generation stopped.");
      } else {
        setError(
          err instanceof Error
            ? err.message
            : "Streaming generation failed. Please try again."
        );
      }
    } finally {
      abortController.current = null;
      setIsGenerating(false);
    }
  };

  const stopGeneration = () => {
    abortController.current?.abort();
  };

  return (
    <section className="mx-auto max-w-5xl space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Text AI Workspace</h1>
        <p className="mt-2 text-sm text-zinc-400">
          Generate text using OmniAI's unified language model gateway.
        </p>
      </div>

      <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-6 space-y-5">
        <div>
          <label
            htmlFor="prompt"
            className="mb-2 block text-sm font-medium text-zinc-200"
          >
            Your prompt
          </label>

          <textarea
            id="prompt"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Ask anything..."
            rows={7}
            disabled={isGenerating}
            className="w-full resize-y rounded-lg border border-zinc-700 bg-zinc-950 p-4 text-sm text-zinc-100 outline-none transition focus:border-zinc-400 disabled:opacity-60"
          />
        </div>

        <div className="grid gap-5 sm:grid-cols-3">
          <div>
            <label
              htmlFor="model"
              className="mb-2 block text-sm font-medium text-zinc-300"
            >
              Model route
            </label>
            <select
              id="model"
              value={model}
              onChange={(event) => setModel(event.target.value)}
              disabled={isGenerating}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-950 p-3 text-sm text-zinc-100 outline-none focus:border-zinc-400"
            >
              <option value="omni-primary">Omni Primary</option>
              <option value="omni-gemini-fallback">Gemini Fallback</option>
            </select>
          </div>

          <div>
            <label
              htmlFor="temperature"
              className="mb-2 block text-sm font-medium text-zinc-300"
            >
              Temperature: {temperature.toFixed(1)}
            </label>
            <input
              id="temperature"
              type="range"
              min="0"
              max="2"
              step="0.1"
              value={temperature}
              onChange={(event) =>
                setTemperature(Number(event.target.value))
              }
              disabled={isGenerating}
              className="mt-3 w-full accent-white"
            />
          </div>

          <div>
            <label
              htmlFor="maxTokens"
              className="mb-2 block text-sm font-medium text-zinc-300"
            >
              Maximum tokens
            </label>
            <select
              id="maxTokens"
              value={maxTokens}
              onChange={(event) => setMaxTokens(Number(event.target.value))}
              disabled={isGenerating}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-950 p-3 text-sm text-zinc-100 outline-none focus:border-zinc-400"
            >
              <option value={256}>256</option>
              <option value={512}>512</option>
              <option value={1024}>1024</option>
              <option value={2048}>2048</option>
              <option value={4096}>4096</option>
              <option value={8192}>8192</option>
            </select>
          </div>
        </div>

        <div className="flex flex-wrap gap-3">
          <button
            onClick={generateStream}
            disabled={isGenerating || !prompt.trim()}
            className="rounded-lg bg-white px-5 py-2.5 text-sm font-semibold text-black transition hover:bg-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Generate with streaming
          </button>

          <button
            onClick={generateText}
            disabled={isGenerating || !prompt.trim()}
            className="rounded-lg border border-zinc-700 px-5 py-2.5 text-sm font-medium text-zinc-200 transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Generate normally
          </button>

          {isGenerating && (
            <button
              onClick={stopGeneration}
              className="rounded-lg border border-red-800 px-5 py-2.5 text-sm font-medium text-red-400 transition hover:bg-red-950"
            >
              Stop
            </button>
          )}
        </div>

        {error && (
          <div
            role="alert"
            className="rounded-lg border border-red-900 bg-red-950/40 p-3 text-sm text-red-300"
          >
            {error}
          </div>
        )}
      </div>

      <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-6">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">Generated response</h2>
          {isGenerating && (
            <span className="text-xs text-zinc-400">Generating...</span>
          )}
        </div>

        {output ? (
          <div className="whitespace-pre-wrap wrap-break-word text-sm leading-7 text-zinc-200">
            {output}
            {isGenerating && (
              <span className="ml-1 inline-block h-4 w-1 animate-pulse bg-zinc-300" />
            )}
          </div>
        ) : (
          <p className="text-sm text-zinc-500">
            Your generated response will appear here.
          </p>
        )}

        {usage && (
          <div className="mt-6 border-t border-zinc-800 pt-4">
            <h3 className="mb-3 text-sm font-semibold text-zinc-300">
              Request usage
            </h3>

            <div className="grid grid-cols-3 gap-3">
              <div className="rounded-lg bg-zinc-950 p-3">
                <p className="text-xs text-zinc-500">Prompt tokens</p>
                <p className="mt-1 text-lg font-semibold">
                  {usage.prompt_tokens}
                </p>
              </div>

              <div className="rounded-lg bg-zinc-950 p-3">
                <p className="text-xs text-zinc-500">Completion tokens</p>
                <p className="mt-1 text-lg font-semibold">
                  {usage.completion_tokens}
                </p>
              </div>

              <div className="rounded-lg bg-zinc-950 p-3">
                <p className="text-xs text-zinc-500">Total tokens</p>
                <p className="mt-1 text-lg font-semibold">
                  {usage.total_tokens}
                </p>
              </div>
            </div>
          </div>
        )}

        {(requestId || usedModel) && (
          <div className="mt-4 space-y-1 text-xs text-zinc-500">
            {usedModel && <p>Model: {usedModel}</p>}
            {requestId && <p>Request ID: {requestId}</p>}
          </div>
        )}
      </div>
    </section>
  );
}
