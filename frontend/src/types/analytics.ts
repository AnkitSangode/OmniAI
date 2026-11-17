export type AnalyticsModality = "text" | "image" | "audio" | "video" | "other";

export interface AnalyticsSummary {
  total_requests: number;
  successful_requests: number;
  failed_requests: number;
  success_rate: number;
  total_tokens: number;
  estimated_cost_usd: number | null;
  requests_without_cost: number;
  average_latency_ms: number;
}

export interface ModalityBreakdown {
  modality: AnalyticsModality;
  requests: number;
  successful_requests: number;
  failed_requests: number;
  total_tokens: number;
  estimated_cost_usd: number | null;
  average_latency_ms: number;
}

export interface ModelBreakdown {
  model: string;
  requests: number;
  total_tokens: number;
  estimated_cost_usd: number | null;
  average_latency_ms: number;
}

export interface DailyUsage {
  day: string;
  requests: number;
  total_tokens: number;
  estimated_cost_usd: number | null;
}

export interface AnalyticsOverview {
  start_date: string;
  end_date: string;
  summary: AnalyticsSummary;
  by_modality: ModalityBreakdown[];
  by_model: ModelBreakdown[];
  daily: DailyUsage[];
}

export interface AnalyticsDateRange {
  start_date: string;
  end_date: string;
}
