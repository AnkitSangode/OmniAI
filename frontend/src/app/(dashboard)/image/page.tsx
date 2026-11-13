
"use client";

import { useCallback, useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL;

interface ImageGeneration {
  id: string;
  prompt: string;
  provider: string;
  model: string;
  status: string;
  image_url: string | null;
  width: number;
  height: number;
  created_at: string;
}

interface ImageHistory {
  items: ImageGeneration[];
  total: number;
}

function getToken() {
  return localStorage.getItem("omniai_access_token");
}

async function getErrorMessage(response: Response) {
  try {
    const data = await response.json();
    return data.detail || "Something went wrong.";
  } catch {
    return "Something went wrong.";
  }
}

// Authenticated image thumbnail for history cards
function HistoryThumbnail({
  image,
}: {
  image: ImageGeneration;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;

    async function loadThumbnail() {
      try {
        const token = getToken();

        if (!token || !API_URL) {
          setFailed(true);
          return;
        }

        const response = await fetch(
          `${API_URL}/images/${image.id}/file`,
          {
            headers: {
              Authorization: `Bearer ${token}`,
            },
          }
        );

        if (!response.ok) {
          throw new Error("Unable to load thumbnail.");
        }

        const blob = await response.blob();

        objectUrl = URL.createObjectURL(blob);

        if (!cancelled) {
          setUrl(objectUrl);
        } else {
          URL.revokeObjectURL(objectUrl);
        }
      } catch {
        if (!cancelled) {
          setFailed(true);
        }
      }
    }

    loadThumbnail();

    return () => {
      cancelled = true;

      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [image.id]);

  return (
    <div className="flex aspect-square items-center justify-center overflow-hidden rounded-lg bg-zinc-950">
      {url ? (
        <img
          src={url}
          alt={image.prompt}
          className="h-full w-full object-cover"
        />
      ) : failed ? (
        <span className="text-sm text-zinc-500">
          Preview unavailable
        </span>
      ) : (
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-700 border-t-blue-500" />
      )}
    </div>
  );
}

export default function ImageWorkspacePage() {
  const [prompt, setPrompt] = useState("");
  const [width, setWidth] = useState(512);
  const [height, setHeight] = useState(512);

  const [history, setHistory] = useState<ImageGeneration[]>([]);
  const [selectedImage, setSelectedImage] =
    useState<ImageGeneration | null>(null);

  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  const [loading, setLoading] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load generation history
  const loadHistory = useCallback(async () => {
    try {
      const token = getToken();

      if (!token || !API_URL) {
        setError("Please log in to use Image AI.");
        return;
      }

      const response = await fetch(
        `${API_URL}/images/history`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error(await getErrorMessage(response));
      }

      const data: ImageHistory = await response.json();

      setHistory(data.items);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load image history."
      );
    } finally {
      setLoadingHistory(false);
    }
  }, []);

  // Load a protected image using its authenticated endpoint
  const loadImage = useCallback(async (image: ImageGeneration) => {
    try {
      const token = getToken();

      if (!token || !API_URL) {
        throw new Error("Please log in again.");
      }

      const response = await fetch(
        `${API_URL}/images/${image.id}/file`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error(await getErrorMessage(response));
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);

      setSelectedImage(image);
      setPreviewUrl(url);
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load image."
      );
    }
  }, []);

  // Initial history loading
  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  // Revoke previous preview URLs to prevent memory leaks
  useEffect(() => {
    return () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  // Generate a new image
  const generateImage = async () => {
    if (prompt.trim().length < 3) {
      setError(
        "Please enter a prompt with at least 3 characters."
      );
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const token = getToken();

      if (!token || !API_URL) {
        throw new Error("Please log in again.");
      }

      const response = await fetch(
        `${API_URL}/images/generate`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            prompt: prompt.trim(),
            width,
            height,
          }),
        }
      );

      if (!response.ok) {
        throw new Error(await getErrorMessage(response));
      }

      const generated: ImageGeneration = await response.json();

      // Refresh history and display the generated image
      await loadHistory();
      await loadImage(generated);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Image generation failed."
      );
    } finally {
      setLoading(false);
    }
  };

  // Download the currently selected image
  const downloadImage = () => {
    if (!previewUrl || !selectedImage) {
      return;
    }

    const link = document.createElement("a");

    link.href = previewUrl;
    link.download = `omniai-${selectedImage.id}.png`;

    document.body.appendChild(link);
    link.click();
    link.remove();
  };

  return (
    <div className="space-y-8 pb-10">

      {/* Page heading */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">
          Image AI
        </h1>

        <p className="mt-2 text-sm text-zinc-500">
          Generate images from your imagination using AI.
        </p>
      </div>

      {/* Error message */}
      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
          {error}
        </div>
      )}

      <div className="grid gap-8 lg:grid-cols-[1fr_1.2fr]">

        {/* Image generation controls */}
        <section className="space-y-5 rounded-xl border border-zinc-800 bg-zinc-900/40 p-6">

          <div>
            <h2 className="text-lg font-semibold">
              Create an image
            </h2>

            <p className="mt-1 text-sm text-zinc-500">
              Describe what you want to generate.
            </p>
          </div>

          {/* Prompt */}
          <div>
            <label
              htmlFor="image-prompt"
              className="mb-2 block text-sm font-medium"
            >
              Image prompt
            </label>

            <textarea
              id="image-prompt"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="A futuristic city with flying cars, cinematic lighting..."
              rows={7}
              maxLength={2000}
              className="w-full resize-none rounded-lg border border-zinc-700 bg-zinc-950 p-4 text-sm outline-none transition focus:border-blue-500"
            />

            <p className="mt-2 text-right text-xs text-zinc-500">
              {prompt.length}/2000
            </p>
          </div>

          {/* Image dimensions */}
          <div className="grid grid-cols-2 gap-4">

            <div>
              <label
                htmlFor="image-width"
                className="mb-2 block text-sm font-medium"
              >
                Width
              </label>

              <select
                id="image-width"
                value={width}
                onChange={(e) =>
                  setWidth(Number(e.target.value))
                }
                className="w-full rounded-lg border border-zinc-700 bg-zinc-950 p-3 text-sm"
              >
                <option value={256}>256 px</option>
                <option value={512}>512 px</option>
                <option value={768}>768 px</option>
                <option value={1024}>1024 px</option>
              </select>
            </div>

            <div>
              <label
                htmlFor="image-height"
                className="mb-2 block text-sm font-medium"
              >
                Height
              </label>

              <select
                id="image-height"
                value={height}
                onChange={(e) =>
                  setHeight(Number(e.target.value))
                }
                className="w-full rounded-lg border border-zinc-700 bg-zinc-950 p-3 text-sm"
              >
                <option value={256}>256 px</option>
                <option value={512}>512 px</option>
                <option value={768}>768 px</option>
                <option value={1024}>1024 px</option>
              </select>
            </div>

          </div>

          {/* Generate button */}
          <button
            onClick={generateImage}
            disabled={loading || prompt.trim().length < 3}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-5 py-3 font-medium text-white transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? (
              <>
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                Generating...
              </>
            ) : (
              "Generate image"
            )}
          </button>

          <p className="text-center text-xs text-zinc-500">
            Development mode: using OmniAI mock image provider.
          </p>

        </section>

        {/* Image preview */}
        <section className="flex min-h-[420px] flex-col rounded-xl border border-zinc-800 bg-zinc-900/40 p-6">

          <div className="mb-5 flex items-center justify-between">
            <h2 className="text-lg font-semibold">
              Preview
            </h2>

            {selectedImage && (
              <button
                onClick={downloadImage}
                className="rounded-lg border border-zinc-700 px-4 py-2 text-sm transition hover:bg-zinc-800"
              >
                Download PNG
              </button>
            )}
          </div>

          <div className="flex flex-1 items-center justify-center overflow-hidden rounded-lg border border-dashed border-zinc-700 bg-zinc-950 p-4">

            {loading ? (
              <div className="text-center">
                <div className="mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-4 border-zinc-700 border-t-blue-500" />

                <p className="text-sm text-zinc-400">
                  Generating your image...
                </p>
              </div>
            ) : previewUrl ? (
              <img
                src={previewUrl}
                alt={selectedImage?.prompt || "Generated image"}
                className="max-h-[500px] max-w-full rounded-lg object-contain"
              />
            ) : (
              <div className="text-center">
                <div className="mb-3 text-5xl">
                  🎨
                </div>

                <p className="font-medium text-zinc-300">
                  Your image will appear here
                </p>

                <p className="mt-2 text-sm text-zinc-500">
                  Enter a prompt to get started.
                </p>
              </div>
            )}

          </div>

          {/* Selected image information */}
          {selectedImage && (
            <div className="mt-4 space-y-1">
              <p className="text-sm font-medium">
                {selectedImage.prompt}
              </p>

              <p className="text-xs text-zinc-500">
                {selectedImage.width} × {selectedImage.height}
                {" · "}
                {selectedImage.provider}
              </p>
            </div>
          )}

        </section>

      </div>

      {/* Generation history */}
      <section className="space-y-4">

        <div className="flex items-center justify-between">

          <div>
            <h2 className="text-xl font-semibold">
              Generation history
            </h2>

            <p className="mt-1 text-sm text-zinc-500">
              Your previously generated images.
            </p>
          </div>

          <button
            onClick={loadHistory}
            disabled={loadingHistory}
            className="rounded-lg border border-zinc-700 px-3 py-2 text-sm hover:bg-zinc-800 disabled:opacity-50"
          >
            {loadingHistory ? "Loading..." : "Refresh"}
          </button>

        </div>

        {/* Loading state */}
        {loadingHistory ? (
          <p className="text-sm text-zinc-500">
            Loading history...
          </p>
        ) : history.length === 0 ? (

          /* Empty state */
          <div className="rounded-xl border border-zinc-800 p-8 text-center text-sm text-zinc-500">
            No image generations yet.
          </div>

        ) : (

          /* Image history cards */
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">

            {history.map((image) => (

              <button
                key={image.id}
                onClick={() => loadImage(image)}
                className={`rounded-xl border p-3 text-left transition hover:border-blue-500 ${
                  selectedImage?.id === image.id
                    ? "border-blue-500 bg-blue-500/5"
                    : "border-zinc-800 bg-zinc-900/40"
                }`}
              >

                {/* Actual authenticated PNG thumbnail */}
                <HistoryThumbnail image={image} />

                <p className="mt-3 line-clamp-2 text-sm font-medium">
                  {image.prompt}
                </p>

                <p className="mt-2 text-xs text-zinc-500">
                  {image.width} × {image.height}
                </p>

                <p className="mt-1 text-xs text-zinc-500">
                  {new Date(
                    image.created_at
                  ).toLocaleDateString()}
                </p>

              </button>

            ))}

          </div>
        )}

      </section>

    </div>
  );
}
