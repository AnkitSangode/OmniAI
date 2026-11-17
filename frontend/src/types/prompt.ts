export type Prompt = {
  id: string;
  name: string;
  description: string | null;
  current_version: number;
  created_at: string;
  updated_at: string;
};

export type PromptVersion = {
  id: string;
  prompt_id: string;
  version_number: number;
  content: string;
  created_at: string;
};

export type PromptDetail = Prompt & {
  latest_version: PromptVersion;
};

export type PromptListResponse = {
  items: Prompt[];
  total: number;
  limit: number;
  offset: number;
};

export type PromptPayload = {
  name: string;
  description: string | null;
  content: string;
};
