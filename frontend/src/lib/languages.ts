import type { Locale } from "date-fns";
import { de, enUS, es, fr, it, nl, ptBR } from "date-fns/locale";

/** A language the editor can pick, as Django lists it in the page. */
export type Language = {
  /** Django's language code, e.g. "pt-br". */
  code: string;
  /** The frontend locale, e.g. "pt-BR". */
  locale: string;
  /** The language's own name, e.g. "Português (Brasil)". */
  name: string;
};

/**
 * The editor's language: Django picks it (content_studio.languages) and
 * writes it into the page. English under the vite dev server.
 */
export function getPageLanguage(): string {
  return window.DCS_LANGUAGE || "en";
}

/** The languages the language picker offers, from the page. */
export function getPageLanguages(): Language[] {
  const script = document.getElementById("dcs-languages");

  if (!script?.textContent) {
    return [];
  }

  try {
    const languages = JSON.parse(script.textContent);
    return Array.isArray(languages) ? languages : [];
  } catch {
    return [];
  }
}

const DATE_LOCALES: Record<string, Locale> = {
  de,
  en: enUS,
  es,
  fr,
  it,
  nl,
  "pt-BR": ptBR,
};

/** The date-fns locale of a language (the calendar's month and day names). */
export function getDateLocale(language: string | undefined): Locale {
  if (!language) {
    return enUS;
  }

  return DATE_LOCALES[language] ?? DATE_LOCALES[language.split("-")[0]] ?? enUS;
}
