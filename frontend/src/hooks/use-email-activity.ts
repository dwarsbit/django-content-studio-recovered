import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";

import { useDiscover } from "@/hooks/use-discover";
import { useHttp } from "@/hooks/use-http";
import type { DateTimeString } from "@/types";

export type SentEmailStatus = "sent" | "failed";

export interface EmailAttachment {
  name: string;
  type: string;
  // Bytes.
  size: number | null;
}

export interface SentEmail {
  id: number;
  from_email: string;
  to: string[];
  cc: string[];
  bcc: string[];
  reply_to: string[];
  // Empty when subjects are masked.
  subject: string;
  // "invite", "test", ... or "" for emails the studio did not send.
  kind: string;
  kind_label: string;
  status: SentEmailStatus;
  error: string | null;
  // How the email was sent: "SMTP · smtp.example.com:587".
  backend: string;
  message_id: string;
  attachments: EmailAttachment[];
  // Bytes.
  size: number | null;
  sent_by: string | null;
  created_at: DateTimeString;
  finished_at: DateTimeString | null;
  // Milliseconds.
  duration: number | null;
}

export interface EmailActivitySummary {
  // How emails leave the site, as words.
  backend: string;
  // EMAIL_BACKEND (or the default mailer's BACKEND), as a dotted path.
  default_backend: string;
  // Sent and failed in the last 24 hours.
  sent: number;
  failed: number;
  // Days emails are kept; null keeps them all.
  keep_days: number | null;
  // Whether the site sends through the logging backend.
  logging: boolean;
  // Whether addresses are masked and subjects left out.
  masked: boolean;
}

export interface EmailActivityPage {
  emails: SentEmail[];
  total: number;
  offset: number;
  limit: number;
  counts: { all: number; sent: number; failed: number };
  kinds: { value: string; label: string }[];
  summary: EmailActivitySummary;
  your_email: string;
}

/** The list's filters; undefined filters nothing. */
export interface EmailActivityQuery {
  status?: SentEmailStatus;
  // "" is the emails without a kind.
  kind?: string;
  q?: string;
}

export function useEmailActivityEnabled() {
  const { data: discover } = useDiscover();

  return discover?.email_activity?.enabled === true;
}

/** The logged emails, newest first, a page at a time. */
export function useEmailActivity(query: EmailActivityQuery = {}) {
  const http = useHttp();
  const enabled = useEmailActivityEnabled();

  return useInfiniteQuery({
    enabled,
    retry: false,
    placeholderData: keepPreviousData,
    queryKey: ["email-activity", query],
    async queryFn({ pageParam }) {
      const { data } = await http.get<EmailActivityPage>("/email-activity", {
        params: { ...query, q: query.q || undefined, offset: pageParam },
      });

      return data;
    },
    initialPageParam: 0,
    getNextPageParam: (page: EmailActivityPage) => {
      const next = page.offset + page.emails.length;
      return page.emails.length > 0 && next < page.total ? next : undefined;
    },
  });
}

/** Send a test email; resolves with the message to show. */
export function useSendTestEmail() {
  const http = useHttp();
  const queryClient = useQueryClient();

  return useMutation({
    async mutationFn(to: string) {
      const { data } = await http.post<{ detail: string }>(
        "/email-activity/test",
        { to },
      );

      return data;
    },
    onSettled() {
      // Sent or failed, the email is in the log.
      void queryClient.invalidateQueries({ queryKey: ["email-activity"] });
      void queryClient.invalidateQueries({ queryKey: ["status"] });
    },
  });
}
