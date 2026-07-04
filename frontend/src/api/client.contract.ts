import {
  API_CLIENT_PLACEHOLDER_REASON,
  createApiClient,
  type ApiClient,
  type ApiClientConfig,
} from "./index";

const config: ApiClientConfig = {
  baseUrl: "http://localhost:8000",
};

const client: ApiClient = createApiClient(config);

export const apiClientBoundaryContract = {
  baseUrl: client.baseUrl,
  generated: client.generated,
  reason: API_CLIENT_PLACEHOLDER_REASON,
} as const;
