import { useTranslation } from "react-i18next";
import {
  PiCaretLeftBold,
  PiCaretRightBold,
  PiDotsThreeBold,
} from "react-icons/pi";
import ReactPaginateModule from "react-paginate";

import { Button, buttonVariants } from "@/components/ui/button";
import { isCounted } from "@/lib/list-pagination";
import { cn } from "@/lib/utils";
import type { ListPagination as ListPaginationData } from "@/types";

const ReactPaginate = (
  ReactPaginateModule as unknown as { default: typeof ReactPaginateModule }
).default;

function Pagination({
  current,
  pages,
  onPageChange,
}: {
  current: number;
  pages: number;
  onPageChange(page: number): void;
}) {
  return (
    pages > 1 && (
      <ReactPaginate
        forcePage={current - 1}
        pageCount={pages}
        onPageChange={({ selected }) => onPageChange(selected + 1)}
        pageRangeDisplayed={2}
        marginPagesDisplayed={3}
        renderOnZeroPageCount={null}
        className="flex items-center gap-2"
        // Page numbers grow with the list (12,500): the buttons widen
        // from their square size instead of overflowing.
        activeLinkClassName={cn(
          buttonVariants({ variant: "secondary" }),
          "min-w-8 px-2 tabular-nums",
        )}
        pageLinkClassName={cn(
          buttonVariants({ variant: "ghost" }),
          "min-w-8 px-2 tabular-nums",
        )}
        breakLabel={
          <Button variant="ghost" size="icon">
            <PiDotsThreeBold />
          </Button>
        }
        previousLabel={
          <Button variant="ghost" size="icon">
            <PiCaretLeftBold className="size-3" />
          </Button>
        }
        nextLabel={
          <Button variant="ghost" size="icon">
            <PiCaretRightBold className="size-3" />
          </Button>
        }
      />
    )
  );
}

/**
 * The pager of a model's list: numbered pages when the list is counted
 * exactly, previous and next when its total is an estimate or unknown
 * (numbered pages would lead past the real end, and far pages are slow
 * to fetch on large tables).
 */
function ListPagination({
  pagination,
  onPageChange,
}: {
  pagination: ListPaginationData;
  onPageChange(page: number): void;
}) {
  const { t } = useTranslation();
  const { current, has_next } = pagination;

  if (isCounted(pagination)) {
    return (
      <Pagination
        current={current}
        pages={pagination.pages}
        onPageChange={onPageChange}
      />
    );
  }

  return (
    (current > 1 || has_next) && (
      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="icon"
          aria-label={t("list_view.previous_page")}
          disabled={current <= 1}
          onClick={() => onPageChange(current - 1)}
        >
          <PiCaretLeftBold className="size-3" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          aria-label={t("list_view.next_page")}
          disabled={!has_next}
          onClick={() => onPageChange(current + 1)}
        >
          <PiCaretRightBold className="size-3" />
        </Button>
      </div>
    )
  );
}

export { ListPagination, Pagination };
