import { createContext, useContext, useState } from "react";
import { useWatch } from "react-hook-form";

import { safeStorage } from "@/lib/safe-storage";
import type { Model, TranslationConfig } from "@/types";

/**
 * The content language: which language the translated fields of the
 * edit and list pages show (ModelStudio.translations). Not the
 * admin's interface language.
 */
export interface ContentLanguageValue {
  config: TranslationConfig | null;
  language: string;
  setLanguage: (code: string) => void;
}

export const ContentLanguageContext = createContext<ContentLanguageValue>({
  config: null,
  language: "",
  setLanguage: () => {},
});

// The last picked content language, so the list and the edit page
// open in it.
const STORAGE_KEY = "dcs-content-language";

export function useContentLanguage() {
  return useContext(ContentLanguageContext);
}

export function storedContentLanguage(config: TranslationConfig) {
  const stored = safeStorage.get(STORAGE_KEY);

  return config.languages.some((language) => language.code === stored)
    ? (stored as string)
    : config.default;
}

export function storeContentLanguage(code: string) {
  safeStorage.set(STORAGE_KEY, code);
}

/** The content language state of a page, for ContentLanguageProvider. */
export function useContentLanguageState(
  model: Model | undefined,
): ContentLanguageValue {
  const config = model?.admin.translations ?? null;
  // The picked language; until then the stored or default one, which
  // is known once the model is.
  const [picked, setPicked] = useState<string | null>(null);
  const language = config
    ? picked && config.languages.some((l) => l.code === picked)
      ? picked
      : storedContentLanguage(config)
    : "";

  return {
    config,
    language,
    setLanguage: (code) => {
      storeContentLanguage(code);
      setPicked(code);
    },
  };
}

export interface TranslatedName {
  // The form value the field is edited in, in the shown language.
  name: string;
  // Whether the field is translated.
  translated: boolean;
  // A shared field, while a language other than the default is shown.
  shared: boolean;
}

/** Where a field of the edit form lives in the shown language. */
export function translatedName(
  config: TranslationConfig | null,
  language: string,
  name: string,
): TranslatedName {
  const columns = config?.fields[name];

  return {
    name: columns?.[language] ?? name,
    translated: columns !== undefined,
    shared:
      config !== null && columns === undefined && language !== config.default,
  };
}

export function useTranslatedName(name: string): TranslatedName {
  const { config, language } = useContentLanguage();

  return translatedName(config, language, name);
}

export function isEmptyValue(value: unknown) {
  return (
    value === null ||
    value === undefined ||
    value === "" ||
    (Array.isArray(value) && value.length === 0)
  );
}

export interface LanguageState {
  // Translated fields left empty in the language.
  missing: number;
  // Translated fields the language has.
  total: number;
}

/** Each language's empty translated fields. */
export function languageStates(
  config: TranslationConfig | null,
  get: (column: string) => unknown,
): Record<string, LanguageState> {
  const states: Record<string, LanguageState> = {};

  for (const { code } of config?.languages ?? []) {
    const columns = Object.values(config!.fields)
      .map((perLanguage) => perLanguage[code])
      .filter((column): column is string => column !== undefined);

    states[code] = {
      total: columns.length,
      missing: columns.filter((column) => isEmptyValue(get(column))).length,
    };
  }

  return states;
}

/** Each language's empty translated fields, from the edit form. */
export function useLanguageStates(): Record<string, LanguageState> {
  const { config } = useContentLanguage();
  const columns = config
    ? Object.values(config.fields).flatMap((perLanguage) =>
        Object.values(perLanguage),
      )
    : [];
  const values = useWatch({ name: columns }) as unknown[] | undefined;

  return languageStates(config, (column) => values?.[columns.indexOf(column)]);
}

/** The language of a translation column, if it is one. */
export function columnLanguage(
  config: TranslationConfig | null,
  column: string,
): string | null {
  for (const perLanguage of Object.values(config?.fields ?? {})) {
    for (const [code, name] of Object.entries(perLanguage)) {
      if (name === column) {
        return code;
      }
    }
  }

  return null;
}
