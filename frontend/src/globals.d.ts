declare module "@fontsource-variable/*" {}

interface Window {
  /** Static asset prefix, set by the Django template. */
  DCS_STATIC_PREFIX?: string;
  /** The editor's language (a frontend locale such as "pt-BR"), set by Django. */
  DCS_LANGUAGE?: string;
  /**
   * Changes with the Content Studio version without naming it, set by
   * Django; busts cached translations.
   */
  DCS_ASSET_TOKEN?: string;
}
