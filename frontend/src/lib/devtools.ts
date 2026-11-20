import axios, { AxiosHeaders, type AxiosInstance } from "axios";
import { useSyncExternalStore } from "react";

/**
 * The developer tools' state in the browser: the issues the browser
 * saw itself (failed requests, uncaught errors), the latest change
 * number the server announced, and whether the button shows. Only used
 * while the developer tools are on (DEBUG).
 */

export const DEVTOOLS_HEADER = "x-content-studio-devtools";

export type DevtoolsLevel = "error" | "warning" | "info";

export interface DevtoolsIssue {
  id: string;
  level: DevtoolsLevel;
  code: string;
  title: string;
  message: string;
  hint: string;
  snippet: string;
  docs: string;
  studio: string;
  source: "check" | "log" | "server" | "report" | "browser";
  stack: string;
  method: string;
  path: string;
  count: number;
  first_seen: string;
  last_seen: string;
}

export interface DevtoolsRequest {
  id: string;
  method: string;
  path: string;
  status: number;
  ms: number;
  time: string;
  queries: number;
  query_ms: number;
  slowest: { sql: string; ms: number }[];
  similar: { sql: string; count: number }[];
}

export interface DevtoolsInfo {
  environment: { label: string; value: string; code?: boolean }[];
  studios: Record<
    string,
    {
      studio: string;
      module: string;
      list_count: string;
      list_per_page: number | null;
    }
  >;
}

export interface DevtoolsData {
  seq: number;
  issues: DevtoolsIssue[];
  requests: DevtoolsRequest[];
  info: DevtoolsInfo;
}

/** On under the vite dev server, or when discover says the server has them on. */
export function isDevtoolsEnabled(serverEnabled: boolean | undefined) {
  return serverEnabled === true || import.meta.env.DEV;
}

interface State {
  issues: DevtoolsIssue[];
  seq: number;
  // Bumped after every API response, so an open panel can refresh
  // its requests.
  responses: number;
  visible: boolean;
}

let state: State = { issues: [], seq: -1, responses: 0, visible: false };
const listeners = new Set<() => void>();
let nextId = 1;

function setState(patch: Partial<State>) {
  state = { ...state, ...patch };
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);

  return () => {
    listeners.delete(listener);
  };
}

export function useDevtoolsState() {
  return useSyncExternalStore(subscribe, () => state);
}

/** Whether the button shows: toasts then sit above it. */
export function useDevtoolsVisible() {
  return useSyncExternalStore(subscribe, () => state.visible);
}

export function setDevtoolsVisible(visible: boolean) {
  if (state.visible !== visible) {
    setState({ visible });
  }
}

/** Adds an issue seen in the browser; repeats are counted. */
export function reportBrowserIssue(
  issue: Pick<DevtoolsIssue, "level" | "title" | "message"> &
    Partial<DevtoolsIssue>,
) {
  const now = new Date().toISOString();
  const key = `${issue.title}:${issue.message}`;
  const existing = state.issues.find(
    (item) => `${item.title}:${item.message}` === key,
  );

  if (existing) {
    setState({
      issues: [
        { ...existing, count: existing.count + 1, last_seen: now },
        ...state.issues.filter((item) => item !== existing),
      ],
    });
    return;
  }

  const added: DevtoolsIssue = {
    id: `browser-${nextId++}`,
    code: "",
    hint: "",
    snippet: "",
    docs: "",
    studio: "",
    stack: "",
    method: "",
    path: "",
    source: "browser",
    count: 1,
    first_seen: now,
    last_seen: now,
    ...issue,
  };

  // The newest 100 are kept.
  setState({ issues: [added, ...state.issues].slice(0, 100) });
}

export function clearBrowserIssues() {
  setState({ issues: [] });
}

function readSeq(headers: unknown): number | null {
  const value = AxiosHeaders.from(headers as Record<string, string>).get(
    DEVTOOLS_HEADER,
  );

  if (value === null || value === undefined || value === "") {
    return null;
  }

  const seq = Number(value);

  return Number.isFinite(seq) ? seq : null;
}

function noteResponse(headers: unknown, url = "") {
  const seq = readSeq(headers);
  // The developer tools' own requests are not recorded, so they do
  // not count as new responses either.
  const own = url.replace(/^\//, "").startsWith("devtools");

  if (own && (seq === null || seq === state.seq)) {
    return seq;
  }

  setState({
    ...(own ? {} : { responses: state.responses + 1 }),
    ...(seq !== null && seq !== state.seq ? { seq } : {}),
  });

  return seq;
}

let installed: AxiosInstance | null = null;

/**
 * Watches the admin API's responses: the server's change number, and
 * failures the server could not report itself (it was unreachable, or
 * a proxy answered).
 */
export function installDevtools(http: AxiosInstance) {
  if (installed === http) {
    return;
  }

  installed = http;

  http.interceptors.response.use(
    (response) => {
      noteResponse(response.headers, response.config?.url);
      return response;
    },
    (error: unknown) => {
      if (axios.isAxiosError(error) && !axios.isCancel(error)) {
        const method = (error.config?.method ?? "get").toUpperCase();
        const path = error.config?.url ?? "";

        if (!error.response) {
          reportBrowserIssue({
            level: "error",
            title: "Request failed",
            message: `${method} ${path}: ${error.message}`,
            code: "network",
            method,
            path,
          });
        } else {
          const seq = noteResponse(error.response.headers, path);

          // A server error the server did not count (no header): a
          // proxy or another server answered.
          if (error.response.status >= 500 && seq === null) {
            reportBrowserIssue({
              level: "error",
              title: "Request failed",
              message: `${method} ${path} returned ${error.response.status}.`,
              code: String(error.response.status),
              method,
              path,
            });
          }
        }
      }

      return Promise.reject(error);
    },
  );

  window.addEventListener("error", (event) => {
    reportBrowserIssue({
      level: "error",
      title: "Uncaught error",
      message: event.message || String(event.error),
      code: "browser",
      stack: event.error instanceof Error ? (event.error.stack ?? "") : "",
    });
  });

  window.addEventListener("unhandledrejection", (event) => {
    const reason: unknown = event.reason;

    // Failed requests are reported above.
    if (axios.isAxiosError(reason) || axios.isCancel(reason)) {
      return;
    }

    reportBrowserIssue({
      level: "error",
      title: "Unhandled promise rejection",
      message: reason instanceof Error ? reason.message : String(reason),
      code: "browser",
      stack: reason instanceof Error ? (reason.stack ?? "") : "",
    });
  });
}

/** For tests: forget everything. */
export function resetDevtools() {
  state = { issues: [], seq: -1, responses: 0, visible: false };
  installed = null;
  listeners.forEach((listener) => listener());
}
