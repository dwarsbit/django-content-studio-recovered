import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axios from "axios";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Devtools from "@/components/devtools/devtools";
import {
  type DevtoolsData,
  type DevtoolsIssue,
  installDevtools,
  reportBrowserIssue,
  resetDevtools,
  useDevtoolsState,
} from "@/lib/devtools";

const httpGetMock = vi.hoisted(() => vi.fn());
const httpDeleteMock = vi.hoisted(() => vi.fn());
const httpPostMock = vi.hoisted(() => vi.fn());

vi.mock("@/hooks/use-http", () => ({
  useHttp: () => ({
    get: httpGetMock,
    delete: httpDeleteMock,
    post: httpPostMock,
  }),
}));

function issue(overrides: Partial<DevtoolsIssue>): DevtoolsIssue {
  return {
    id: "1",
    level: "warning",
    code: "",
    title: "",
    message: "Something",
    hint: "",
    snippet: "",
    docs: "",
    studio: "",
    source: "server",
    stack: "",
    method: "",
    path: "",
    count: 1,
    first_seen: "2026-11-16T08:00:00Z",
    last_seen: "2026-11-16T08:00:00Z",
    ...overrides,
  };
}

function data(overrides: Partial<DevtoolsData> = {}): DevtoolsData {
  return {
    seq: 3,
    issues: [
      issue({
        id: "1",
        code: "slow_count",
        title: "Slow count on ArticleStudio",
        message: "Counting the list of ArticleStudio took 3.2 seconds.",
        snippet:
          'class ArticleStudio(ModelStudio):\n    list_count = "estimated"',
        docs: "https://djangocontentstudio.org/docs/list-page#large-tables",
        count: 3,
        last_seen: "2026-11-16T08:01:00Z",
      }),
      issue({
        id: "2",
        source: "check",
        code: "content_studio.W004",
        title: "System check content_studio.W004",
        message: "ArticleStudio.sortable_by contains 'reach'.",
      }),
    ],
    requests: [
      {
        id: "9",
        method: "GET",
        path: "content/blog.article/42",
        status: 200,
        ms: 212,
        time: "2026-11-16T08:01:00Z",
        queries: 27,
        query_ms: 164,
        slowest: [{ sql: 'SELECT * FROM "auth_user"', ms: 12 }],
        similar: [
          { sql: 'SELECT * FROM "auth_user" WHERE id = %s', count: 21 },
        ],
      },
    ],
    info: {
      environment: [
        { label: "Content Studio", value: "1.17.0" },
        { label: "Cache", value: "LocMemCache", code: true },
      ],
      studios: {
        "blog.article": {
          studio: "ArticleStudio",
          module: "blog.admin",
          list_count: "exact",
          list_per_page: 20,
        },
      },
    },
    ...overrides,
  };
}

function renderDevtools(path = "/content/blog.article") {
  const client = new QueryClient();

  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Devtools />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  resetDevtools();
  httpGetMock.mockReset();
  httpDeleteMock.mockReset();
  httpPostMock.mockReset();
  httpGetMock.mockResolvedValue({ data: data() });
  httpDeleteMock.mockResolvedValue({});
  httpPostMock.mockResolvedValue({});
});

afterEach(() => {
  resetDevtools();
});

describe("Developer tools", () => {
  it("shows nothing when the server has them off", async () => {
    httpGetMock.mockRejectedValue(new Error("404"));
    const { container } = renderDevtools();

    await waitFor(() => expect(httpGetMock).toHaveBeenCalled());

    expect(container).toBeEmptyDOMElement();
  });

  it("shows the number of issues, amber for warnings", async () => {
    renderDevtools();

    const button = await screen.findByRole("button", {
      name: "Developer tools, 2 warnings",
    });
    const count = within(button).getByText("2");

    expect(count).toHaveAttribute("data-level", "warning");
  });

  it("turns the count red with an error and lists browser issues", async () => {
    renderDevtools();
    await screen.findByRole("button", { name: /Developer tools/ });

    reportBrowserIssue({
      level: "error",
      title: "Uncaught error",
      message: "x is undefined",
    });

    const button = await screen.findByRole("button", {
      name: "Developer tools, 1 error, 2 warnings",
    });

    expect(within(button).getByText("3")).toHaveAttribute(
      "data-level",
      "error",
    );
  });

  it("opens the issues, filters them and expands one", async () => {
    const user = userEvent.setup();
    renderDevtools();

    await user.click(
      await screen.findByRole("button", { name: /Developer tools/ }),
    );

    const panel = screen.getByRole("region", { name: "Developer tools" });
    expect(
      within(panel).getByText("Slow count on ArticleStudio"),
    ).toBeVisible();
    expect(within(panel).getByText("system check")).toBeVisible();

    await user.click(within(panel).getByRole("button", { name: /Errors/ }));
    expect(
      within(panel).queryByText("Slow count on ArticleStudio"),
    ).not.toBeInTheDocument();

    await user.click(within(panel).getByRole("button", { name: /All/ }));
    await user.click(
      within(panel).getByRole("button", {
        name: /Slow count on ArticleStudio/,
      }),
    );

    expect(within(panel).getByText(/list_count = "estimated"/)).toBeVisible();
    expect(within(panel).getByText(/Seen 3 times/)).toBeVisible();
    expect(within(panel).getByRole("link", { name: /Docs/ })).toHaveAttribute(
      "href",
      "https://djangocontentstudio.org/docs/list-page#large-tables",
    );
  });

  it("clears the issues", async () => {
    const user = userEvent.setup();
    renderDevtools();

    await user.click(
      await screen.findByRole("button", { name: /Developer tools/ }),
    );
    await user.click(screen.getByRole("button", { name: "Clear" }));

    expect(httpDeleteMock).toHaveBeenCalledWith("/devtools/issues");
  });

  it("lists the requests with their queries", async () => {
    const user = userEvent.setup();
    renderDevtools();

    await user.click(
      await screen.findByRole("button", { name: /Developer tools/ }),
    );
    await user.click(screen.getByRole("tab", { name: /Requests/ }));
    await user.click(
      screen.getByRole("button", {
        name: "GET content/blog.article/42, 200, 212 ms, 27 queries",
      }),
    );

    expect(screen.getByText(/21 of them alike/)).toBeVisible();
    expect(
      screen.getByText(/select_related or prefetch_related/),
    ).toBeVisible();
  });

  it("shows this page's studio and the environment", async () => {
    const user = userEvent.setup();
    renderDevtools();

    await user.click(
      await screen.findByRole("button", { name: /Developer tools/ }),
    );
    await user.click(screen.getByRole("tab", { name: "Info" }));

    expect(screen.getByText("ArticleStudio")).toBeVisible();
    expect(screen.getByText('"exact"')).toBeVisible();
    expect(screen.getByText("LocMemCache")).toBeVisible();

    await user.click(screen.getByRole("button", { name: /Run system checks/ }));

    expect(httpPostMock).toHaveBeenCalledWith("/devtools/checks");
  });

  it("hides until the page reloads", async () => {
    const user = userEvent.setup();
    const { container } = renderDevtools();

    await user.click(
      await screen.findByRole("button", { name: /Developer tools/ }),
    );
    await user.click(
      screen.getByRole("button", {
        name: "Hide the button until the page reloads",
      }),
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("closes with Escape", async () => {
    const user = userEvent.setup();
    renderDevtools();

    await user.click(
      await screen.findByRole("button", { name: /Developer tools/ }),
    );
    await user.click(screen.getByRole("tab", { name: "Info" }));
    await user.keyboard("{Escape}");

    expect(
      screen.queryByRole("region", { name: "Developer tools" }),
    ).not.toBeInTheDocument();
  });

  it("refetches when the server announces new issues", async () => {
    renderDevtools();
    await screen.findByRole("button", { name: /Developer tools/ });
    expect(httpGetMock).toHaveBeenCalledTimes(1);

    const http = axios.create();
    installDevtools(http);
    http.defaults.adapter = async (config) => ({
      data: {},
      status: 200,
      statusText: "OK",
      headers: { "x-content-studio-devtools": "4" },
      config,
    });
    await http.get("/me");

    await waitFor(() => expect(httpGetMock).toHaveBeenCalledTimes(2));
  });
});

describe("The response watcher", () => {
  function Probe() {
    const state = useDevtoolsState();

    return (
      <ul>
        {state.issues.map((item) => (
          <li key={item.id}>{item.message}</li>
        ))}
      </ul>
    );
  }

  it("reports failures the server could not report", async () => {
    const http = axios.create();
    installDevtools(http);
    http.defaults.adapter = async (config) => {
      if (config.url === "/down") {
        throw new axios.AxiosError("Network Error", "ERR_NETWORK", config);
      }

      throw new axios.AxiosError(
        "Bad gateway",
        "ERR_BAD_RESPONSE",
        config,
        null,
        {
          data: "",
          status: 502,
          statusText: "Bad Gateway",
          headers: {},
          config,
        },
      );
    };

    render(<Probe />);

    await expect(http.get("/down")).rejects.toThrow();
    await expect(http.get("/proxy")).rejects.toThrow();

    expect(
      await screen.findByText("GET /down: Network Error"),
    ).toBeInTheDocument();
    expect(screen.getByText("GET /proxy returned 502.")).toBeInTheDocument();
  });

  it("leaves server errors the server counted to the server", async () => {
    const http = axios.create();
    installDevtools(http);
    http.defaults.adapter = async (config) => {
      throw new axios.AxiosError(
        "Server error",
        "ERR_BAD_RESPONSE",
        config,
        null,
        {
          data: "",
          status: 500,
          statusText: "Internal Server Error",
          headers: { "x-content-studio-devtools": "7" },
          config,
        },
      );
    };

    const { container } = render(<Probe />);

    await expect(http.get("/content")).rejects.toThrow();

    expect(container.querySelectorAll("li")).toHaveLength(0);
  });
});
