import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  PiArrowsClockwiseBold,
  PiArrowSquareOutBold,
  PiCaretRightBold,
  PiCheckBold,
  PiCodeBold,
  PiCopyBold,
  PiEyeSlashBold,
  PiInfoBold,
  PiTrashBold,
  PiWarningBold,
  PiXBold,
  PiXCircleBold,
} from "react-icons/pi";
import { Link, useMatch } from "react-router";

import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useHttp } from "@/hooks/use-http";
import {
  clearBrowserIssues,
  type DevtoolsData,
  type DevtoolsInfo,
  type DevtoolsIssue,
  type DevtoolsLevel,
  type DevtoolsRequest,
  setDevtoolsVisible,
  useDevtoolsState,
} from "@/lib/devtools";
import { cn } from "@/lib/utils";

/*
 * The developer tools: a button in the bottom-right corner with the
 * number of issues, and a panel with the issues, the recent requests to
 * the admin API and the environment. Shown while DEBUG is on only, in
 * English only: it is for the developer running the project.
 */

const DOCS_URL = "https://djangocontentstudio.org/docs/developer-tools";

// A request slower than this, or with more alike queries, is marked.
const SLOW_REQUEST_MS = 1000;
const SIMILAR_QUERIES = 10;

type Filter = "all" | "error" | "warning";
type Tab = "issues" | "requests" | "info";

export default function Devtools() {
  const http = useHttp();
  const { issues: browserIssues, seq, responses } = useDevtoolsState();
  const [open, setOpen] = useState(false);
  const [hidden, setHidden] = useState(false);
  const [tab, setTab] = useState<Tab>("issues");

  const query = useQuery({
    queryKey: ["devtools"],
    retry: false,
    refetchOnWindowFocus: false,
    async queryFn() {
      const { data } = await http.get<DevtoolsData>("/devtools");
      return data;
    },
  });
  const { data, refetch } = query;
  // A 404: the server has them off (DEBUG is off, or DEVTOOLS = False).
  const available = query.isSuccess;
  const visible = available && !hidden;

  // The server announced new issues.
  useEffect(() => {
    if (data && seq >= 0 && seq !== data.seq) {
      void refetch();
    }
  }, [seq, data, refetch]);

  // While the requests are open, every response is a new row.
  useEffect(() => {
    if (!open || tab !== "requests") {
      return;
    }

    const timeout = window.setTimeout(() => void refetch(), 300);

    return () => window.clearTimeout(timeout);
  }, [responses, open, tab, refetch]);

  useEffect(() => {
    setDevtoolsVisible(visible);
    return () => setDevtoolsVisible(false);
  }, [visible]);

  const issues = useMemo(
    () =>
      [...(data?.issues ?? []), ...browserIssues].sort((a, b) =>
        b.last_seen.localeCompare(a.last_seen),
      ),
    [data, browserIssues],
  );

  if (!visible) {
    return null;
  }

  const errors = issues.filter((issue) => issue.level === "error").length;
  const warnings = issues.filter((issue) => issue.level === "warning").length;
  const label = [
    "Developer tools",
    errors && `${errors} ${errors === 1 ? "error" : "errors"}`,
    warnings && `${warnings} ${warnings === 1 ? "warning" : "warnings"}`,
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <>
      {open && (
        <DevtoolsPanel
          tab={tab}
          onTabChange={setTab}
          issues={issues}
          requests={data?.requests ?? []}
          info={data?.info}
          onClose={() => setOpen(false)}
          onHide={() => {
            setOpen(false);
            setHidden(true);
          }}
          onClearIssues={async () => {
            clearBrowserIssues();
            await http.delete("/devtools/issues");
            await refetch();
          }}
          onClearRequests={async () => {
            await http.delete("/devtools/requests");
            await refetch();
          }}
          onRunChecks={async () => {
            await http.post("/devtools/checks");
            await refetch();
          }}
        />
      )}
      <button
        type="button"
        data-slot="devtools-button"
        aria-label={open ? "Close developer tools" : label}
        aria-expanded={open}
        title={label}
        onClick={() => setOpen((value) => !value)}
        className={cn(
          "fixed right-5 bottom-5 z-50 flex size-11 cursor-pointer items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg outline-none transition-transform hover:scale-105 focus-visible:ring-3 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
          open && "ring-3 ring-ring ring-offset-2 ring-offset-background",
        )}
      >
        {open ? (
          <PiXBold className="size-[18px]" />
        ) : (
          <PiCodeBold className="size-5" />
        )}
        {!open && issues.length > 0 && (
          <span
            data-slot="devtools-count"
            data-level={errors ? "error" : "warning"}
            className={cn(
              "absolute -top-1.5 -right-1.5 min-w-5 h-5 px-1.5 rounded-full border-2 border-background text-[11px] leading-4 font-semibold tabular-nums text-primary-foreground",
              errors ? "bg-destructive" : "bg-warning",
            )}
          >
            {issues.length > 99 ? "99+" : issues.length}
          </span>
        )}
      </button>
    </>
  );
}

function DevtoolsPanel({
  tab,
  onTabChange,
  issues,
  requests,
  info,
  onClose,
  onHide,
  onClearIssues,
  onClearRequests,
  onRunChecks,
}: {
  tab: Tab;
  onTabChange: (tab: Tab) => void;
  issues: DevtoolsIssue[];
  requests: DevtoolsRequest[];
  info?: DevtoolsInfo;
  onClose: () => void;
  onHide: () => void;
  onClearIssues: () => Promise<void>;
  onClearRequests: () => Promise<void>;
  onRunChecks: () => Promise<void>;
}) {
  return (
    <section
      aria-label="Developer tools"
      data-slot="devtools-panel"
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.stopPropagation();
          onClose();
        }
      }}
      className="fixed right-5 bottom-[76px] z-50 flex h-[620px] max-h-[calc(100vh-96px)] w-[480px] max-w-[calc(100vw-40px)] flex-col overflow-hidden rounded-2xl border bg-popover text-popover-foreground shadow-xl animate-in fade-in-0 slide-in-from-bottom-2 duration-150"
    >
      <div className="flex items-center gap-2 py-3 pr-3 pl-4">
        <PiCodeBold className="size-4" />
        <h2 className="text-base font-semibold">Developer tools</h2>
        <span className="h-5 rounded-md border px-1.5 text-[11px] leading-[18px] font-medium text-muted-foreground">
          DEBUG
        </span>
        <span className="grow" />
        <Button
          variant="ghost"
          size="icon-sm"
          className="text-muted-foreground"
          aria-label="Hide the button until the page reloads"
          title="Hide until the page reloads"
          onClick={onHide}
        >
          <PiEyeSlashBold />
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          className="text-muted-foreground"
          aria-label="Close developer tools"
          onClick={onClose}
        >
          <PiXBold />
        </Button>
      </div>
      <Tabs
        value={tab}
        onValueChange={(value) => onTabChange(value as Tab)}
        className="min-h-0 flex-1 gap-0"
      >
        <div className="px-4 pb-3">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="issues">
              Issues
              <Count value={issues.length} />
            </TabsTrigger>
            <TabsTrigger value="requests">
              Requests
              <Count value={requests.length} />
            </TabsTrigger>
            <TabsTrigger value="info">Info</TabsTrigger>
          </TabsList>
        </div>
        <TabsContent value="issues" className="min-h-0 overflow-y-auto">
          <IssuesTab issues={issues} onClear={onClearIssues} />
        </TabsContent>
        <TabsContent value="requests" className="min-h-0 overflow-y-auto">
          <RequestsTab requests={requests} onClear={onClearRequests} />
        </TabsContent>
        <TabsContent value="info" className="min-h-0 overflow-y-auto">
          <InfoTab info={info} onRunChecks={onRunChecks} />
        </TabsContent>
      </Tabs>
      <div className="border-t bg-muted px-4 py-2.5 text-xs text-muted-foreground">
        Shown because DEBUG is on. Turn it off with{" "}
        <code className="font-mono">CONTENT_STUDIO["DEVTOOLS"] = False</code>.
      </div>
    </section>
  );
}

function Count({ value }: { value: number }) {
  return value ? (
    <span className="text-xs font-normal text-muted-foreground tabular-nums">
      {value}
    </span>
  ) : null;
}

function IssuesTab({
  issues,
  onClear,
}: {
  issues: DevtoolsIssue[];
  onClear: () => Promise<void>;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const shown = issues.filter(
    (issue) => filter === "all" || issue.level === filter,
  );
  const counts: Record<Filter, number> = {
    all: issues.length,
    error: issues.filter((issue) => issue.level === "error").length,
    warning: issues.filter((issue) => issue.level === "warning").length,
  };

  if (!issues.length) {
    return (
      <Empty
        title="No issues"
        text="Warnings and errors from the server and the browser show up here."
      />
    );
  }

  return (
    <div>
      <div className="flex items-center gap-1.5 px-4 pb-2.5">
        {(
          [
            ["all", "All"],
            ["error", "Errors"],
            ["warning", "Warnings"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            aria-pressed={filter === value}
            onClick={() => setFilter(value)}
            className={cn(
              "inline-flex h-[26px] cursor-pointer items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium text-muted-foreground outline-none focus-visible:ring-3 focus-visible:ring-ring",
              filter === value &&
                "border-transparent bg-secondary text-foreground",
            )}
          >
            {label}
            <span className="tabular-nums text-muted-foreground">
              {counts[value]}
            </span>
          </button>
        ))}
        <span className="grow" />
        <Button
          variant="ghost"
          size="sm"
          className="text-muted-foreground"
          onClick={() => void onClear()}
        >
          <PiTrashBold />
          Clear
        </Button>
      </div>
      <ul>
        {shown.map((issue) => (
          <IssueItem
            key={issue.id}
            issue={issue}
            expanded={expanded.has(issue.id)}
            onToggle={() =>
              setExpanded((current) => {
                const next = new Set(current);

                if (next.has(issue.id)) {
                  next.delete(issue.id);
                } else {
                  next.add(issue.id);
                }

                return next;
              })
            }
          />
        ))}
      </ul>
    </div>
  );
}

function LevelIcon({
  level,
  className,
}: {
  level: DevtoolsLevel;
  className?: string;
}) {
  if (level === "error") {
    return (
      <PiXCircleBold
        aria-label="Error"
        className={cn("text-destructive", className)}
      />
    );
  }

  if (level === "warning") {
    return (
      <PiWarningBold
        aria-label="Warning"
        className={cn("text-warning", className)}
      />
    );
  }

  return (
    <PiInfoBold
      aria-label="Info"
      className={cn("text-muted-foreground", className)}
    />
  );
}

function IssueItem({
  issue,
  expanded,
  onToggle,
}: {
  issue: DevtoolsIssue;
  expanded: boolean;
  onToggle: () => void;
}) {
  const title = issue.title || firstLine(issue.message);
  const code = issue.snippet || issue.stack;

  return (
    <li className="border-t" data-slot="devtools-issue">
      <button
        type="button"
        aria-expanded={expanded}
        onClick={onToggle}
        className="grid w-full cursor-pointer grid-cols-[16px_minmax(0,1fr)_auto_14px] items-start gap-2.5 px-4 py-3 text-left outline-none hover:bg-accent focus-visible:bg-accent"
      >
        <LevelIcon level={issue.level} className="mt-0.5 size-4" />
        <span className="flex min-w-0 flex-col gap-0.5">
          <span className="min-w-0">
            <span className="font-medium">{title}</span>
            {issue.code && (
              <span className="ml-1.5 inline-flex h-[18px] items-center rounded-md bg-secondary px-1.5 align-[1px] font-mono text-[11px] font-medium text-secondary-foreground">
                {issue.code}
              </span>
            )}
          </span>
          {!expanded && (
            <span className="truncate text-muted-foreground">
              {issue.message}
            </span>
          )}
        </span>
        <span className="mt-px text-xs whitespace-nowrap text-muted-foreground">
          {issue.source === "check" ? "system check" : timeAgo(issue.last_seen)}
        </span>
        <PiCaretRightBold
          className={cn(
            "mt-[3px] size-3.5 text-muted-foreground transition-transform",
            expanded && "rotate-90",
          )}
        />
      </button>
      {expanded && (
        <div className="flex flex-col gap-2.5 pr-4 pb-3.5 pl-[42px]">
          <p className="whitespace-pre-wrap break-words">{issue.message}</p>
          {issue.hint && <p className="text-muted-foreground">{issue.hint}</p>}
          {code && <CodeBlock>{code}</CodeBlock>}
          <div className="flex flex-wrap items-center gap-3">
            {code && (
              <CopyButton
                text={code}
                label={issue.snippet ? "Copy" : "Copy traceback"}
              />
            )}
            {issue.docs && (
              <a
                href={issue.docs}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-xs font-medium hover:underline"
              >
                Docs
                <PiArrowSquareOutBold className="size-3" />
              </a>
            )}
            <span className="grow" />
            <span className="text-xs text-muted-foreground">
              {issueMeta(issue)}
            </span>
          </div>
        </div>
      )}
    </li>
  );
}

function issueMeta(issue: DevtoolsIssue) {
  const parts: string[] = [];

  if (issue.method && issue.path) {
    parts.push(`${issue.method} ${issue.path}`);
  }

  parts.push(
    {
      check: "System check",
      log: "Log",
      server: "Server",
      report: "Reported",
      browser: "Browser",
    }[issue.source],
  );

  if (issue.count > 1) {
    parts.push(`Seen ${issue.count} times`);
  }

  return parts.join(" · ");
}

function RequestsTab({
  requests,
  onClear,
}: {
  requests: DevtoolsRequest[];
  onClear: () => Promise<void>;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (!requests.length) {
    return (
      <Empty
        title="No requests yet"
        text="Your requests to the admin API show up here, with their time and database queries."
      />
    );
  }

  return (
    <div>
      <div className="flex items-center gap-1.5 px-4 pb-1.5 text-muted-foreground">
        <span>Your last {requests.length} requests to the admin API</span>
        <span className="grow" />
        <Button
          variant="ghost"
          size="sm"
          className="text-muted-foreground"
          onClick={() => void onClear()}
        >
          <PiTrashBold />
          Clear
        </Button>
      </div>
      <div
        aria-hidden="true"
        className="grid grid-cols-[44px_minmax(0,1fr)_36px_64px_28px_12px] gap-2 px-4 py-2 text-xs font-medium text-muted-foreground"
      >
        <span>Method</span>
        <span>Path</span>
        <span>Status</span>
        <span className="text-right">Time</span>
        <span className="text-right">DB</span>
        <span />
      </div>
      <ul>
        {requests.map((request) => (
          <RequestItem
            key={request.id}
            request={request}
            expanded={expanded === request.id}
            onToggle={() =>
              setExpanded((current) =>
                current === request.id ? null : request.id,
              )
            }
          />
        ))}
      </ul>
    </div>
  );
}

function RequestItem({
  request,
  expanded,
  onToggle,
}: {
  request: DevtoolsRequest;
  expanded: boolean;
  onToggle: () => void;
}) {
  const slow = request.ms >= SLOW_REQUEST_MS;
  const similar = request.similar[0];
  const many = !!similar && similar.count > SIMILAR_QUERIES;

  return (
    <li className="border-t" data-slot="devtools-request">
      <button
        type="button"
        aria-expanded={expanded}
        aria-label={`${request.method} ${request.path}, ${request.status}, ${Math.round(request.ms)} ms, ${request.queries} queries`}
        onClick={onToggle}
        className="grid w-full cursor-pointer grid-cols-[44px_minmax(0,1fr)_36px_64px_28px_12px] items-center gap-2 px-4 py-2.5 text-left text-xs outline-none hover:bg-accent focus-visible:bg-accent"
      >
        <span className="font-mono font-semibold text-muted-foreground">
          {request.method}
        </span>
        <span className="truncate font-mono" title={request.path}>
          {request.path}
        </span>
        <span
          className={cn(
            "font-mono font-semibold",
            request.status >= 500
              ? "text-destructive"
              : request.status >= 400
                ? "text-warning"
                : "text-muted-foreground",
          )}
        >
          {request.status}
        </span>
        <span
          className={cn(
            "text-right tabular-nums",
            slow && "font-semibold text-warning",
          )}
        >
          {formatMs(request.ms)}
        </span>
        <span
          className={cn(
            "text-right tabular-nums",
            many && "font-semibold text-warning",
          )}
        >
          {request.queries}
        </span>
        <PiCaretRightBold
          className={cn(
            "size-3 text-muted-foreground transition-transform",
            expanded && "rotate-90",
          )}
        />
      </button>
      {expanded && (
        <div className="flex flex-col gap-2 pr-4 pb-3.5 pl-[68px]">
          <p>
            {request.queries} {request.queries === 1 ? "query" : "queries"} in{" "}
            {formatMs(request.query_ms)}
            {similar
              ? `, ${similar.count} of them alike.`
              : request.queries
                ? "."
                : ""}
          </p>
          {similar && (
            <CodeBlock>{`${similar.sql}   × ${similar.count}`}</CodeBlock>
          )}
          {request.slowest.length > 0 && (
            <>
              <p className="text-xs font-medium text-muted-foreground">
                Slowest
              </p>
              <CodeBlock>
                {request.slowest
                  .map(
                    (item) => `${formatMs(item.ms).padStart(9)}  ${item.sql}`,
                  )
                  .join("\n")}
              </CodeBlock>
            </>
          )}
          {many && (
            <p className="flex items-start gap-1.5 text-muted-foreground">
              <PiInfoBold className="mt-0.5 size-3.5 shrink-0" />
              <span>
                One query per related object usually means a missing
                select_related or prefetch_related in the studio's get_queryset.
              </span>
            </p>
          )}
        </div>
      )}
    </li>
  );
}

function InfoTab({
  info,
  onRunChecks,
}: {
  info?: DevtoolsInfo;
  onRunChecks: () => Promise<void>;
}) {
  const match = useMatch("/content/:model/*");
  const label = match?.params.model;
  const studio = label ? info?.studios[label] : undefined;
  const [running, setRunning] = useState(false);
  const [ran, setRan] = useState(false);

  return (
    <div>
      {studio && (
        <InfoSection title="This page" first>
          <InfoRow label="Studio" value={studio.studio} code />
          <InfoRow label="Module" value={studio.module} code />
          <InfoRow label="Model" value={label!} code />
          <InfoRow
            label="list_count"
            value={JSON.stringify(studio.list_count)}
            code
          />
          {studio.list_per_page !== null && (
            <InfoRow label="Page size" value={String(studio.list_per_page)} />
          )}
        </InfoSection>
      )}
      <InfoSection title="Environment" first={!studio}>
        {info?.environment.map((item) => (
          <InfoRow
            key={item.label}
            label={item.label}
            value={item.value}
            code={item.code}
          />
        ))}
      </InfoSection>
      <InfoSection title="Tools">
        <div className="col-span-2 flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            isLoading={running}
            onClick={async () => {
              setRunning(true);

              try {
                await onRunChecks();
                setRan(true);
              } finally {
                setRunning(false);
              }
            }}
          >
            {ran ? <PiCheckBold /> : <PiArrowsClockwiseBold />}
            Run system checks
          </Button>
          <Button variant="outline" size="sm" asChild>
            <Link to="/ui">UI showcase</Link>
          </Button>
          <Button variant="outline" size="sm" asChild>
            <a href={DOCS_URL} target="_blank" rel="noreferrer">
              Documentation
              <PiArrowSquareOutBold className="size-3" />
            </a>
          </Button>
        </div>
      </InfoSection>
    </div>
  );
}

function InfoSection({
  title,
  first,
  children,
}: {
  title: string;
  first?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section
      className={cn(
        "flex flex-col gap-2.5 px-4 py-3.5",
        first ? "pt-0.5" : "border-t",
      )}
    >
      <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
        {title}
      </h3>
      <dl className="grid grid-cols-[150px_minmax(0,1fr)] gap-x-3 gap-y-2">
        {children}
      </dl>
    </section>
  );
}

function InfoRow({
  label,
  value,
  code,
}: {
  label: string;
  value: string;
  code?: boolean;
}) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={cn("min-w-0 break-words", code && "font-mono text-xs")}>
        {value}
      </dd>
    </>
  );
}

function CodeBlock({ children }: { children: string }) {
  return (
    <pre className="max-h-60 overflow-auto rounded-md border bg-muted px-3 py-2.5 font-mono text-xs leading-relaxed whitespace-pre">
      {children}
    </pre>
  );
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);

  return (
    <Button
      variant="outline"
      size="xs"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1500);
        } catch {
          // Copying is not allowed here.
        }
      }}
    >
      {copied ? <PiCheckBold /> : <PiCopyBold />}
      {copied ? "Copied" : label}
    </Button>
  );
}

function Empty({ title, text }: { title: string; text: string }) {
  return (
    <div className="flex flex-col items-center gap-1 px-8 py-16 text-center">
      <p className="font-medium">{title}</p>
      <p className="text-muted-foreground">{text}</p>
    </div>
  );
}

function firstLine(text: string) {
  return text.split("\n")[0];
}

function formatMs(ms: number) {
  return `${Math.round(ms).toLocaleString("en")} ms`;
}

function timeAgo(iso: string) {
  const seconds = (Date.now() - new Date(iso).getTime()) / 1000;

  if (!Number.isFinite(seconds) || seconds < 45) {
    return "just now";
  }

  if (seconds < 3600) {
    return `${Math.round(seconds / 60)} min ago`;
  }

  if (seconds < 86400) {
    return `${Math.round(seconds / 3600)} h ago`;
  }

  return new Date(iso).toLocaleDateString("en");
}
