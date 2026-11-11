
import Link from "next/link";
import {
  MessageSquare,
  Image as ImageIcon,
  Mic,
  Video,
  ArrowUpRight,
  Sparkles,
} from "lucide-react";

const tools = [
  {
    title: "Text AI",
    description: "Generate, summarize and interact with language models.",
    href: "/text",
    icon: MessageSquare,
    color: "bg-blue-500/10 text-blue-400",
  },
  {
    title: "Image AI",
    description: "Create images from natural language prompts.",
    href: "/image",
    icon: ImageIcon,
    color: "bg-purple-500/10 text-purple-400",
  },
  {
    title: "Audio AI",
    description: "Transcribe speech and generate natural audio.",
    href: "/audio",
    icon: Mic,
    color: "bg-emerald-500/10 text-emerald-400",
  },
  {
    title: "Video AI",
    description: "Analyze videos, generate transcripts and summaries.",
    href: "/video",
    icon: Video,
    color: "bg-orange-500/10 text-orange-400",
  },
];

export default function DashboardPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <section>
        <div className="mb-3 flex items-center gap-2 text-sm text-blue-400">
          <Sparkles size={16} />
          AI Workspace
        </div>

        <h1 className="text-3xl font-bold tracking-tight">
          Welcome to OmniAI
        </h1>

        <p className="mt-2 text-zinc-400">
          One platform. Multiple AI capabilities. One unified workspace.
        </p>
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        {tools.map((tool) => {
          const Icon = tool.icon;

          return (
            <Link
              key={tool.title}
              href={tool.href}
              className="group rounded-2xl border border-zinc-800 bg-zinc-900/60 p-6 transition hover:border-zinc-600 hover:bg-zinc-900"
            >
              <div className="mb-5 flex items-center justify-between">
                <div className={`rounded-xl p-3 ${tool.color}`}>
                  <Icon size={24} />
                </div>

                <ArrowUpRight
                  size={20}
                  className="text-zinc-600 transition group-hover:text-white"
                />
              </div>

              <h2 className="text-lg font-semibold">{tool.title}</h2>

              <p className="mt-2 text-sm leading-6 text-zinc-400">
                {tool.description}
              </p>

              <span className="mt-5 inline-block text-sm font-medium text-blue-400">
                Open workspace →
              </span>
            </Link>
          );
        })}
      </section>

      <section className="rounded-2xl border border-zinc-800 bg-linear-to-br from-blue-950/40 to-zinc-900 p-6">
        <h2 className="text-lg font-semibold">Your AI workspace</h2>
        <p className="mt-2 text-sm text-zinc-400">
          Access text generation, image creation, audio processing and
          video intelligence from one place.
        </p>
      </section>
    </div>
  );
}
