import colors from "tailwindcss/colors";

export type Id = string;
export type DateString = string;
export type DateTimeString = string;

export type TailwindColor = Exclude<
  keyof typeof colors,
  "inherit" | "transparent" | "current" | "black" | "white"
>;

export interface PaginatedResponse<T> {
  pagination: {
    count: number;
    current: number;
    pages: number;
  };
  results: T[];
}

/**
 * The pagination of a model's list page, which a studio's list_count
 * can make estimated ("approximate") or leave uncounted (count and
 * pages null).
 */
export interface ListPagination {
  count: number | null;
  approximate: boolean;
  current: number;
  pages: number | null;
  has_next: boolean;
  /**
   * While the server runs with DEBUG: a slow exact count, with the
   * studio that can set list_count to avoid it.
   */
}

export interface ListResponse<T> {
  pagination: ListPagination;
  results: T[];
}

export interface AuthState {
  token: string | null;
  setToken(token: string | null): void;
  isAuthenticated: boolean;
  /** Resolves to false when the server could not end the session. */
  logout(): Promise<boolean>;
}

export interface AdminInfo {
  site_header: string;
  site_title: string;
  index_title: string;
  site_url: string;
  health_check: null;
  // The help texts of the project's AUTH_PASSWORD_VALIDATORS.
  password_rules: string[];
  // Null without the password reset app.
  password_reset: { code_minutes: number } | null;
  login_backends: LoginBackend[];
  token_backend: TokenBackend;
  formats: Record<FieldType, FormatConfig>;
  widgets: Record<FieldType, WidgetConfig>;
  settings: {
    created_at_attr: string;
    created_by_attr: string;
    edited_at_attr: string;
    edited_by_attr: string;
    // Days unsaved changes stay in the browser for recovery
    // (RECOVERY_MAX_AGE).
    recovery_max_age?: number;
  };
}

export type LoginBackend = UsernamePasswordBackend;

// A studio's edit_width: "default" keeps the main column readable,
// "wide" lets it fill the page.
export type EditWidth = "default" | "wide";

export enum LoginBackendType {
  UsernamePassword = "UsernamePasswordBackend",
}

export interface UsernamePasswordBackend {
  type: LoginBackendType.UsernamePassword;
  config: {
    username_field_type: FieldType.EmailField | FieldType.CharField;
  };
}

export type TokenBackend = JsonWebTokenBackend;

export enum TokenBackendType {
  JsonWebToken = "JsonWebTokenBackend",
}

export interface JsonWebTokenBackend {
  type: TokenBackendType.JsonWebToken;
  config: {
    ACCESS_TOKEN_LIFETIME: number;
    REFRESH_TOKEN_LIFETIME: number;
  };
}

export interface SessionUser {
  id: string;
  first_name: string;
  last_name: string;
  username: string;
}

export interface ModelGroup {
  models: string[];
  name: string;
  icon: string | null;
  // Accepted for compatibility; the main menu no longer shows it.
  color: TailwindColor | null;
  label: string;
  // Starts collapsed in the main menu; the group holding the current
  // model is always expanded.
  collapsed?: boolean;
}

export interface Model {
  label: string;
  verbose_name: string;
  verbose_name_plural: string;
  tenant_field: string | null;
  // Only reachable through its parent's inline: no list page of its own.
  inline_only?: boolean;
  // Combinations of fields that must be unique: the editor warns about
  // duplicates.
  unique_sets?: UniqueSet[];
  admin: {
    is_singleton: boolean;
    icon: string | null;
    // Whether the edit and list pages show who else has an object open.
    presence?: boolean;
    // Whether the edit page offers Follow (the notifications app).
    notifications?: boolean;
    // Whether the edit page has a Comments card (the comments app).
    comments?: boolean;
    // Whether rich text can link to the model's objects.
    linkable?: boolean;
    // The translated fields and their column per language; null
    // without translations.
    translations?: TranslationConfig | null;
    list: {
      per_page: number;
      description: string;
      display: {
        name: string;
        header: string | null;
        format: FormatConfig | null;
      }[];
      views?: string[];
      search: boolean;
      // The field a relation picker fills with the typed search text when
      // it creates an object: the first search field, if a text field.
      search_field?: string | null;
      // The list filters; plain field names from older servers.
      filter: (ListFilter | string)[];
      trash?: boolean;
      sortable_by: string[] | null;
      // Whether the user may reorder the list (reorder_field is set).
      reorderable?: boolean;
      // The formats the list can be exported in; null without export.
      export?: { formats: ExportFormat[] } | null;
      // Import from a file; null when the studio offers none.
      import?: ImportConfig | null;
      actions: BulkAction[];
      // The actions in each row's menu, run on that one object.
      row_actions?: BulkAction[];
      // Draft, publish and scheduling; null when the studio has none.
      publishing?: PublishingConfig | null;
      // The columns edited in place (list_edit).
      edit?: string[];
    };
    edit: {
      // The studio's edit_actions, in the more actions menu.
      actions?: BulkAction[];
      // Components in the edit page's header, next to the save button.
      header?: FormField[];
      main: FormSetGroup[];
      sidebar: FormSet[];
      // The create form's read-only fields (get_readonly_fields without
      // an object); saved objects carry their own __readonly_fields__.
      readonly_fields?: string[];
      // The create form's prepopulated fields, mapped to their sources.
      prepopulated_fields?: Record<string, string[]>;
      // Whether the edit page offers Duplicate (allow_duplication);
      // it also needs add permission.
      duplicate?: boolean;
      // Whether unsaved changes are kept in the browser for recovery
      // (recover_changes and the RECOVER_CHANGES setting; on when absent),
      // and the fields never kept (recover_changes_exclude).
      recover_changes?: boolean;
      recover_changes_exclude?: string[];
      // The width of the edit page and its dialogs (edit_width).
      width?: EditWidth;
      inlines: {
        model: string;
        fk_name: string;
        readonly_fields?: string[];
        prepopulated_fields?: Record<string, string[]>;
        table_display: {
          name: string;
          header: string | null;
          format: FormatConfig | null;
        }[];
        reorderable?: boolean;
        // Components in the header of an inline row's editor.
        header?: FormField[];
        // The width of the inline's dialogs; the inline studio decides,
        // not the inline model's own studio.
        width?: EditWidth;
        // The inline studio's permissions; unset grants everything the
        // inline endpoints allow.
        permissions?: Permissions;
      }[];
    };
    permissions: Permissions;
  };
  fields: Record<string, ModelField>;
}

export type PresenceState = "viewing" | "editing";

// Another user who has an object open: viewing it, or editing it (their
// form has unsaved changes).
// A person as comments show them.
export interface CommentPerson {
  id: Id;
  name: string;
  initials: string;
  avatar: string | null;
}

export interface CommentInfo {
  id: number;
  // None for a comment from code without an author.
  author: CommentPerson | null;
  body: string;
  mentions: CommentPerson[];
  created_at: DateTimeString;
  edited_at: DateTimeString | null;
  // Deleted with replies: shown as "Comment deleted".
  deleted: boolean;
  // What posted it besides a person, such as "review.submitted" for a
  // review note; empty for an ordinary comment.
  kind?: string;
  can_edit: boolean;
  can_delete: boolean;
}

export interface CommentThread extends CommentInfo {
  resolved_at: DateTimeString | null;
  resolved_by: CommentPerson | null;
  can_resolve: boolean;
  replies: CommentInfo[];
}

export interface CommentThreads {
  threads: CommentThread[];
  open: number;
  resolved: number;
}

export interface PresenceUser {
  id: Id;
  name: string;
  initials: string;
  avatar: string | null;
  state: PresenceState;
}

// A duplicate's starting point: the copied values, in the form's
// shape, and the object they were copied from.
export interface DuplicateInitial {
  initial: Partial<Resource>;
  source: { id: Id; __str__: string };
}

export interface Permissions {
  add_permission: boolean;
  change_permission: boolean;
  delete_permission: boolean;
  view_permission: boolean;
}

export interface BulkAction {
  id: string;
  label: string;
  icon: string | null;
  confirm: string | null;
  destructive: boolean;
  // The built-in export's formats: it downloads the selection instead
  // of running on it.
  formats?: ExportFormat[];
  // The inputs the action asks for in a dialog before it runs.
  fields?: FormField[];
}

export type ExportFormat = "csv" | "xlsx";

export type ImportFormat = "csv" | "xlsx" | "json";

export interface ImportConfig {
  // What an import reads and the "For import" export writes.
  formats: ImportFormat[];
  // The template (a header row) is offered in these.
  template_formats: ExportFormat[];
  // The fields rows are matched on.
  key: string[];
  // The template's columns: the key, then the fields a file may set.
  columns: {
    name: string;
    label: string;
    // The related model's field a relation column holds.
    lookup: string | null;
    required: boolean;
  }[];
  can_import: boolean;
  can_create: boolean;
  can_update: boolean;
}

export interface ImportError {
  // The file's column, or null for the row as a whole.
  column: string | null;
  field: string | null;
  messages: string[];
}

export interface ImportResult {
  preview: boolean;
  // Whether the rows were saved (never for a preview).
  applied: boolean;
  total: number;
  created: number;
  updated: number;
  unchanged: number;
  failed: number;
  // The first failing rows; failed counts all of them.
  failures: { row: number; errors: ImportError[] }[];
  ignored_columns: string[];
  // Why the file cannot be imported at all.
  errors: string[];
}

export interface ImportJob {
  id: string;
  status: "queued" | "running" | "done" | "failed";
  preview: boolean;
  processed: number;
  total: number;
  result: ImportResult | null;
  error: string | null;
}

export interface UniqueSet {
  id: string;
  // The fields whose combination must be unique (without the tenant field).
  fields: string[];
  // The fields a conditional constraint reads.
  condition_fields?: string[];
  // nulls_distinct=False: empty values clash too.
  nulls_equal?: boolean;
}

/**
 * A filter of the list page: a field or a path across relations (with
 * the path's last field), or a custom filter whose options the server
 * builds when the filter opens.
 */
export interface ListFilter {
  name: string;
  label: string;
  field?: ModelField;
  custom?: boolean;
  multiple?: boolean;
}

export interface ModelField {
  type: FieldType;
  choices?: [string, string][];
  required?: boolean;
  verbose_name?: string;
  readonly?: boolean;
  default?: unknown;
  primary_key?: boolean;
  // unique=True (not the primary key): the editor warns about duplicates.
  unique?: boolean;
  max_length?: number;
  help_text?: string;
  widget_class?: FieldWidget;
  format_class?: FieldFormat;
  related_model?: string;
  json_schema?: Record<string, unknown>;
  multiple?: boolean;
  // ColorField, or a field with a ColorValidator: the notation colors are
  // saved in and whether they may be translucent.
  color_format?: "hex" | "rgb" | "hsl";
  alpha?: boolean;
  // BlockField: the block types and the limits on the number of blocks.
  blocks?: BlockDefinition[];
  min_num?: number | null;
  max_num?: number | null;
}

export interface BlockDefinition {
  name: string;
  verbose_name: string;
  description: string;
  icon: string | null;
  fields: Record<string, ModelField>;
}

export interface BlockValue {
  id: string;
  type: string;
  data: Record<string, unknown>;
}

/**
 * A widget as configured on the server: its name and the options it
 * was given (unset options are left out).
 */
export interface WidgetConfig {
  name: FieldWidget;
  options?: Record<string, unknown>;
}

/** A format as configured on the server, like WidgetConfig. */
export interface FormatConfig {
  name: FieldFormat;
  options?: Record<string, unknown>;
}

// Where a format is shown: a table cell (the list page, inlines) or a
// read-only field on the edit page, which has room for more.
export type FormatDisplay = "cell" | "field";

export interface NumberFormatOptions {
  decimals?: number;
  compact?: boolean;
  prefix?: string;
  suffix?: string;
  // CurrencyFormat: an ISO 4217 code.
  currency?: string;
  // PercentFormat: the value is a fraction of one (0.91 is 91%).
  fraction?: boolean;
}

export type BadgeColor =
  "gray" | "blue" | "green" | "yellow" | "red" | "purple";

export interface BadgeFormatOptions {
  colors?: Record<string, BadgeColor>;
  default_color?: BadgeColor;
}

export type DateStyle = "short" | "medium" | "long";

export interface TextFormatOptions {
  // On the list page: cut at this many characters, or clamp to this
  // many lines, with the full text on hover.
  max_length?: number;
  lines?: number;
}

export type DurationStyle = "narrow" | "short" | "long";

export interface DurationFormatOptions {
  style?: DurationStyle;
}

export interface ProgressFormatOptions {
  max_value?: number;
}

export interface BooleanFormatOptions {
  // Words for true and false; colors shows them as badges.
  labels?: [string, string];
  colors?: [BadgeColor, BadgeColor];
}

export interface DateFormatOptions {
  style?: DateStyle;
}

export interface DateTimeFormatOptions {
  relative?: boolean;
  style?: DateStyle;
}

// The character counter of a text field. Unset, it shows once the text
// nears the field's max_length (or recommended_length).
export interface CharacterCountOptions {
  show_count?: boolean;
  // A soft limit: the counter warns past it.
  recommended_length?: number;
}

export interface InputWidgetOptions extends CharacterCountOptions {
  placeholder?: string;
  prefix?: string;
  suffix?: string;
  min_value?: number;
  max_value?: number;
  step?: number;
}

export interface TextAreaWidgetOptions extends CharacterCountOptions {
  rows?: number;
  placeholder?: string;
}

// EmailWidget, URLWidget and PhoneWidget.
export interface PlaceholderWidgetOptions {
  placeholder?: string;
}

export interface PasswordWidgetOptions extends PlaceholderWidgetOptions {
  // The saved value stays on the server: the field's value is
  // {is_set}, and a new value replaces it.
  write_only?: boolean;
}

export interface SliderWidgetOptions {
  min_value: number;
  max_value: number;
  step?: number;
  suffix?: string;
}

export type CodeLanguage = "css" | "html" | "javascript" | "json";

export interface CodeWidgetOptions {
  // The language highlighted; plain text when unset.
  language?: CodeLanguage | null;
}

export interface RatingWidgetOptions {
  // The number of stars.
  max_value?: number;
}

export interface MapWidgetOptions {
  // On a latitude number field: the number field holding the
  // longitude, which the widget fills in too. Unset on a JSONField,
  // which holds {lat, lng}.
  lng_field?: string | null;
  // Where the map starts while the field is empty: [lat, lng] and the
  // zoom (0 the world, 19 a street).
  center?: [number, number] | null;
  zoom?: number | null;
}

// The map tiles and the address search of MapWidget.
export interface MapSettings {
  tile_url: string;
  tile_attribution: string;
  // A Nominatim search URL; null leaves the search box out.
  geocoder_url: string | null;
}

// A location, as MapWidget stores it in a JSONField.
export interface LatLng {
  lat: number;
  lng: number;
}

// The preview of an embedded URL, from /oembed.
export interface EmbedPreview {
  provider: string;
  type: string | null;
  title: string | null;
  author: string | null;
  author_url: string | null;
  thumbnail: string | null;
  thumbnail_width: number | null;
  thumbnail_height: number | null;
  url: string;
}

export interface DurationWidgetOptions {
  show_days?: boolean;
  show_seconds?: boolean;
}

// A FileField's value: the saved file, a file picked in the editor
// (uploaded, attached when the object is saved), or none.
export interface SavedFile {
  name: string;
  url: string;
  // An ImageField's small thumbnail; null when there is none.
  thumbnail?: string | null;
}

export interface PickedFile {
  upload: string;
  name: string;
  size: number;
}

export type FileValue = SavedFile | PickedFile | null;

// A write-only value as the API sends it: whether one is saved.
export interface WriteOnlyValue {
  is_set: boolean;
}

export type RichTextFeature =
  | "heading"
  | "blockquote"
  | "code_block"
  | "bold"
  | "italic"
  | "underline"
  | "strike"
  | "ordered_list"
  | "bullet_list"
  | "link"
  | "image"
  | "table";

export type HeadingLevel = 1 | 2 | 3 | 4 | 5 | 6;

export interface RichTextWidgetOptions {
  // Unset: every feature.
  features?: RichTextFeature[];
  heading_levels?: HeadingLevel[];
  // The models links can point to (labels); unset: every linkable model.
  link_models?: string[];
  // The sizes images can have, the first being the default; unset: every
  // size of IMAGE_SIZES, starting at "original".
  image_sizes?: string[];
}

export interface CoverImageWidgetOptions {
  // "W:H"; unset: 16:9.
  aspect_ratio?: string;
  // Pixels: smaller images get a warning.
  min_width?: number;
  min_height?: number;
}

export interface ColorPickerWidgetOptions {
  // Unset: true.
  show_input?: boolean;
  // Colors offered below the picker.
  swatches?: string[];
}

export interface DateWidgetOptions {
  // ISO dates (YYYY-MM-DD) bounding the days the picker offers.
  min_date?: DateString;
  max_date?: DateString;
}

/**
 * Props shared by field widgets. The concrete value type depends on the
 * field being edited, so every widget instantiates this with the type it
 * handles; the widget registry passes values through as `unknown`.
 */
export interface WidgetProps<T, O = Record<string, unknown>> {
  value?: T;
  onChange(value: T): void;
  // The widget's options, from its configuration.
  options?: O;
}

export interface Resource {
  id: Id;
  __str__: string;
  // The resolved list item display, present on list rows when the admin
  // offers the list view.
  list_item_display?: {
    title: string;
    description?: string;
    meta?: string;
    // An image URL, shown on the left.
    thumbnail?: string;
  };
  // Relation display customization (ModelAdmin.get_relation_display).
  description?: string | null;
  icon?: string | null;
  initials?: string | null;
  avatar?: string | null;
  // The fields read-only for this object (get_readonly_fields), on
  // detail responses.
  __readonly_fields__?: string[];
  // What this user may do with this object (has_change_permission and
  // has_delete_permission with the object), on detail responses.
  __permissions__?: ObjectPermissions;
  // What the edit page of a user offers besides the fields, on detail
  // responses of the user model.
  __user__?: UserInfo;
  // The URL of the object's public page for the edit page's "View on
  // site" button (the studio's view_on_site), on detail responses.
  __view_on_site__?: string | null;
  // The object's publishing, on studios with publishing (list rows and
  // detail responses of saved objects).
  __publishing__?: PublishingInfo | null;
  // Previews, on studios with publishing (detail responses): whether
  // the object is live, and whether the editor may share a draft link.
  __preview__?: PreviewInfo | null;
  [key: string]: unknown;
}

export interface PreviewInfo {
  live: boolean;
  can_share: boolean;
}

// A shared draft link of an object; its URL is only in the answer that
// created it.
export interface SharedLink {
  id: number;
  note: string;
  language: string | null;
  created_by: string | null;
  created_at: string;
  expires_at: string | null;
  opens: number;
  last_opened_at: string | null;
  url?: string;
}

// A publishable object's state, from its dates.
export type PublishingState = "draft" | "scheduled" | "published" | "expired";

export interface PublishingConfig {
  // Whether objects can get an unpublish date.
  unpublish: boolean;
  // Whether the user may publish (per object in __publishing__).
  can_publish: boolean;
  // Whether edits to published objects stay unpublished until Publish
  // changes.
  pending_changes?: boolean;
  // Review before publishing (the review app), or null without it.
  review?: ReviewConfig | null;
}

export interface ReviewConfig {
  // Whether publishers go through review too.
  required: boolean;
  // Whether a publisher may approve their own request.
  self_approval: boolean;
}

export type ReviewStatus =
  "open" | "changes_requested" | "approved" | "withdrawn";

// The object's current review request, on detail responses (list rows
// carry only the status).
export interface ReviewInfo {
  id: number;
  status: ReviewStatus;
  // Whether the review is of a live object's unpublished changes.
  live: boolean;
  submitted_by: CommentPerson | null;
  submitted_at: DateTimeString;
  reviewer: CommentPerson | null;
  note: string;
  decided_by: CommentPerson | null;
  decided_at: DateTimeString | null;
  decision_note: string;
  // Whether the user submitted it.
  mine: boolean;
  can_approve: boolean;
  can_withdraw: boolean;
}

// What the Review dialog shows: GET .../review.
export interface ReviewDetails {
  review: ReviewInfo | null;
  // The version an approval names.
  version: string;
  changes: {
    // What the values are compared with: the live version, the last
    // approved values, or nothing (never approved).
    base: "live" | "approved" | null;
    fields: string[];
    before: Record<string, unknown>;
    after: Record<string, unknown>;
  };
  has_pending: boolean;
  // The fields changed since the request was submitted.
  changed_since_submitted: string[];
  reviewers?: CommentPerson[];
}

// The unpublished changes of a published object, on detail responses.
export interface PendingChangesInfo {
  // The changed fields, in form order.
  fields: string[];
  // Who saved them last, and when.
  edited_by: string | null;
  edited_at: DateTimeString;
  // The published values of those fields, for Compare.
  live: Record<string, unknown>;
}

export interface PublishingInfo {
  state: PublishingState;
  published_at: DateTimeString | null;
  unpublish_at: DateTimeString | null;
  // On detail responses: whether the user may publish this object.
  can_publish?: boolean;
  // On studios with pending_changes: whether the object has unpublished
  // changes, and (on detail responses) what they are.
  has_pending?: boolean;
  pending?: PendingChangesInfo | null;
  // On studios with review: the current review request (null without
  // one); list rows carry only its status.
  review?: ReviewInfo | { status: ReviewStatus } | null;
}

export interface UserInfo {
  // Whether the editor may set this user's password.
  can_set_password: boolean;
  // Whether the editor may email this user a link to set it.
  can_send_password_link?: boolean;
  // Whether the user never logged in: the link is then an invite.
  invited?: boolean;
  // Whether the editor may reset this user's two-factor login.
  can_reset_two_factor?: boolean;
}

export interface ObjectPermissions {
  change: boolean;
  delete: boolean;
}

export interface FormSetGroup {
  label: string;
  formsets: FormSet[];
  // When the tab shows; null: always.
  when?: ConditionTree | null;
}

export interface FormLayout {
  columns: number;
  fields: FormField[];
}

export interface FormSet {
  title: string;
  description: string;
  fields: (FormField | FormLayout)[];
  // When the form set shows; null: always.
  when?: ConditionTree | null;
}

// A condition of the edit page, evaluated by lib/conditions.ts: a group
// of conditions, a field lookup, or a server-side Condition.
export type ConditionTree =
  ConditionGroup | ConditionLookup | ServerConditionLeaf;

export interface ConditionGroup {
  connector: "AND" | "OR" | "XOR";
  negated: boolean;
  children: ConditionTree[];
}

export interface ConditionLookup {
  field: string;
  lookup: string;
  value: unknown;
}

export interface ServerConditionLeaf {
  condition: string;
  fields: string[];
}

export interface FormField {
  type: "field" | "component";
  name: string;
  label: string | null;
  readonly: boolean;
  col_span: number;
  // Widget override from the form configuration; falls back to the
  // model field's default widget when null.
  widget: WidgetConfig | null;
  // When the field or component shows; null: always.
  when?: ConditionTree | null;
  component_id: string;
  component_type:
    | "Link"
    | "LinkButton"
    | "Button"
    | "ActivityLog"
    | "Title"
    | "Subtitle"
    | "Text"
    | "Callout"
    | "Analytics"
    | "SEOPreview"
    | "TranslationStatus";
  copy: boolean;
  icon: string;
  title?: string | null;
  // Button: a question to confirm first, and the destructive style.
  confirm?: string | null;
  destructive?: boolean;
  // Button: the inputs it asks for in a dialog before it runs.
  fields?: FormField[];
  // An action's input that is not a model field: described like one.
  input?: ModelField;
  // Text components: static text, or null when it is computed for the
  // object (per_object) and fetched from the component's endpoint.
  text?: string | null;
  per_object?: boolean;
  // Callout: its variant (the color and default icon).
  variant?: CalloutVariant;
  // Analytics: compact, full, or auto (compact in the sidebar).
  layout?: "auto" | "compact" | "full";
  default_range?: string;
  // SEOPreview: the form fields it reads, and the page's URL (base_url
  // joined with the path field's value) and site name.
  title_field?: string | null;
  description_field?: string | null;
  base_url?: string | null;
  path_field?: string | null;
  site_name?: string | null;
}

export type CalloutVariant = "info" | "success" | "warning" | "danger";

// What a server-side button reports back: a message, and optionally a
// value shown once (such as a generated secret).
export interface ButtonResult {
  message: string | null;
  value: string | null;
}

export enum FieldType {
  BlockField = "BlockField",
  BooleanField = "BooleanField",
  CharField = "CharField",
  ColorField = "ColorField",
  DateField = "DateField",
  DateTimeField = "DateTimeField",
  DecimalField = "DecimalField",
  DurationField = "DurationField",
  EmailField = "EmailField",
  FileField = "FileField",
  FlexField = "FlexField",
  FloatField = "FloatField",
  HTMLField = "HTMLField",
  ImageField = "ImageField",
  IntegerField = "IntegerField",
  JSONField = "JSONField",
  ManyToManyField = "ManyToManyField",
  SlugField = "SlugField",
  TextField = "TextField",
  TimeField = "TimeField",
  URLField = "URLField",
  URLPathField = "URLPathField",
  UUIDField = "UUIDField",
}

export enum FieldFormat {
  BadgeFormat = "BadgeFormat",
  BlockFormat = "BlockFormat",
  BooleanFormat = "BooleanFormat",
  CodeFormat = "CodeFormat",
  ColorFormat = "ColorFormat",
  CurrencyFormat = "CurrencyFormat",
  DateFormat = "DateFormat",
  DateTimeFormat = "DateTimeFormat",
  DurationFormat = "DurationFormat",
  EmailFormat = "EmailFormat",
  FileFormat = "FileFormat",
  FileSizeFormat = "FileSizeFormat",
  ForeignKeyFormat = "ForeignKeyFormat",
  HtmlFormat = "HtmlFormat",
  ImageFormat = "ImageFormat",
  LinkFormat = "LinkFormat",
  ManyMediaFormat = "ManyMediaFormat",
  ManyToManyFormat = "ManyToManyFormat",
  MediaFormat = "MediaFormat",
  NumberFormat = "NumberFormat",
  PercentFormat = "PercentFormat",
  ProgressFormat = "ProgressFormat",
  TagFormat = "TagFormat",
  TextFormat = "TextFormat",
  TimeFormat = "TimeFormat",
  JSONFormat = "JSONFormat",
  // The Status column of studios with publishing.
  PublishingFormat = "PublishingFormat",
}

export enum FieldWidget {
  BlockWidget = "BlockWidget",
  CheckboxWidget = "CheckboxWidget",
  CodeWidget = "CodeWidget",
  ColorPickerWidget = "ColorPickerWidget",
  DateTimeWidget = "DateTimeWidget",
  DateWidget = "DateWidget",
  DurationWidget = "DurationWidget",
  EmailWidget = "EmailWidget",
  EmbedWidget = "EmbedWidget",
  FileWidget = "FileWidget",
  ForeignKeyWidget = "ForeignKeyWidget",
  IconPickerWidget = "IconPickerWidget",
  InputWidget = "InputWidget",
  JSONSchemaWidget = "JSONSchemaWidget",
  JSONWidget = "JSONWidget",
  KeyValueWidget = "KeyValueWidget",
  ListWidget = "ListWidget",
  MarkdownWidget = "MarkdownWidget",
  ManyToManyWidget = "ManyToManyWidget",
  MapWidget = "MapWidget",
  MediaWidget = "MediaWidget",
  CoverImageWidget = "CoverImageWidget",
  ManyMediaWidget = "ManyMediaWidget",
  MultiSelectWidget = "MultiSelectWidget",
  PasswordWidget = "PasswordWidget",
  PermissionMatrixWidget = "PermissionMatrixWidget",
  PhoneWidget = "PhoneWidget",
  RadioButtonWidget = "RadioButtonWidget",
  RatingWidget = "RatingWidget",
  RichTextWidget = "RichTextWidget",
  SelectWidget = "SelectWidget",
  SlugWidget = "SlugWidget",
  SliderWidget = "SliderWidget",
  SwitchWidget = "SwitchWidget",
  TextAreaWidget = "TextAreaWidget",
  ToggleGroupWidget = "ToggleGroupWidget",
  TimeWidget = "TimeWidget",
  URLPathWidget = "URLPathWidget",
  URLWidget = "URLWidget",
  TagWidget = "TagWidget",
}

export interface CropValue {
  x: string;
  y: string;
  width: string;
  height: string;
  unit: "%";
}

// The focal point on an image, as percentages of its dimensions.
export interface FocalPointValue {
  x: number;
  y: number;
}

export interface MediaItem {
  id: string;
  folder: string | null;
  name: string;
  // Fits 480px: grids, pickers and list rows.
  thumbnail: string;
  // Fits 1600px: the cover image, cropping and the focal point.
  thumbnail_large?: string | null;
  file: string;
  tags: string[];
  alt_text: string;
  type: "file" | "image" | "video" | "audio";
  size: number;
  // A cropped image's original and the crop on it, as percentages of
  // the original; null when the image is not cropped.
  original?: { url: string; crop: CropBox } | null;
  // The image's sizes (IMAGE_SIZES), when the site has any.
  sizes?: Record<
    string,
    { url: string; width: number | null; height: number | null; ready: boolean }
  >;
}

// A crop as the server stores it: numbers, percentages of the original.
export interface CropBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * Metadata read from a media item's file, under the attribute the
 * discover's media_library.metadata names. Images have their size by
 * default; a site's get_media_metadata hook can add more.
 */
export interface MediaMetadata {
  width?: number;
  height?: number;
  // Seconds.
  duration?: number;
  frame_rate?: number;
  [key: string]: unknown;
}

/**
 * Values editors set for some types of media, under the attribute the
 * discover's media_library.properties names. Other keys are a site's
 * own and kept as they are.
 */
export interface MediaProperties {
  focal_point?: FocalPointValue | null;
  [key: string]: unknown;
}

export interface MediaFolder {
  id: string;
  name: string;
  parent: string | null;
  has_children: boolean;
  /** The folder's direct items; null without a media model. */
  count?: number | null;
}

export interface Dashboard {
  widgets: DashboardWidget[];
}

export interface DashboardWidget {
  name: string;
  // How the widget is shown; independent of its name.
  widget_type: DashboardWidgetType | null;
  widget_id: string;
  col_span: number;
  // Seconds between reloads of the widget's data; null reloads only on
  // focus and reconnect.
  refresh_interval?: number | null;
}

export enum DashboardWidgetType {
  SpacingWidget = "SpacingWidget",
  StatisticWidget = "StatisticWidget",
  ActivityLogWidget = "ActivityLogWidget",
  ScheduledTasksWidget = "ScheduledTasksWidget",
  ContentListWidget = "ContentListWidget",
  NotificationsWidget = "NotificationsWidget",
  ReviewQueue = "ReviewQueue",
}

export interface ActivityLogEntry {
  id: number;
  action_flag: 1 | 2 | 3; // Addition, change or deletion
  action_time: DateTimeString;
  object_repr: string;
  object_id: string;
  object_model: string;
  user?: {
    id: string;
    __str__: string;
  };
  // The change in words, such as "Changed Title and Body."; empty when
  // nothing was recorded.
  message?: string;
  // The object's activity only: whether the history app kept a
  // version with the entry, which then opens it.
  has_version?: boolean;
}

// A version the history app kept with an activity log entry: the
// object's values after the change (data), the fields it changed and
// their values before it (previous). A created object changed none.
export interface ActivityVersion extends ActivityLogEntry {
  fields: string[];
  previous: Record<string, unknown>;
  data: Record<string, unknown>;
}

/** One model's results from the global search endpoint. */
export interface SearchResultGroup {
  model: string;
  verbose_name: string;
  icon: string | null;
  // url: with linkable searches only, the URL a link to the object gets.
  results: { id: Id; title: string; url?: string }[];
}

export interface MainMenuLinkConfig {
  // A path in the admin, or an http(s) URL that opens in a new tab.
  url: string;
  icon: string | null;
  color: TailwindColor | null;
  label: string;
  // The position among the menu's links and buttons: lower first.
  weight?: number;
}

export interface MainMenuButtonConfig {
  label: string;
  icon: string | null;
  color: TailwindColor | null;
  confirm: string | null;
  weight?: number;
}

export interface IFramePageConfig {
  path: string;
  iframe_url: string;
  // The iframe's sandbox attribute; null embeds the page without one.
  sandbox: string | null;
}

export interface DashboardPageConfig {
  path: string;
  title: string;
  description: string | null;
  widgets: DashboardWidget[];
}

export interface MainMenuLinkExtension {
  extension_id: string;
  extension_type: ExtensionType.MainMenuLink;
  config: MainMenuLinkConfig;
}

export interface IFramePageExtension {
  extension_id: string;
  extension_type: ExtensionType.IFramePage;
  config: IFramePageConfig;
}

export interface DashboardPageExtension {
  extension_id: string;
  extension_type: ExtensionType.DashboardPage;
  config: DashboardPageConfig;
}

export interface MainMenuButtonExtension {
  extension_id: string;
  extension_type: ExtensionType.MainMenuButton;
  config: MainMenuButtonConfig;
}

export interface UserMenuLinkExtension {
  extension_id: string;
  extension_type: ExtensionType.UserMenuLink;
  config: MainMenuLinkConfig;
}

export interface UserMenuButtonExtension {
  extension_id: string;
  extension_type: ExtensionType.UserMenuButton;
  config: MainMenuButtonConfig;
}

export interface AnalyticsMetric {
  key: string;
  label: string;
  kind: "number" | "percent" | "duration";
  // Whether a rise is good (1) or bad (-1).
  sign: 1 | -1;
}

export interface AnalyticsExtensionConfig {
  provider: string;
  metrics: AnalyticsMetric[];
  timeseries_metrics: string[];
  breakdowns: string[];
  realtime: boolean;
  page_path: string | null;
}

export interface AnalyticsExtension {
  extension_id: string;
  extension_type: ExtensionType.AnalyticsExtension;
  config: AnalyticsExtensionConfig;
}

export interface AnalyticsPageExtension {
  extension_id: string;
  extension_type: ExtensionType.AnalyticsPage;
  config: { path: string; title: string; description: string | null };
}

export type Extension =
  | MainMenuLinkExtension
  | MainMenuButtonExtension
  | UserMenuLinkExtension
  | UserMenuButtonExtension
  | IFramePageExtension
  | DashboardPageExtension
  | AnalyticsExtension
  | AnalyticsPageExtension;

export enum ExtensionType {
  MainMenuLink = "MainMenuLink",
  MainMenuButton = "MainMenuButton",
  UserMenuLink = "UserMenuLink",
  UserMenuButton = "UserMenuButton",
  IFramePage = "IFramePage",
  DashboardPage = "DashboardPage",
  AnalyticsExtension = "AnalyticsExtension",
  AnalyticsPage = "AnalyticsPage",
}

export interface TranslationConfig {
  languages: { code: string; name: string }[];
  default: string;
  required: string[];
  // {field: {language code: column}}
  fields: Record<string, Record<string, string>>;
}
