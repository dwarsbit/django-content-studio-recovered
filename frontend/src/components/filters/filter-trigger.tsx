import type { ComponentProps, ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { PiCaretDownBold, PiXBold } from "react-icons/pi";

import { cn } from "@/lib/utils";

/**
 * The button a filter opens from: a quiet label while it is unset, a
 * "Field is value" chip with an inline clear once it has a value. A
 * list of values shows its first and "+N more", so the chip keeps a
 * maximum width. Radix triggers render it through `asChild`, so every
 * prop reaches the button.
 */
export function FilterTrigger({
  label,
  value,
  onClear,
  className,
  ...props
}: Omit<ComponentProps<"button">, "value"> & {
  label: ReactNode;
  // The chosen value (or values), empty or absent while the filter is
  // unset.
  value?: ReactNode | ReactNode[];
  onClear?(): void;
}) {
  const { t } = useTranslation();
  const values = (Array.isArray(value) ? value : [value]).filter(
    (item) => item !== undefined && item !== null && item !== "",
  );
  const active = values.length > 0;

  return (
    <button
      type="button"
      {...props}
      className={cn(
        "h-7 max-w-[min(100%,22rem)] inline-flex items-center gap-1.5 text-sm font-medium whitespace-nowrap cursor-pointer select-none",
        "outline-none focus-visible:ring-3 focus-visible:ring-ring",
        active
          ? "px-3 rounded-full bg-secondary text-secondary-foreground"
          : "px-2.5 rounded-full text-muted-foreground hover:text-foreground hover:bg-muted",
        className,
      )}
    >
      <span className="first-letter:uppercase shrink-0">{label}</span>
      {active ? (
        <>
          <span className="font-normal text-muted-foreground">
            {t("list_view.filters.is")}
          </span>
          <span className="truncate min-w-0">{values[0]}</span>
          {values.length > 1 && (
            <span className="shrink-0 font-normal text-muted-foreground">
              {t("list_view.filters.more", { count: values.length - 1 })}
            </span>
          )}
          {onClear && (
            <span
              role="button"
              tabIndex={0}
              aria-label={t("list_view.filters.clear", { field: label })}
              className="-mr-1.5 size-5 shrink-0 rounded-full inline-flex items-center justify-center hover:bg-foreground/10"
              // A dropdown menu trigger opens on pointerdown, before the
              // click: the clear button must keep that from the trigger.
              onPointerDown={(event) => event.stopPropagation()}
              onClick={(event) => {
                event.stopPropagation();
                onClear();
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  event.stopPropagation();
                  onClear();
                }
              }}
            >
              <PiXBold className="size-3" />
            </span>
          )}
        </>
      ) : (
        <PiCaretDownBold className="size-3 opacity-60" />
      )}
    </button>
  );
}
