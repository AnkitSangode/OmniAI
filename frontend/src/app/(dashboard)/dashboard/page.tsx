"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Activity,
  AudioLines,
  CalendarDays,
  CheckCircle2,
  Clock3,
  Coins,
  Image as ImageIcon,
  MessageSquare,
  Mic,
  RefreshCw,
  Sparkles,
  Video,
  XCircle,
  Zap,
} from "lucide-react";

import { analyticsService } from "@/services/analytics.service";
import type {
  AnalyticsModality,
  AnalyticsOverview,
  DailyUsage,
} from "@/types/analytics";

const modalityMeta: Record<AnalyticsModality, { label: string; icon: typeof MessageSquare; color: string }> = {
  text: { label: "Text", icon: MessageSquare, color: "bg-sky-400" },
  image: { label: "Image", icon: ImageIcon, color: "bg-violet-400" },
  audio: { label: "Audio", icon: AudioLines, color: "bg-emerald-400" },
  video: { label: "Video", icon: Video, color: "bg-orange-400" },
  other: { label: "Other", icon: Activity, color: "bg-zinc-400" },
};

function toDateInputValue(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function getRange(days: number) {
  const end = new Date();
  const start = new Date(end);
  start.setDate(start.getDate() - (days - 1));
  return { start_date: toDateInputValue(start), end_date: toDateInputValue(end) };
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}

function formatCurrency(value: number | null) {
  if (value === null) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 4,
  }).format(value);
}

function formatLatency(value: number) {
  if (!Number.isFinite(value)) return "—";
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${Math.round(value)} ms`;
}

function formatDay(value: string, compact = false) {
  const date = new Date(`${value}T00:00:00`);
  return new Intl.DateTimeFormat("en-US", compact
    ? { month: "short", day: "numeric" }
    : { weekday: "short", month: "short", day: "numeric" }).format(date);
}

function MetricCard({
  label,
  value,
  detail,
  icon: Icon,
}: {
  label: string;
  value: string;
  detail: string;
  icon: typeof Activity;
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-[#111116] p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm text-zinc-400">{label}</p>
          <p className="mt-3 text-2xl font-semibold tracking-tight text-white">{value}</p>
          <p className="mt-2 text-xs text-zinc-500">{detail}</p>
        </div>
        <div className="rounded-xl border border-white/10 bg-white/4 p-2.5 text-violet-300">
          <Icon size={19} />
        </div>
      </div>
    </div>
  );
}

function UsageChart({ daily }: { daily: DailyUsage[] }) {
  const width = 720;
  const height = 230;
  const padding = { top: 18, right: 18, bottom: 34, left: 34 };
  const values = daily.map((item) => item.requests);
  const maxValue = Math.max(...values, 1);
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const points = daily.map((item, index) => {
    const x = padding.left + (daily.length <= 1 ? chartWidth / 2 : (index / (daily.length - 1)) * chartWidth);
    const y = padding.top + chartHeight - (item.requests / maxValue) * chartHeight;
    return { x, y, item };
  });
  const line = points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");
  const area = points.length
    ? `${line} L ${points[points.length - 1].x} ${padding.top + chartHeight} L ${points[0].x} ${padding.top + chartHeight} Z`
    : "";
  const labelIndexes = daily.length <= 7
    ? daily.map((_, index) => index)
    : [0, Math.floor((daily.length - 1) / 3), Math.floor(((daily.length - 1) * 2) / 3), daily.length - 1];

  if (!daily.length) {
    return <div className="flex h-56 items-center justify-center text-sm text-zinc-500">No usage recorded for this period yet.</div>;
  }

  return (
    <div className="w-full">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Daily request volume" className="h-56 w-full overflow-visible">
        {[0, 1, 2, 3].map((step) => {
          const y = padding.top + (chartHeight / 3) * step;
          return <g key={step}>
            <line x1={padding.left} x2={width - padding.right} y1={y} y2={y} stroke="rgba(255,255,255,0.08)" strokeDasharray="4 6" />
            <text x={padding.left - 10} y={y + 4} fill="#71717a" fontSize="10" textAnchor="end">{Math.round(maxValue * (1 - step / 3))}</text>
          </g>;
        })}
        <defs>
          <linearGradient id="usage-area-gradient" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#8b5cf6" stopOpacity="0.28" />
            <stop offset="100%" stopColor="#8b5cf6" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={area} fill="url(#usage-area-gradient)" />
        <path d={line} fill="none" stroke="#a78bfa" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        {points.map((point, index) => <circle key={`${point.item.day}-${index}`} cx={point.x} cy={point.y} r="3.5" fill="#c4b5fd" stroke="#18181b" strokeWidth="2" />)}
        {labelIndexes.map((index) => {
          const point = points[index];
          if (!point) return null;
          return <text key={point.item.day} x={point.x} y={height - 8} fill="#71717a" fontSize="10" textAnchor={index === 0 ? "start" : index === points.length - 1 ? "end" : "middle"}>{formatDay(point.item.day, true)}</text>;
        })}
      </svg>
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="h-8 w-56 rounded-lg bg-white/10" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[1, 2, 3, 4].map((item) => <div key={item} className="h-32 rounded-2xl border border-white/10 bg-white/3" />)}</div>
      <div className="h-80 rounded-2xl border border-white/10 bg-white/3" />
    </div>
  );
}

export default function DashboardPage() {
  const [data, setData] = useState<AnalyticsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [preset, setPreset] = useState("30");
  const [startDate, setStartDate] = useState(() => getRange(30).start_date);
  const [endDate, setEndDate] = useState(() => getRange(30).end_date);
  const [appliedRange, setAppliedRange] = useState(() => getRange(30));

  const loadOverview = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await analyticsService.getOverview(appliedRange);
      setData(result);
    } catch (err) {
      console.error("Failed to load analytics overview:", err);
      setError("We couldn't load your analytics right now. Please check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }, [appliedRange]);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  const maxModalityRequests = useMemo(
    () => Math.max(...(data?.by_modality.map((item) => item.requests) ?? [0]), 1),
    [data],
  );

  const handlePreset = (days: number) => {
    const range = getRange(days);
    setPreset(String(days));
    setStartDate(range.start_date);
    setEndDate(range.end_date);
    setAppliedRange(range);
  };

  const applyCustomRange = () => {
    if (!startDate || !endDate || startDate > endDate) {
      setError("Choose a valid date range. The start date must be on or before the end date.");
      return;
    }
    setPreset("custom");
    setAppliedRange({ start_date: startDate, end_date: endDate });
  };

  const summary = data?.summary;

  if (loading && !data) return <DashboardSkeleton />;

  return (
    <div className="mx-auto max-w-7xl space-y-8">
      <section className="flex flex-col justify-between gap-5 lg:flex-row lg:items-end">
        <div>
          <div className="mb-3 flex items-center gap-2 text-sm font-medium text-violet-300">
            <Sparkles size={16} /> OmniAI workspace
          </div>
          <h1 className="text-3xl font-semibold tracking-tight text-white">Overview</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-400">
            Monitor your AI activity, usage patterns, performance and estimated spend from one place.
          </p>
        </div>
        <button onClick={() => void loadOverview()} disabled={loading} className="inline-flex h-10 items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/4 px-4 text-sm font-medium text-zinc-200 transition hover:bg-white/8 disabled:cursor-not-allowed disabled:opacity-50">
          <RefreshCw size={15} className={loading ? "animate-spin" : ""} /> Refresh data
        </button>
      </section>

      <section className="flex flex-col gap-3 rounded-2xl border border-white/10 bg-[#111116] p-4 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex items-center gap-2 text-sm text-zinc-300"><CalendarDays size={16} className="text-violet-300" /> Date range</div>
        <div className="flex flex-wrap items-center gap-2">
          {[7, 30, 90].map((days) => <button key={days} onClick={() => handlePreset(days)} className={`rounded-lg px-3 py-2 text-xs font-medium transition ${preset === String(days) ? "bg-violet-500/20 text-violet-200 ring-1 ring-violet-400/30" : "text-zinc-400 hover:bg-white/6 hover:text-white"}`}>Last {days} days</button>)}
          <div className="hidden h-7 w-px bg-white/10 sm:block" />
          <label className="flex items-center gap-2 text-xs text-zinc-500">From <input type="date" value={startDate} max={endDate || undefined} onChange={(event) => { setStartDate(event.target.value); setPreset("custom"); }} className="rounded-lg border border-white/10 bg-[#09090b] px-2 py-2 text-xs text-zinc-200 outline-none focus:border-violet-400/60" /></label>
          <label className="flex items-center gap-2 text-xs text-zinc-500">To <input type="date" value={endDate} min={startDate || undefined} onChange={(event) => { setEndDate(event.target.value); setPreset("custom"); }} className="rounded-lg border border-white/10 bg-[#09090b] px-2 py-2 text-xs text-zinc-200 outline-none focus:border-violet-400/60" /></label>
          <button onClick={applyCustomRange} className="rounded-lg bg-violet-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-violet-500">Apply</button>
        </div>
      </section>

      {error && <div role="alert" className="flex flex-col gap-3 rounded-xl border border-red-400/20 bg-red-400/6 p-4 text-sm text-red-200 sm:flex-row sm:items-center sm:justify-between"><span>{error}</span><button onClick={() => void loadOverview()} className="font-medium underline underline-offset-4">Try again</button></div>}

      {loading && data && <p className="text-xs text-zinc-500">Refreshing analytics…</p>}

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Total requests" value={formatNumber(summary?.total_requests ?? 0)} detail={`${formatNumber(summary?.successful_requests ?? 0)} successful requests`} icon={Activity} />
        <MetricCard label="Estimated cost" value={formatCurrency(summary?.estimated_cost_usd ?? null)} detail={`${formatNumber(summary?.requests_without_cost ?? 0)} successful requests without pricing`} icon={Coins} />
        <MetricCard label="Total tokens" value={formatNumber(summary?.total_tokens ?? 0)} detail="Across tracked text requests" icon={Zap} />
        <MetricCard label="Average latency" value={formatLatency(summary?.average_latency_ms ?? 0)} detail="Average processing time per request" icon={Clock3} />
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.65fr_1fr]">
        <div className="rounded-2xl border border-white/10 bg-[#111116] p-5 sm:p-6">
          <div className="mb-6 flex items-start justify-between gap-3">
            <div><h2 className="font-semibold text-white">Usage over time</h2><p className="mt-1 text-xs text-zinc-500">Daily request volume for the selected period</p></div>
            <span className="rounded-lg bg-violet-400/10 px-2.5 py-1.5 text-xs font-medium text-violet-200">Requests / day</span>
          </div>
          <UsageChart daily={data?.daily ?? []} />
        </div>

        <div className="rounded-2xl border border-white/10 bg-[#111116] p-5 sm:p-6">
          <div className="mb-6"><h2 className="font-semibold text-white">By modality</h2><p className="mt-1 text-xs text-zinc-500">How your requests are distributed</p></div>
          {data?.by_modality.length ? <div className="space-y-5">{data.by_modality.map((item) => {
            const meta = modalityMeta[item.modality];
            const Icon = meta.icon;
            const percentage = (item.requests / maxModalityRequests) * 100;
            return <div key={item.modality}>
              <div className="mb-2 flex items-center justify-between gap-3"><div className="flex items-center gap-2 text-sm text-zinc-300"><Icon size={15} className="text-zinc-400" />{meta.label}</div><span className="text-sm font-medium tabular-nums text-white">{formatNumber(item.requests)}</span></div>
              <div className="h-2 overflow-hidden rounded-full bg-white/[0.07]"><div className={`h-full rounded-full ${meta.color} transition-all`} style={{ width: `${percentage}%` }} /></div>
              <div className="mt-1.5 flex justify-between text-[11px] text-zinc-500"><span>{item.successful_requests} successful · {item.failed_requests} failed</span><span>{formatLatency(item.average_latency_ms)}</span></div>
            </div>;
          })}</div> : <div className="flex h-48 items-center justify-center text-sm text-zinc-500">No modality usage yet.</div>}
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[1fr_1fr]">
        <div className="rounded-2xl border border-white/10 bg-[#111116] p-5 sm:p-6">
          <div className="mb-5"><h2 className="font-semibold text-white">Request health</h2><p className="mt-1 text-xs text-zinc-500">Success and failure across all tracked requests</p></div>
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-xl border border-emerald-400/15 bg-emerald-400/5 p-4"><CheckCircle2 size={18} className="text-emerald-300" /><p className="mt-3 text-2xl font-semibold text-white">{formatNumber(summary?.successful_requests ?? 0)}</p><p className="mt-1 text-xs text-zinc-400">Successful</p></div>
            <div className="rounded-xl border border-red-400/15 bg-red-400/5 p-4"><XCircle size={18} className="text-red-300" /><p className="mt-3 text-2xl font-semibold text-white">{formatNumber(summary?.failed_requests ?? 0)}</p><p className="mt-1 text-xs text-zinc-400">Failed</p></div>
          </div>
          <div className="mt-5 flex items-center justify-between text-sm"><span className="text-zinc-400">Success rate</span><span className="font-semibold text-white">{(summary?.success_rate ?? 0).toFixed(1)}%</span></div>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-white/[0.07]"><div className="h-full rounded-full bg-emerald-400 transition-all" style={{ width: `${Math.min(Math.max(summary?.success_rate ?? 0, 0), 100)}%` }} /></div>
        </div>

        <div className="rounded-2xl border border-white/10 bg-[#111116] p-5 sm:p-6">
          <div className="mb-5"><h2 className="font-semibold text-white">Model usage</h2><p className="mt-1 text-xs text-zinc-500">Requests grouped by model identifier</p></div>
          {data?.by_model.length ? <div className="divide-y divide-white/[0.07]">{data.by_model.slice(0, 5).map((item) => <div key={item.model} className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0"><div className="min-w-0"><p className="truncate text-sm font-medium text-zinc-200">{item.model}</p><p className="mt-1 text-xs text-zinc-500">{formatNumber(item.total_tokens)} tokens</p></div><div className="shrink-0 text-right"><p className="text-sm font-semibold text-white">{formatNumber(item.requests)}</p><p className="mt-1 text-xs text-zinc-500">{formatCurrency(item.estimated_cost_usd)}</p></div></div>)}</div> : <div className="flex h-36 items-center justify-center text-sm text-zinc-500">No model usage yet.</div>}
        </div>
      </section>

      <section className="rounded-2xl border border-violet-400/15 bg-linear-to-br from-violet-500/10 via-[#111116] to-[#111116] p-5 sm:p-6">
        <div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-center">
          <div><div className="flex items-center gap-2 text-sm font-medium text-violet-200"><Sparkles size={16} /> Your AI workspace</div><h2 className="mt-2 text-lg font-semibold text-white">What would you like to create today?</h2><p className="mt-1 text-sm text-zinc-400">Jump back into one of your multimodal tools.</p></div>
          <div className="flex flex-wrap gap-2">
            <Link href="/text" className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.05] px-3 py-2 text-xs font-medium text-zinc-200 hover:bg-white/10"><MessageSquare size={14} /> Text</Link>
            <Link href="/image" className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs font-medium text-zinc-200 hover:bg-white/10"><ImageIcon size={14} /> Image</Link>
            <Link href="/audio" className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs font-medium text-zinc-200 hover:bg-white/10"><Mic size={14} /> Audio</Link>
            <Link href="/video" className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs font-medium text-zinc-200 hover:bg-white/10"><Video size={14} /> Video</Link>
          </div>
        </div>
      </section>
    </div>
  );
}
