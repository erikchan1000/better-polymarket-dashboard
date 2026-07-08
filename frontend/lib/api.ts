import type { ApiError, DashboardResponse } from "./types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

export class DashboardApiError extends Error {
  kind: ApiError["kind"];
  status?: number;

  constructor(err: ApiError) {
    super(err.message);
    this.name = "DashboardApiError";
    this.kind = err.kind;
    this.status = err.status;
  }
}

export interface FetchDashboardOptions {
  /** Cap on trade/resolution records pulled for grouping. 0 (default) pulls
   *  the complete history by paging to the end of the feed. */
  maxActivities?: number;
  enrichEvents?: boolean;
  signal?: AbortSignal;
}

export async function fetchDashboard(
  options: FetchDashboardOptions = {},
): Promise<DashboardResponse> {
  const { maxActivities = 0, enrichEvents = true, signal } = options;
  const params = new URLSearchParams({
    max_activities: String(maxActivities),
    enrich_events: String(enrichEvents),
  });
  const url = `${API_BASE_URL}/api/dashboard?${params.toString()}`;

  let res: Response;
  try {
    res = await fetch(url, { signal, cache: "no-store" });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new DashboardApiError({
      kind: "network",
      message:
        `Could not reach the backend at ${API_BASE_URL}. ` +
        "Is the Python server running?",
    });
  }

  if (!res.ok) {
    // Try to decode the structured error body from the backend.
    let detail = res.statusText;
    let errorCode = "";
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
      errorCode = body.error ?? "";
    } catch {
      // non-JSON body; keep statusText
    }

    if (res.status === 503 && errorCode === "missing_credentials") {
      throw new DashboardApiError({
        kind: "missing_credentials",
        message: detail,
        status: 503,
      });
    }
    throw new DashboardApiError({
      kind: "upstream_error",
      message: detail,
      status: res.status,
    });
  }

  return (await res.json()) as DashboardResponse;
}

export { API_BASE_URL };
