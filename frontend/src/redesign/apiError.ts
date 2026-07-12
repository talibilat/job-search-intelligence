export function publicApiError(error: unknown, fallback: string): string {
  if (typeof error !== "object" || error === null || !("response" in error)) return fallback;
  const response = (error as { response?: unknown }).response;
  if (typeof response !== "object" || response === null || !("data" in response)) return fallback;
  const data = (response as { data?: unknown }).data;
  if (typeof data !== "object" || data === null || !("error" in data)) return fallback;
  const body = (data as { error?: unknown }).error;
  if (typeof body !== "object" || body === null || !("message" in body)) return fallback;
  return typeof (body as { message?: unknown }).message === "string"
    ? (body as { message: string }).message
    : fallback;
}
