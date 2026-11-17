import { api } from "@/lib/api";
import type {
  PromptDetail,
  PromptListResponse,
  PromptPayload,
  PromptVersion,
} from "@/types/prompt";

export const promptService = {
  async list(limit = 100, offset = 0) {
    const response = await api.get<PromptListResponse>("/prompts", {
      params: { limit, offset },
    });
    return response.data;
  },

  async get(promptId: string) {
    const response = await api.get<PromptDetail>(`/prompts/${promptId}`);
    return response.data;
  },

  async create(payload: PromptPayload) {
    const response = await api.post<PromptDetail>("/prompts", payload);
    return response.data;
  },

  async update(promptId: string, payload: PromptPayload) {
    const response = await api.put<PromptDetail>(`/prompts/${promptId}`, payload);
    return response.data;
  },

  async listVersions(promptId: string) {
    const response = await api.get<PromptVersion[]>(`/prompts/${promptId}/versions`);
    return response.data;
  },

  async getVersion(promptId: string, versionNumber: number) {
    const response = await api.get<PromptVersion>(
      `/prompts/${promptId}/versions/${versionNumber}`
    );
    return response.data;
  },
};
