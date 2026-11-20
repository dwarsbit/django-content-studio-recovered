import i18n from "i18next";
import Backend from "i18next-http-backend";
import { initReactI18next } from "react-i18next";

import { getPageLanguage } from "@/lib/languages";

i18n
  .use(initReactI18next)
  .use(Backend)
  .init({
    // Django picks the language (content_studio.languages), so the menus
    // and the labels and errors from the server always match. A string a
    // language lacks shows in English.
    lng: getPageLanguage(),
    fallbackLng: "en",
    defaultNS: "translation",
    load: "currentOnly",
    interpolation: {
      escapeValue: false,
    },
    backend: {
      loadPath(lng: string, ns: string) {
        const token = window.DCS_ASSET_TOKEN
          ? `?v=${encodeURIComponent(window.DCS_ASSET_TOKEN)}`
          : "";

        return `${window.DCS_STATIC_PREFIX ?? "/"}locales/${lng}/${ns}.json${token}`;
      },
    },
  });
