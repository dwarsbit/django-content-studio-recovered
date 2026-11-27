import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { type ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  PiArrowLeftBold,
  PiClockBold,
  PiCopyBold,
  PiEnvelopeSimpleBold,
  PiPaperclipBold,
  PiPaperPlaneTiltBold,
  PiWarningCircleBold,
} from "react-icons/pi";
import { Link } from "react-router";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DebouncedInput } from "@/components/ui/debounced-input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageBody, PageHeader } from "@/components/ui/page-header";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import {
  type EmailActivityPage as Page,
  type EmailActivityQuery,
  type SentEmail,
  type SentEmailStatus,
  useEmailActivity,
  useEmailActivityEnabled,
  useSendTestEmail,
} from "@/hooks/use-email-activity";
import { useStatusEnabled } from "@/hooks/use-status";
import { cn, getErrorMessage } from "@/lib/utils";

import { formatBytes } from "../backups/_components/format";

dayjs.extend(relativeTime);

const LOGGING_BACKEND =
  "content_studio.contrib.email_activity.backends.EmailBackend";

// Select items cannot have an empty value.
const ALL_KINDS = "__all__";
const NO_KIND = "__other__";

/**
 * The Email activity page, for superusers: the emails the site sent,
 * without their bodies, and Send test email.
 */
export function EmailActivityPage() {
  const { t } = useTranslation();
  const enabled = useEmailActivityEnabled();
  const statusEnabled = useStatusEnabled();
  const [query, setQuery] = useState<EmailActivityQuery>({});
  const { data, isError, isFetching, fetchNextPage, hasNextPage } =
    useEmailActivity(query);
  const [testOpen, setTestOpen] = useState(false);
  const [open, setOpen] = useState<SentEmail | null>(null);
  const first = data?.pages[0];
  const emails = data?.pages.flatMap((page) => page.emails) ?? [];

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <PageHeader
        back={
          statusEnabled ? (
            <Button
              asChild
              size="icon-sm"
              variant="ghost"
              className="-ml-2 text-muted-foreground"
              aria-label={t("email_activity.back")}
            >
              <Link to="/status">
                <PiArrowLeftBold />
              </Link>
            </Button>
          ) : undefined
        }
        icon={<PiEnvelopeSimpleBold />}
        title={t("email_activity.title")}
        actions={
          enabled &&
          !isError && (
            <Button disabled={!first} onClick={() => setTestOpen(true)}>
              <PiPaperPlaneTiltBold />
              {t("email_activity.send_test")}
            </Button>
          )
        }
      />
      <PageBody className="space-y-5">
        {isError || !enabled ? (
          <EmptyState
            icon={<PiEnvelopeSimpleBold />}
            title={t("email_activity.unavailable_title")}
            description={t("email_activity.unavailable_description")}
          />
        ) : (
          <>
            {first && !first.summary.logging ? (
              <NotSetUp page={first} />
            ) : (
              <Facts page={first} />
            )}
            {(!first || first.summary.logging || first.counts.all > 0) && (
              <EmailList
                page={first}
                emails={emails}
                query={query}
                onQuery={setQuery}
                onOpen={setOpen}
                loadingMore={isFetching && !!hasNextPage}
                onLoadMore={hasNextPage ? () => void fetchNextPage() : null}
              />
            )}
          </>
        )}
      </PageBody>
      {first && (
        <TestEmailDialog
          key={testOpen ? "open" : "closed"}
          open={testOpen}
          page={first}
          onOpenChange={setTestOpen}
        />
      )}
      <EmailDialog email={open} onClose={() => setOpen(null)} />
    </div>
  );
}

/** How emails are sent, the last day's counts and how long they are kept. */
function Facts({ page }: { page?: Page }) {
  const { t } = useTranslation();

  if (!page) {
    return (
      <section
        aria-busy
        className="rounded-lg border bg-card shadow-xs h-[74px] animate-pulse"
      />
    );
  }

  const { summary } = page;

  return (
    <section className="rounded-lg border bg-card shadow-xs px-4 py-3 grid gap-3 sm:grid-cols-3">
      <Fact
        icon={<PiEnvelopeSimpleBold />}
        label={t("email_activity.sent_through")}
      >
        {summary.backend}
      </Fact>
      <Fact
        icon={<PiPaperPlaneTiltBold />}
        label={t("email_activity.last_day")}
      >
        {t("email_activity.sent_count", { count: summary.sent })}
        {summary.failed > 0 && (
          <>
            {" · "}
            <span className="text-destructive">
              {t("email_activity.failed_count", { count: summary.failed })}
            </span>
          </>
        )}
      </Fact>
      <Fact icon={<PiClockBold />} label={t("email_activity.kept")}>
        {summary.keep_days
          ? t("email_activity.keep_days", { count: summary.keep_days })
          : t("email_activity.keep_all")}
      </Fact>
    </section>
  );
}

function Fact({
  icon,
  label,
  children,
}: {
  icon: ReactNode;
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="flex items-start gap-3 min-w-0">
      <span
        aria-hidden
        className="size-8 shrink-0 rounded-md border bg-muted text-muted-foreground flex items-center justify-center [&_svg]:size-4"
      >
        {icon}
      </span>
      <div className="min-w-0">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className="text-sm font-medium break-words">{children}</div>
      </div>
    </div>
  );
}

/** The site sends without the logging backend: how to turn it on. */
function NotSetUp({ page }: { page: Page }) {
  const { t } = useTranslation();
  const snippet = [
    `EMAIL_BACKEND = "${LOGGING_BACKEND}"`,
    "",
    "CONTENT_STUDIO = {",
    `    "EMAIL_DELIVERY_BACKEND": "${page.summary.default_backend}",`,
    "}",
  ].join("\n");

  return (
    <section className="rounded-lg border bg-card shadow-xs">
      <EmptyState
        className="py-12"
        icon={<PiEnvelopeSimpleBold />}
        title={t("email_activity.not_set_up_title")}
        description={
          <span className="block max-w-xl">
            {t("email_activity.not_set_up_description", {
              backend: page.summary.backend,
            })}
          </span>
        }
        action={
          <div className="mt-4 w-full max-w-2xl space-y-3">
            <pre className="rounded-md border bg-muted/50 px-4 py-3 text-left text-xs font-mono overflow-x-auto">
              {snippet}
            </pre>
            <p className="text-xs text-muted-foreground">
              {t("email_activity.not_set_up_test")}
            </p>
          </div>
        }
      />
    </section>
  );
}

const STATUSES: (SentEmailStatus | undefined)[] = [undefined, "sent", "failed"];

function EmailList({
  page,
  emails,
  query,
  onQuery,
  onOpen,
  onLoadMore,
  loadingMore,
}: {
  page?: Page;
  emails: SentEmail[];
  query: EmailActivityQuery;
  onQuery: (query: EmailActivityQuery) => void;
  onOpen: (email: SentEmail) => void;
  onLoadMore: (() => void) | null;
  loadingMore: boolean;
}) {
  const { t } = useTranslation();
  const filtered = !!(query.status || query.q || query.kind !== undefined);
  const kind =
    query.kind === undefined
      ? ALL_KINDS
      : query.kind === ""
        ? NO_KIND
        : query.kind;

  return (
    <section className="rounded-lg border bg-card shadow-xs overflow-hidden">
      <div className="px-4 py-3 space-y-3">
        <div>
          <h2 className="font-semibold">{t("email_activity.list.title")}</h2>
          <div className="text-xs text-muted-foreground">
            {t("email_activity.list.description")}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div
            role="group"
            aria-label={t("email_activity.list.status")}
            className="flex items-center gap-1.5"
          >
            {STATUSES.map((status) => {
              const active = query.status === status;
              const count = page?.counts[status ?? "all"];

              return (
                <Button
                  key={status ?? "all"}
                  size="sm"
                  variant={active ? "secondary" : "outline"}
                  aria-pressed={active}
                  className="rounded-full"
                  onClick={() => onQuery({ ...query, status })}
                >
                  {t(`email_activity.list.${status ?? "all"}`)}
                  {count !== undefined && (
                    <span className="text-muted-foreground tabular-nums">
                      {count}
                    </span>
                  )}
                </Button>
              );
            })}
          </div>
          <div className="flex-1" />
          <DebouncedInput
            type="search"
            value={query.q ?? ""}
            onChange={(q) => {
              if (q !== (query.q ?? "")) {
                onQuery({ ...query, q: q || undefined });
              }
            }}
            placeholder={t("email_activity.list.search")}
            aria-label={t("email_activity.list.search")}
            className="h-8 w-full sm:w-72"
          />
          <Select
            value={kind}
            onValueChange={(value) =>
              onQuery({
                ...query,
                kind:
                  value === ALL_KINDS
                    ? undefined
                    : value === NO_KIND
                      ? ""
                      : value,
              })
            }
          >
            <SelectTrigger
              size="sm"
              className="w-auto"
              aria-label={t("email_activity.list.kind")}
            >
              <span className="text-muted-foreground">
                {t("email_activity.list.kind")}:
              </span>
              <SelectValue />
            </SelectTrigger>
            <SelectContent align="end">
              <SelectItem value={ALL_KINDS}>
                {t("email_activity.list.all_kinds")}
              </SelectItem>
              {page?.kinds.map((item) => (
                <SelectItem
                  key={item.value}
                  value={item.value === "" ? NO_KIND : item.value}
                >
                  {item.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      {page?.summary.masked && (
        <div className="border-t bg-muted/50 px-4 py-2 text-xs text-muted-foreground">
          {t("email_activity.list.masked")}
        </div>
      )}
      {!page ? (
        <div aria-busy className="border-t">
          {Array.from({ length: 4 }, (_, idx) => (
            <div key={idx} className="px-4 py-3 space-y-1.5">
              <div className="h-3 w-1/3 rounded bg-muted animate-pulse" />
              <div className="h-2.5 w-1/2 rounded bg-muted animate-pulse" />
            </div>
          ))}
        </div>
      ) : emails.length === 0 ? (
        <EmptyState
          className="border-t py-10"
          icon={<PiEnvelopeSimpleBold />}
          title={
            filtered
              ? t("email_activity.list.no_matches_title")
              : t("email_activity.list.empty_title")
          }
          description={
            filtered
              ? t("email_activity.list.no_matches_description")
              : t("email_activity.list.empty_description")
          }
          action={
            filtered && (
              <Button
                variant="outline"
                size="sm"
                className="mt-3"
                onClick={() => onQuery({})}
              >
                {t("email_activity.list.clear_filters")}
              </Button>
            )
          }
        />
      ) : (
        <ul>
          {emails.map((email) => (
            <EmailRow key={email.id} email={email} onOpen={onOpen} />
          ))}
        </ul>
      )}
      {page && emails.length > 0 && (
        <div className="border-t bg-muted/50 px-4 py-2 text-xs text-muted-foreground flex items-center gap-3">
          <span className="flex-1">
            {page.summary.keep_days
              ? t("email_activity.list.showing_days", {
                  shown: emails.length,
                  count: page.total,
                  days: page.summary.keep_days,
                })
              : t("email_activity.list.showing", {
                  shown: emails.length,
                  count: page.total,
                })}
          </span>
          {onLoadMore && (
            <Button
              variant="outline"
              size="sm"
              disabled={loadingMore}
              onClick={onLoadMore}
            >
              {loadingMore && <Spinner className="size-4" />}
              {t("email_activity.list.load_more")}
            </Button>
          )}
        </div>
      )}
    </section>
  );
}

function StatusBadge({ status }: { status: SentEmailStatus }) {
  const { t } = useTranslation();

  return (
    <Badge tone={status === "sent" ? "green" : "red"} className="shrink-0">
      <span
        aria-hidden
        className={cn(
          "size-1.5 rounded-full",
          status === "sent" ? "bg-success" : "bg-destructive",
        )}
      />
      {t(`email_activity.status.${status}`)}
    </Badge>
  );
}

function formatDuration(ms: number) {
  return `${(ms / 1000).toFixed(1)} s`;
}

function formatWhen(value: string) {
  const when = dayjs(value);

  return dayjs().diff(when, "hour") < 22
    ? when.fromNow()
    : when.format("D MMM YYYY, HH:mm");
}

function EmailRow({
  email,
  onOpen,
}: {
  email: SentEmail;
  onOpen: (email: SentEmail) => void;
}) {
  const { t } = useTranslation();
  const recipients = [...email.to, ...email.cc, ...email.bcc];
  const [firstRecipient] = recipients;

  return (
    <li data-status={email.status} className="border-t">
      <button
        type="button"
        className="w-full text-left px-4 py-3 flex items-start gap-3 hover:bg-muted/50 focus-visible:bg-muted/50 outline-none"
        onClick={() => onOpen(email)}
      >
        <div className="flex-1 min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="font-medium break-words min-w-0">
              {email.subject || (
                <span className="text-muted-foreground italic">
                  {t("email_activity.no_subject")}
                </span>
              )}
            </span>
            <Badge variant="outline" className="font-normal">
              {email.kind_label}
            </Badge>
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
            {firstRecipient && (
              <span className="break-all">
                {t("email_activity.to", { address: firstRecipient })}
                {recipients.length > 1 && (
                  <span className="text-foreground">
                    {" "}
                    {t("email_activity.more", {
                      count: recipients.length - 1,
                    })}
                  </span>
                )}
              </span>
            )}
            {email.from_email && (
              <span className="break-all">
                {t("email_activity.from", { address: email.from_email })}
              </span>
            )}
            <span title={dayjs(email.created_at).format("YYYY-MM-DD HH:mm:ss")}>
              {formatWhen(email.created_at)}
            </span>
            {email.attachments.length > 0 && (
              <span className="inline-flex items-center gap-1 break-all">
                <PiPaperclipBold className="shrink-0" />
                {email.attachments.length === 1
                  ? email.attachments[0].name ||
                    t("email_activity.attachments", { count: 1 })
                  : t("email_activity.attachments", {
                      count: email.attachments.length,
                    })}
              </span>
            )}
            {email.duration != null && (
              <span>{formatDuration(email.duration)}</span>
            )}
          </div>
          {email.error && (
            <div className="text-xs text-destructive break-words line-clamp-2">
              {email.error}
            </div>
          )}
        </div>
        <StatusBadge status={email.status} />
      </button>
    </li>
  );
}

/** One email's details. */
function EmailDialog({
  email,
  onClose,
}: {
  email: SentEmail | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();

  async function onCopy(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      toast.success(t("email_activity.details.copied"));
    } catch {
      toast.error(t("email_activity.details.copy_failed"));
    }
  }

  const list = (values: string[]) => (values.length ? values.join(", ") : "-");
  const at = (value: string | null) =>
    value ? dayjs(value).format("D MMM YYYY, HH:mm:ss") : "-";

  return (
    <Dialog open={!!email} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        {email && (
          <>
            <DialogHeader>
              <DialogTitle className="break-words pr-6">
                {email.subject || t("email_activity.no_subject")}
              </DialogTitle>
              <DialogDescription asChild>
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge status={email.status} />
                  <Badge variant="outline" className="font-normal">
                    {email.kind_label}
                  </Badge>
                </div>
              </DialogDescription>
            </DialogHeader>
            {email.error && (
              <div
                role="alert"
                className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive font-mono break-words"
              >
                <PiWarningCircleBold className="shrink-0 mt-0.5" />
                <span className="min-w-0">{email.error}</span>
              </div>
            )}
            <dl className="grid grid-cols-[minmax(0,9rem)_minmax(0,1fr)] gap-x-4 gap-y-2 text-sm">
              <Row label={t("email_activity.details.from")}>
                {email.from_email || "-"}
              </Row>
              <Row label={t("email_activity.details.to")}>{list(email.to)}</Row>
              <Row label={t("email_activity.details.cc")}>{list(email.cc)}</Row>
              <Row label={t("email_activity.details.bcc")}>
                {list(email.bcc)}
              </Row>
              <Row label={t("email_activity.details.reply_to")}>
                {list(email.reply_to)}
              </Row>
              <Row label={t("email_activity.details.attachments")}>
                {email.attachments.length
                  ? email.attachments
                      .map((item) =>
                        [
                          item.name,
                          item.type,
                          item.size != null ? formatBytes(item.size) : null,
                        ]
                          .filter(Boolean)
                          .join(" · "),
                      )
                      .join(", ")
                  : "-"}
              </Row>
              <Row label={t("email_activity.details.size")}>
                {email.size != null ? formatBytes(email.size) : "-"}
              </Row>
              <Row label={t("email_activity.details.created")}>
                {at(email.created_at)}
              </Row>
              <Row
                label={
                  email.status === "sent"
                    ? t("email_activity.details.sent")
                    : t("email_activity.details.failed")
                }
              >
                {at(email.finished_at)}
                {email.duration != null &&
                  ` (${formatDuration(email.duration)})`}
              </Row>
              {email.sent_by && (
                <Row label={t("email_activity.details.sent_by")}>
                  {email.sent_by}
                </Row>
              )}
              <Row label={t("email_activity.details.backend")}>
                {email.backend || "-"}
              </Row>
              <Row label={t("email_activity.details.message_id")}>
                <span className="font-mono text-xs">
                  {email.message_id || "-"}
                </span>
              </Row>
            </dl>
            <DialogFooter className="sm:items-center">
              <span className="text-xs text-muted-foreground sm:mr-auto">
                {t("email_activity.details.no_body")}
              </span>
              {email.message_id && (
                <Button
                  variant="outline"
                  onClick={() => void onCopy(email.message_id)}
                >
                  <PiCopyBold />
                  {t("email_activity.details.copy_message_id")}
                </Button>
              )}
              <Button onClick={onClose}>
                {t("email_activity.details.close")}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="break-words min-w-0">{children}</dd>
    </>
  );
}

function testEmailError(error: unknown): string {
  const data = (error as { response?: { data?: { to?: string[] } } })?.response
    ?.data;

  return data?.to?.[0] ?? String(getErrorMessage(error));
}

/** Send a test email to an address, your own by default. */
function TestEmailDialog({
  open,
  page,
  onOpenChange,
}: {
  open: boolean;
  page: Page;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  const send = useSendTestEmail();
  const [to, setTo] = useState(page.your_email ?? "");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    try {
      const { detail } = await send.mutateAsync(to.trim());
      toast.success(detail);
      onOpenChange(false);
    } catch (e) {
      setError(testEmailError(e));
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={(event) => void onSubmit(event)} className="space-y-4">
          <DialogHeader>
            <DialogTitle>{t("email_activity.test.title")}</DialogTitle>
            <DialogDescription>
              {page.summary.logging
                ? t("email_activity.test.description", {
                    backend: page.summary.backend,
                  })
                : t("email_activity.test.description_not_logged", {
                    backend: page.summary.backend,
                  })}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="test-email-to">{t("email_activity.test.to")}</Label>
            <Input
              id="test-email-to"
              type="email"
              required
              autoFocus
              value={to}
              aria-invalid={!!error}
              onChange={(event) => setTo(event.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              {t("email_activity.test.hint")}
            </p>
          </div>
          {error && (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive break-words"
            >
              <PiWarningCircleBold className="shrink-0 mt-0.5" />
              <div className="min-w-0">
                <div className="font-medium">
                  {t("email_activity.test.failed")}
                </div>
                <div className="font-mono text-xs">{error}</div>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              {t("email_activity.test.cancel")}
            </Button>
            <Button type="submit" disabled={send.isPending || !to.trim()}>
              {send.isPending ? (
                <Spinner className="size-4" />
              ) : (
                <PiPaperPlaneTiltBold />
              )}
              {t("email_activity.send_test")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
