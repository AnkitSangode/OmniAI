import { api } from "@/lib/api";
import type { AnalyticsDateRange, AnalyticsOverview } from "@/types/analytics";

export const analyticsService = {
  async getOverview(range?: Partial<AnalyticsDateRange>): Promise<AnalyticsOverview> {
    const response = await api.get<AnalyticsOverview>("/analytics/overview", {
      params: range,
    });

    return response.data;
  },
};
