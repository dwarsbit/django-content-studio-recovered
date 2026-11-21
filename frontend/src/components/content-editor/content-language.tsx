import type { ReactNode } from "react";
import { useFormContext, useWatch } from "react-hook-form";
import { useTranslation } from "react-i18next";
import {
  PiCaretDownBold,
  PiCheckBold,
  PiCopyBold,
  PiGlobeSimpleXBold,
  PiTranslateBold,
} from "react-icons/pi";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  ContentLanguageContext,
  type ContentLanguageValue,
  type LanguageState,
  useContentLanguage,
  useContentLanguageState,
  useLanguageStates,
} from "@/lib/content-language";
import { cn } from "@/lib/utils";
import type { FormField, Model } from "@/types";

/** The content language of the edit or list page it wraps. */
export function ContentLanguageProvider({
  model,
  value,
  children,
}: {
  model: Model;
  // The page's own state, when it reads the language itself.
  value?: ContentLanguageValue;
  children: ReactNode;
}) {
  return value ? (
    <ContentLanguageContext value={value}>{children}</ContentLanguageContext>
  ) : (
    <OwnContentLanguage model={model}>{children}</OwnContentLanguage>
  );
}

function OwnContentLanguage({
  model,
  children,
}: {
  model: Model;
  children: ReactNode;
}) {
  const value = useContentLanguageState(model);

  return (
    <ContentLanguageContext value={value}>{children}</ContentLanguageContext>
  );
}

function stateClass(state: LanguageState | undefined, required: boolean) {
  return !state || state.missing === 0
    ? "bg-success"
    : required
      ? "bg-destructive"
      : "bg-warning";
}

function StateDot({
  state,
  required,
}: {
  state?: LanguageState;
  required: boolean;
}) {
  return (
    <span
      aria-hidden
      className={cn(
        "size-1.5 shrink-0 rounded-full",
        stateClass(state, required),
      )}
    />
  );
}

/**
 * The content language menu: one compact button with the shown
 * language, and every language with how complete it is.
 */
export function LanguageMenu({
  states,
  className,
}: {
  states?: Record<string, LanguageState>;
  className?: string;
}) {
  const { t } = useTranslation();
  const { config, language, setLanguage } = useContentLanguage();

  if (!config) {
    return null;
  }

  const current = config.languages.find((l) => l.code === language);

  return (
    <DropdownMenu>
      <Tooltip>
        <TooltipTrigger asChild>
          <DropdownMenuTrigger asChild>
            <Button
              variant="outline"
              className={cn("gap-1.5 px-2.5", className)}
              aria-label={`${t("translations.content_language")}: ${
                current?.name ?? language
              }`}
            >
              <PiTranslateBold className="text-muted-foreground" />
              <span className="text-xs font-semibold uppercase tracking-wide">
                {language}
              </span>
              {states && (
                <StateDot
                  state={states[language]}
                  required={config.required.includes(language)}
                />
              )}
              <PiCaretDownBold className="size-3 text-muted-foreground" />
            </Button>
          </DropdownMenuTrigger>
        </TooltipTrigger>
        <TooltipContent>{t("translations.content_language")}</TooltipContent>
      </Tooltip>
      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuLabel className="text-xs text-muted-foreground font-normal">
          {t("translations.content_language")}
        </DropdownMenuLabel>
        {config.languages.map(({ code, name }) => {
          const state = states?.[code];
          const required = config.required.includes(code);

          return (
            <DropdownMenuItem
              key={code}
              onSelect={() => setLanguage(code)}
              className="gap-2.5"
              aria-current={code === language ? "true" : undefined}
            >
              <span className="w-5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                {code}
              </span>
              <span className="flex-1 truncate">
                {name}
                {code === config.default && (
                  <span className="ml-1.5 text-xs text-muted-foreground">
                    {t("translations.default_short")}
                  </span>
                )}
              </span>
              {state && (
                <span
                  className={cn(
                    "flex items-center gap-1.5 text-xs",
                    state.missing === 0
                      ? "text-muted-foreground"
                      : required
                        ? "text-destructive"
                        : "text-warning",
                  )}
                >
                  {state.missing === 0
                    ? t("translations.complete")
                    : t("translations.missing_short", {
                        count: state.missing,
                      })}
                  <StateDot state={state} required={required} />
                </span>
              )}
              <PiCheckBold
                className={cn("size-3.5", code !== language && "invisible")}
              />
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** The edit header's language menu, with each language's state. */
export function EditorLanguageMenu() {
  const states = useLanguageStates();

  return <LanguageMenu states={states} />;
}

function plainText(value: unknown) {
  if (typeof value !== "string") {
    return "";
  }

  return value
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Under a translated field, in another language than the default:
 * the default language's text, with Copy.
 */
export function TranslationReference({ name }: { name: string }) {
  const { t } = useTranslation();
  const { config, language } = useContentLanguage();
  const form = useFormContext();
  const sourceColumn = config?.fields[name]?.[config.default] ?? name;
  const column = config?.fields[name]?.[language];
  const source = useWatch({ name: sourceColumn });

  if (!config || !column || language === config.default) {
    return null;
  }

  const text = plainText(source);

  if (!text) {
    return null;
  }

  const sourceName =
    config.languages.find((l) => l.code === config.default)?.name ??
    config.default;

  return (
    <div
      className="flex items-start gap-2 rounded-md bg-muted/60 px-3 py-2 text-xs"
      data-testid="translation-reference"
    >
      <span
        className="shrink-0 font-semibold uppercase tracking-wide text-muted-foreground mt-px"
        title={sourceName}
      >
        {config.default}
      </span>
      <p className="flex-1 min-w-0 text-muted-foreground line-clamp-2 break-words">
        {text}
      </p>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-6 px-1.5 -my-0.5 text-xs text-muted-foreground"
        aria-label={t("translations.copy_from", { language: sourceName })}
        onClick={() =>
          form.setValue(column, source, {
            shouldDirty: true,
            shouldValidate: true,
          })
        }
      >
        <PiCopyBold className="size-3" />
        {t("translations.copy")}
      </Button>
    </div>
  );
}

/** The language badge on a translated field's label. */
export function LanguageBadge({ code }: { code: string }) {
  return (
    <span className="ml-1.5 rounded bg-muted px-1 py-px text-[10px] font-semibold uppercase tracking-wide text-muted-foreground align-middle">
      {code}
    </span>
  );
}

/** The mark on a shared field's label while another language is shown. */
export function SharedFieldMarker() {
  const { t } = useTranslation();

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className="inline-flex text-muted-foreground/70 align-middle ml-1"
          aria-label={t("translations.shared")}
          role="img"
        >
          <PiGlobeSimpleXBold className="size-3.5" />
        </span>
      </TooltipTrigger>
      <TooltipContent>{t("translations.shared")}</TooltipContent>
    </Tooltip>
  );
}

/**
 * The TranslationStatus component: how complete each content language
 * is, with a click to switch to it.
 */
export function TranslationStatus({ formField }: { formField: FormField }) {
  const { t } = useTranslation();
  const { config, language, setLanguage } = useContentLanguage();
  const states = useLanguageStates();

  if (!config) {
    return null;
  }

  const done = config.languages.filter(
    (l) => states[l.code]?.missing === 0,
  ).length;

  return (
    <div>
      <h2 className="font-semibold">{formField.title}</h2>
      <p className="text-xs text-muted-foreground">
        {t("translations.languages_complete", {
          done,
          total: config.languages.length,
        })}
      </p>
      <ul className="mt-2 -mx-2">
        {config.languages.map(({ code, name }) => {
          const state = states[code];
          const required = config.required.includes(code);
          const progress = state
            ? (state.total - state.missing) / Math.max(state.total, 1)
            : 0;

          return (
            <li key={code}>
              <button
                type="button"
                onClick={() => setLanguage(code)}
                aria-current={code === language ? "true" : undefined}
                className={cn(
                  "w-full flex items-center gap-3 rounded-md px-2 py-2 text-left text-sm transition-colors",
                  code === language ? "bg-accent" : "hover:bg-accent/60",
                )}
              >
                <span className="w-6 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {code}
                </span>
                <span className="flex-1 min-w-0">
                  <span className="block font-medium truncate">
                    {name}
                    {code === config.default && (
                      <span className="ml-1.5 text-xs font-normal text-muted-foreground">
                        {t("translations.default_short")}
                      </span>
                    )}
                  </span>
                  <span className="mt-1 block h-1 rounded-full bg-muted overflow-hidden">
                    <span
                      className={cn(
                        "block h-full rounded-full",
                        stateClass(state, required),
                      )}
                      style={{ width: `${progress * 100}%` }}
                    />
                  </span>
                </span>
                <span
                  className={cn(
                    "text-xs shrink-0",
                    state?.missing
                      ? required
                        ? "text-destructive"
                        : "text-muted-foreground"
                      : "text-success",
                  )}
                >
                  {state?.missing
                    ? t("translations.missing_short", {
                        count: state.missing,
                      })
                    : t("translations.complete")}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
