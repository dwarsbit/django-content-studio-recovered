declare module "@fontsource-variable/*" {}

interface Window {
  /** Set by the Django template when DEBUG is on; enables dev-only UIs. */
  DCS_DEBUG?: boolean;
  /** Set by the Django template while the developer tools are on. */
  DCS_DEVTOOLS?: boolean;
  /** Static asset prefix, set by the Django template. */
  DCS_STATIC_PREFIX?: string;
  /** The editor's language (a frontend locale such as "pt-BR"), set by Django. */
  DCS_LANGUAGE?: string;
  /** The Content Studio version, set by Django; busts cached translations. */
  DCS_VERSION?: string;
}
