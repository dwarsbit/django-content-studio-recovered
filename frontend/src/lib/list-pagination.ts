import type { ListPagination } from "@/types";

/**
 * Whether a list's pagination has an exact total, so that its pages
 * can be numbered.
 */
export function isCounted(
  pagination: ListPagination,
): pagination is ListPagination & { count: number; pages: number } {
  return (
    pagination.count !== null &&
    pagination.pages !== null &&
    !pagination.approximate
  );
}
