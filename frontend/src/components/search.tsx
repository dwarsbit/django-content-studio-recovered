import { useState } from "react";
import { useTranslation } from "react-i18next";
import { PiMagnifyingGlassBold } from "react-icons/pi";
import { useSearchParams } from "react-router";
import { useDebounce } from "react-use";

import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
} from "@/components/ui/input-group";
import { cn } from "@/lib/utils";

/**
 * The list's search box: a debounced input that keeps its term in the
 * URL (`search`). A term that changes in the URL from elsewhere — a
 * "clear all filters", the browser's back button — flows back into
 * the box.
 *
 * The `plain` variant drops the box's own border, for a toolbar that
 * already frames it (the list card's).
 */
export function Search({
  variant = "default",
}: {
  variant?: "default" | "plain";
}) {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const param = searchParams.get("search") ?? "";
  const [local, setLocal] = useState(param);
  // The term the box itself last pushed to the URL, so its own
  // navigation does not overwrite what is being typed meanwhile.
  const [pushed, setPushed] = useState(param);
  const [lastParam, setLastParam] = useState(param);

  if (param !== lastParam) {
    setLastParam(param);
    if (param !== pushed) {
      setLocal(param);
      setPushed(param);
    }
  }

  useDebounce(
    () => {
      // Only navigate when the value actually changed: setSearchParams drops
      // the location hash, and the no-op run on mount would otherwise close
      // an editor opened right after page load (and pollute every list URL
      // with an empty ?search=).
      if ((searchParams.get("search") ?? "") === local) {
        return;
      }

      // A new term strands the current page, so searching returns to
      // the first page.
      setPushed(local);
      setSearchParams((searchParams) => {
        if (local) {
          searchParams.set("search", local);
        } else {
          searchParams.delete("search");
        }
        searchParams.delete("page");
        return searchParams;
      });
    },
    300,
    [local, searchParams, setSearchParams],
  );

  return (
    <InputGroup
      className={cn(
        "h-8 max-w-full shrink-0",
        variant === "plain"
          ? "w-full sm:w-56 border-transparent bg-transparent shadow-none dark:bg-transparent has-[[data-slot=input-group-control]:focus-visible]:ring-0 has-[[data-slot=input-group-control]:focus-visible]:border-transparent has-[[data-slot=input-group-control]:focus-visible]:bg-muted"
          : "w-64",
      )}
    >
      <InputGroupAddon>
        <PiMagnifyingGlassBold className="text-muted-foreground" />
      </InputGroupAddon>
      <InputGroupInput
        placeholder={t("common.search")}
        aria-label={t("common.search")}
        value={local}
        onChange={(e) => {
          setLocal(e.target.value);
        }}
      />
    </InputGroup>
  );
}
