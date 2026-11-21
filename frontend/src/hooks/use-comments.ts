import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useHttp } from "@/hooks/use-http";
import { useTenant } from "@/tenant";
import type { CommentPerson, CommentThreads, Id } from "@/types";

const EMPTY: CommentThreads = { threads: [], open: 0, resolved: 0 };

function useCommentsKey(model: string, id: Id) {
  const { tenantId } = useTenant();

  return ["comments", tenantId ?? "", model, String(id)];
}

/** An object's comment threads, and the changes to them. Every change
 * answers with the threads, which replace the cached ones. */
export function useComments(model: string, id: Id) {
  const http = useHttp();
  const queryClient = useQueryClient();
  const queryKey = useCommentsKey(model, id);

  const query = useQuery({
    queryKey,
    // Others comment too: refresh now and then while the page is open.
    refetchInterval: 60_000,
    async queryFn() {
      const { data } = await http.get<CommentThreads>("/comments", {
        params: { model, id },
      });

      return data;
    },
  });

  const update = (data: CommentThreads) =>
    queryClient.setQueryData(queryKey, data);

  const mutation = useMutation({
    async mutationFn(
      change:
        | {
            kind: "add";
            body: string;
            mentions: Id[];
            parent?: number;
          }
        | { kind: "edit"; comment: number; body: string; mentions: Id[] }
        | { kind: "delete"; comment: number }
        | { kind: "resolve"; comment: number; resolved: boolean },
    ) {
      switch (change.kind) {
        case "add":
          return (
            await http.post<CommentThreads>("/comments", {
              model,
              id,
              body: change.body,
              mentions: change.mentions,
              parent: change.parent ?? null,
            })
          ).data;
        case "edit":
          return (
            await http.patch<CommentThreads>(`/comments/${change.comment}`, {
              body: change.body,
              mentions: change.mentions,
            })
          ).data;
        case "delete":
          return (
            await http.delete<CommentThreads>(`/comments/${change.comment}`)
          ).data;
        case "resolve":
          return (
            await http.post<CommentThreads>(
              `/comments/${change.comment}/resolve`,
              { resolved: change.resolved },
            )
          ).data;
      }
    },
    onSuccess: update,
  });

  return {
    data: query.data ?? EMPTY,
    isLoading: query.isLoading,
    error: query.error,
    change: mutation.mutateAsync,
    isPending: mutation.isPending,
  };
}

/** The people who can be mentioned on an object, matching query. */
export function useMentionable(model: string, id: Id, query: string | null) {
  const http = useHttp();
  const { tenantId } = useTenant();

  return useQuery({
    enabled: query !== null,
    queryKey: ["comments", tenantId ?? "", model, String(id), "people", query],
    staleTime: 30_000,
    async queryFn() {
      const { data } = await http.get<{ results: CommentPerson[] }>(
        "/comments/people",
        { params: { model, id, q: query } },
      );

      return data.results;
    },
  });
}
