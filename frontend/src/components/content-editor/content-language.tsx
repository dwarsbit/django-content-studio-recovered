import { createContext, type ReactNode, useContext, useState } from "react";
import { useFormContext, useWatch } from "react-hook-form";
import { useTranslation } from "react-i18next";
import {
  PiCopyBold,
  PiGlobeSimpleXBold,
  PiTranslateBold,
} from "react-icons/pi";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { safeStorage } from "@/lib/safe-storage";
import { cn } from "@/lib/utils";
import type { Model, TranslationConfig } from "@/types";

const STORAGE_KEY = "dcs-content-language";

interface ContentLanguageValue {
  config: TranslationConfig | null;
  language: string;
  setLanguage: (code: string) => void;
}

export const ContentLanguageContext = createContext<ContentLanguageValue>({
  config: null,
  language: "",
  setLanguage: () => {},
});

export function useContentLanguage() {
  return useContext(ContentLanguageContext);
}

function initialLanguage(config: TranslationConfig) {
  const params = new URLSearchParams(window.location.search);
  const wanted = params.get("lang") ?? safeStorage.get(STORAGE_KEY);

  return config.languages.some((l) => l.code === wanted)
    ? (wanted as string)
    : config.default;
}

/** The content language of the edit or list page it wraps. */
export function ContentLanguageProvider({
  model,
  children,
}: {
  model: Model;
  children: ReactNode;
}) {
  const config = model.admin.translations ?? null;
  const [language, setLanguageState] = useState(() =>
    config ? initialLanguage(config) : "",
  );

  return (
    <ContentLanguageContext
      value={{
        config,
        language,
        setLanguage: (code) => {
          safeStorage.set(STORAGE_KEY, code);
          setLanguageState(code);
        },
      }}
    >
      {children}
    </ContentLanguageContext>
  );
}

/** The column a field is edited in, in the current content language. */
export function useTranslatedName(name: string) {
  const { config, language } = useContentLanguage();
  const columns = config?.fields[name];

  return {
    name: columns?.[language] ?? name,
    translated: columns !== undefined,
    // A shared field, while a language other than the default is shown.
    shared:
      config !== null && columns === undefined && language !== config.default,
  };
}

function isEmpty(value: unknown) {
  return value === null || value === undefined || value === "";
}

/** {language code: translated fields left empty}, from the form values. */
export function useLanguageStates(values?: Record<string, unknown>) {
  const { config } = useContentLanguage();
  const columns = config
    ? Object.values(config.fields).flatMap((perLanguage) =>
        Object.values(perLanguage),
      )
    : [];
  const watched = useWatch({ name: columns, disabled: values !== undefined });
  const get = (column: string) =>
    values ? values[column] : watched?.[columns.indexOf(column)];

  const states: Record<string, { missing: number; total: number }> = {};

  for (const language of config?.languages ?? []) {
    const fields = Object.values(config!.fields).filter(
      (perLanguage) => language.code in perLanguage,
    );
    states[language.code] = {
      total: fields.length,
      missing: fields.filter((perLanguage) =>
        isEmpty(get(perLanguage[language.code])),
      ).length,
    };
  }

  return states;
}

function dotClass(missing: number, required: boolean) {
  return missing === 0
    ? "bg-success"
    : required
      ? "bg-destructive"
      : "bg-warning";
}

/** EN · NL · DE in the edit header and list toolbar. */
export function LanguageSwitcher({
  states,
  className,
}: {
  states?: Record<string, { missing: number; total: number }>;
  className?: string;
}) {
  const { t } = useTranslation();
  const { config, language, setLanguage } = useContentLanguage();

  if (!config) {
    return null;
  }

  return (
    <div
      role="radiogroup"
      aria-label={t("translations.content_language")}
      className={cn(
        "inline-flex items-center gap-0.5 rounded-lg bg-muted p-0.5 h-8",
        className,
      )}
    >
      <PiTranslateBold className="mx-1.5 size-3.5 text-muted-foreground" />
      {config.languages.map(({ code, name }) => {
        const state = states?.[code];
        const required = config.required.includes(code);
        const active = code === language;

        return (
          <Tooltip key={code}>
            <TooltipTrigger asChild>
              <button
                type="button"
                role="radio"
                aria-checked={active}
                aria-label={name}
                onClick={() => setLanguage(code)}
                className={cn(
                  "h-7 px-2.5 rounded-md text-xs font-semibold uppercase tracking-wide flex items-center gap-1.5 transition-colors",
                  active
                    ? "bg-background text-foreground shadow-xs"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {code}
                {state && (
                  <span
                    className={cn(
                      "size-1.5 rounded-full",
                      dotClass(state.missing, required),
                    )}
                  />
                )}
              </button>
            </TooltipTrigger>
            <TooltipContent>
              {name}
              {state &&
                ` · ${
                  state.missing === 0
                    ? t("translations.language_complete")
                    : t("translations.language_missing", {
                        count: state.missing,
                      })
                }`}
            </TooltipContent>
          </Tooltip>
        );
      })}
    </div>
  );
}

function plainText(value: unknown) {
  if (typeof value !== "string") {
    return "";
  }

  return value
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Under a translated field in another language than the default: the
 * default language's text, with Copy.
 */
export function TranslationReference({
  name,
  column,
}: {
  name: string;
  column: string;
}) {
  const { t } = useTranslation();
  const { config, language } = useContentLanguage();
  const form = useFormContext();
  const source = useWatch({ name });

  if (!config || language === config.default || column === name) {
    return null;
  }

  const sourceName =
    config.languages.find((l) => l.code === config.default)?.name ??
    config.default;
  const text = plainText(source);

  if (!text) {
    return null;
  }

  return (
    <div className="flex items-start gap-2 rounded-md bg-muted/60 px-3 py-2 text-xs">
      <span className="shrink-0 font-semibold uppercase tracking-wide text-muted-foreground mt-px">
        {config.default}
      </span>
      <p
        className="flex-1 min-w-0 text-muted-foreground line-clamp-2"
        title={sourceName}
      >
        {text}
      </p>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-6 px-1.5 -my-0.5 text-xs text-muted-foreground"
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

/** The marker on a shared field's label while another language is shown. */
export function SharedFieldMarker() {
  const { t } = useTranslation();

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className="inline-flex text-muted-foreground/70 align-middle ml-1"
          aria-label={t("translations.shared")}
        >
          <PiGlobeSimpleXBold className="size-3.5" />
        </span>
      </TooltipTrigger>
      <TooltipContent>{t("translations.shared")}</TooltipContent>
    </Tooltip>
  );
}

/** The Translations card at the top of the sidebar. */
export function TranslationsCard() {
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
    <section className="rounded-lg border bg-card shadow-xs w-full">
      <div className="px-5 py-3 border-b">
        <h4 className="font-semibold">{t("translations.card_title")}</h4>
        <div className="text-xs text-muted-foreground">
          {t("translations.card_description", {
            done,
            total: config.languages.length,
          })}
        </div>
      </div>
      <ul className="p-2">
        {config.languages.map(({ code, name }) => {
          const state = states[code];
          const required = config.required.includes(code);
          const active = code === language;
          const progress = state
            ? (state.total - state.missing) / Math.max(state.total, 1)
            : 0;

          return (
            <li key={code}>
              <button
                type="button"
                onClick={() => setLanguage(code)}
                className={cn(
                  "w-full flex items-center gap-3 rounded-md px-3 py-2 text-left text-sm transition-colors",
                  active ? "bg-accent" : "hover:bg-accent/60",
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
                        {t("translations.language_default")}
                      </span>
                    )}
                  </span>
                  <span className="mt-1 block h-1 rounded-full bg-muted overflow-hidden">
                    <span
                      className={cn(
                        "block h-full rounded-full",
                        dotClass(state?.missing ?? 0, required),
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
                    ? t("translations.language_missing", {
                        count: state.missing,
                      })
                    : t("translations.language_complete")}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
