export const API_CLIENT_PLACEHOLDER_REASON =
  "OpenAPI generation is not wired yet; this module marks the generated client destination.";

export interface ApiClientConfig {
  readonly baseUrl: string;
}

export interface ApiClient {
  readonly baseUrl: string;
  readonly generated: false;
}

export function createApiClient(config: ApiClientConfig): ApiClient {
  return {
    baseUrl: config.baseUrl,
    generated: false,
  };
}
