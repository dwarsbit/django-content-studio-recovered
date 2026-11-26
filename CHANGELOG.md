# Changelog

## 1.22.1 (2026-11-26)

### Fixes

- **Filters on text fields without choices.** A `CharField` or `TextField`
  without `choices` in `list_filter` (`"city"`, `"author__username"`) was
  listed in the Filter menu but showed nothing when picked. It now gets a
  searchable list of the values in the table, like the classic admin's
  `AllValuesFieldListFilter`: the first 100, with search to find the
  others, and editors can pick several. The values come from the list
  itself, so other tenants and trashed objects stay out. A field the list
  page has no filter for (JSON, files, media) is left out of the menu, and
  `manage.py check` warns about it as `content_studio.W034`. Filter values
  may now contain commas, in custom filter options too.
- **Filter chips stay compact.** A filter with several values shows the
  first and "+2 more", so its chip no longer runs across the toolbar.
- **Remove a filter picked without a value.** A filter added from the
  Filter menu now sits in a bordered chip with an X until it gets a
  value, so a date range (or any other filter) picked by mistake can be
  taken away again.
- **Wider pickers.** The search pickers of relation and text filters are
  at least 18rem and at most 24rem wide, so short filter names no longer
  squeeze their options.

## 1.22.0 (2026-11-25)

### Features

- **Skeleton loaders instead of spinners.** The list page shows its header,
  tabs, search, filters and view toggles at once, and while the first page
  loads, the table shows its own column names over placeholder rows (the
  list, gallery and media library views have their own). The edit page,
  in a dialog too, shows its tabs, card titles and field labels with a
  placeholder for each value, sized by its widget, and the trash list does
  the same for its rows. A load quicker than 200 ms skips the skeleton, so
  a fast page goes straight to its content. The pulse stops when the system
  asks for reduced motion. Nothing to configure.

## 1.21.2 (2026-11-25)

### Fixes

- **Translated fields with a column for every language pass the checks.**
  For a model whose default language has its own column too (`title_en`,
  `title_nl`, no `title`), declared with a `TranslationAdapter` subclass,
  naming `title` in the edit layout, `table_display` or `search_fields`
  failed `manage.py check` (E010, E006, E011), and W001 warned that the
  required columns were missing from the form. The checks now resolve
  translated fields through the studio's translations, and a translated
  field on the form covers all of its columns. The list no longer fails
  on such a field in `table_display`, and its labels read "title" and
  "title (Dutch)" instead of the default column's "title en".
## 1.21.1 (2026-11-22)

### Fixes

- **Backups no longer fail on models without a table.** A backup stopped
  with "Unable to serialize database: relation … does not exist" when an
  installed app had a model with no table, such as a `managed = False`
  model that only stands in for an admin page, or an app that was never
  migrated. Such models are now left out: the backup logs a warning, lists
  them under `skipped` in its manifest and names them on the Backups page.

## 1.21.0 (2026-11-22)

### Features

- **Internal comments and mentions.** Add `content_studio.comments` to
  `INSTALLED_APPS` and run `migrate`: every edit page gets a **Comments**
  card in the sidebar, for notes between the people who work on an object
  (not public comments). Threads with replies, **Resolve** and **Reopen**,
  editing and deleting your own comments, and `@` to mention someone who
  may view the object. With the notifications app, mentions, replies and
  comments on followed objects notify. Anyone who may view an object may
  comment; override `has_comment_permission` to decide otherwise, or set
  `comments = False` to leave a studio out. From code: `add_comment()`,
  `get_comments()` and the `comment_added` signal. See
  [Comments](https://djangocontentstudio.org/docs/comments).
- **Review and approval.** Add `content_studio.review` to `INSTALLED_APPS`,
  run `migrate` and set `review = True` on a studio with publishing.
  Editors without Can publish get **Submit for review**, with an optional
  reviewer and note; people who may publish get **Review**, which shows the
  changes against the live or last approved version and then **Approve and
  publish**, **Approve and schedule…** or **Request changes** with a note.
  Approval is pinned to the version the reviewer saw, and editing stays
  allowed meanwhile. `Review(required=True)` sends publishers through
  review too; `self_approval=True` lets them approve their own requests.
  Badges on the edit and list pages, **In review**, **Changes requested**
  and **Waiting for my review** in the Status filter, three notification
  events, review notes as comments with the comments app, a `ReviewQueue`
  dashboard widget, the `get_reviewers`, `on_submit_for_review` and
  `on_review` hooks and the `review_submitted` and `review_decided`
  signals. System check `content_studio.E058`. See
  [Review and approval](https://djangocontentstudio.org/docs/review).
- Comments have a `kind`, set by `add_comment(..., kind=)`, for comments
  posted by code such as review notes.
- **Calendar view.** Add `"calendar"` to `list_views` and the list page
  offers the objects on a month grid by their publishing date, with the
  list's search and filters. Scheduled content shows on the day it goes
  live, a dot gives each item's state, and items without a date wait in a
  **No date** tray. Drag an item to another day to reschedule it (Can
  publish), or a draft onto a day to schedule it, with Undo. For another
  date field use `CalendarView("starts_on", end=None, label=None,
  editable=True)` from `content_studio.list_views`: a drag saves the date
  through the same save as table editing. New endpoint
  `GET content/<model>/calendar`. Checks `content_studio.E059` (a bare
  `"calendar"` without publishing) and `content_studio.E060` (a calendar
  field that is not a date). See
  [Calendar](https://djangocontentstudio.org/docs/list-page#calendar).
- **Board view.** `BoardView("stage")` from `content_studio.list_views` in
  `list_views` shows the objects as cards in columns, one per choice of a
  field (or object of a foreign key), with the list's search, filters and
  ordering. Each column shows its count and first 20 cards with **Show
  more**, items without a value get a "No <field>" column, cards have the
  bulk checkbox and row menu, and a column's **+** creates an object with
  its value. Drag a card to another column to change the value, saved
  like a table edit, with Undo. Options: `columns=` picks and orders the
  columns, `label=`, `editable=False`. New endpoint
  `GET content/<model>/board`. Check `content_studio.E061`. See
  [Board](https://djangocontentstudio.org/docs/list-page#board).
- **Gallery view.** Add `"gallery"` to `list_views` and the list page
  shows the page as image tiles from the `list_item_display` thumbnail,
  with the title, the meta badge or the publishing state, a placeholder
  for items without an image, and the bulk checkbox and row menu on
  hover. Large or small tiles, remembered per model; it pages, searches,
  filters and sorts like the list. Check `content_studio.W033` (a
  gallery without a thumbnail role). See
  [Gallery](https://djangocontentstudio.org/docs/list-page#gallery).

## 1.20.0 (2026-11-21)

### Features

- **Editing in the table.** Name columns with `table_edit = ["featured",
  "views", "author"]` and editors change them in place on the list page:
  inputs for text and numbers, switches, selects for choices, date pickers
  and foreign key pickers. A cell saves as soon as the editor leaves it,
  through the edit page's save path (hooks, `clean()`, history), with a
  toast that offers Undo; Tab moves on to the next cell and Esc puts the
  old value back. A value someone else changed since the list loaded is
  refused instead of overwritten. Rows the editor may not change show a
  lock, and the first column, which opens the object, is never edited in
  place. Override `get_table_edit(request)` per request; the Django
  admin's `list_editable` also works (check `W032` asks for `table_edit`),
  and check `E057` reports columns a cell cannot edit.
- **Translated content.** Name a studio's translated fields with
  `translations = ["title", "body"]` and give the model a column per
  language (`title_nl`, `title_de`); models registered with
  django-modeltranslation or built on django-parler's `TranslatableModel`
  are detected without it. The edit page gets a language menu in the
  header with how complete each language is; translated fields switch to
  the picked language, show the default language's text with **Copy**
  under them, and shared fields are marked. Add `TranslationStatus()` to
  the sidebar for each language's progress. The list page shows the
  translated columns in the picked language, a Languages column, and a
  **Missing translation** filter; search looks in every language. Set the
  languages with `CONTENT_LANGUAGES` (default: `LANGUAGES`), and the
  languages that must be complete with `Translations(required=...)` (the
  default language). System checks `content_studio.E055` and
  `content_studio.W030` report a configuration that cannot work. See
  [Translated content](https://djangocontentstudio.org/docs/translations).
- **Previews and shared draft links.** On a studio with publishing, View
  on site becomes **Preview draft** while an object is not live: it opens
  the object's page with a preview token that works for an hour
  (`PREVIEW_MAX_AGE`), and **Copy preview link** copies it. Its menu has
  **Share draft link…**: a link anyone can open to see the draft, with an
  expiry (1 day, 7 days by default, 30 days, a date or none), a content
  language and a note, until it is revoked. The dialog lists the active
  links with how often they were opened. Live content keeps its plain link
  and gets **Copy link**. With translated content, the page opens in the
  content language shown. The site shows drafts with one line in a view,
  `previewable(request, queryset)` (or `get_preview(request)` in an API for
  a headless frontend), and `{% preview_banner %}` marks a preview page.
  Shared links need the `content_studio.previews` app and
  `PreviewMiddleware`, which keeps preview pages out of caches and search
  results; `content_studio_prune_previews` deletes expired links. Sharing
  needs the new **Can share** permission (`share_<model>`, superusers
  always have it); set `preview = False` on a studio to keep drafts without
  a page link. System checks `content_studio.E056` and
  `content_studio.W031` report a configuration that cannot work. See
  [Previews and shared draft links](https://djangocontentstudio.org/docs/previews).
- **Unpublished changes.** With `Publishing(..., pending_changes=True)`,
  saving a published object keeps the edit apart instead of changing the
  live content: it is validated as a save would be, the edit page shows it,
  and the site keeps the published version. The header offers **Publish
  changes**, which saves them the regular way (save hooks, history,
  notifications), and the Publishing card names the changed fields with
  **Compare** and **Discard**. The list marks objects with **Unpublished
  changes** and the Status filter finds them; table edits of published rows
  are kept as unpublished changes too. Unpublishing or scheduling again
  keeps the changes in the draft. Needs `content_studio.history`
  (system check `content_studio.E054`); run `migrate` for its new table. See
  [Unpublished changes](https://djangocontentstudio.org/docs/publishing#unpublished-changes).

### Changes

- **Edit pages: a tidier header.** The header's items are grouped and in a fixed order. The publishing state and **Unsaved changes** (else when the object was last edited) sit next to the title. On the right come the editors who have the object open, the content language, and the quiet actions as icon buttons with a tooltip (Follow, View on site, `edit_header` components and the more actions menu), then Save and Publish, set apart. Every control has the same height. The title keeps its room in a narrow window: the status text gives way first and leaves its dot, and below 1024 pixels the model's name is hidden.
- **Kept unsaved changes say so in words.** The header reads **Unsaved changes · kept** instead of showing a green check, which looked like "saved".

## 1.19.0 (2026-11-21)

### Features

- **Draft, publish and scheduling.** Set `publishing = "published_at"` on
  a studio, or `Publishing(...)` for an unpublish date and a status field
  kept in step, and new objects start as drafts. A **Publishing** card at
  the top of the edit page's sidebar shows the state (Draft, Scheduled,
  Published or Expired) and schedules, cancels, unpublishes and sets the
  unpublish date; the header adds **Publish** next to Save while the
  object is not live, saving unsaved changes first. The list gets a
  Status column and filter, and the bulk actions Publish now, Schedule…
  and Unpublish (also for `row_actions`). The state follows from the
  dates, so content goes live on time without a worker.
- **A Can publish permission** for each publishable model, created by
  `migrate` and on the permission matrix. Override
  `has_publish_permission(request, obj=None)` to decide per object.
- **The scheduled run** records what went live or came down: a history
  entry, the new `published` and `unpublished` changes for webhooks and
  notifications, the status field, and the studio's
  `on_publish`/`on_unpublish` hooks. It is a periodic task with Huey, or
  `manage.py content_studio_publish` from cron, and is listed on the
  status page.
- `PublishableModel`, an abstract base model with `published_at` and
  `unpublish_at`, and `Article.objects.live()`, `drafts()`, `scheduled()`
  and `expired()`; `content_studio.publishing.live()` filters any
  queryset. The system check `content_studio.E054` reports a publishing
  configuration that cannot work. See
  [Draft, publish and scheduling](https://djangocontentstudio.org/docs/publishing).
- **Unsaved changes survive a crash, a reload or an expired session.** The
  edit page keeps an editor's changes in their browser while they work (a
  check next to *Unsaved changes* in the header says so) and, when the
  object opens again, offers them back on a banner: **Restore unsaved
  changes**, **Compare** (word by word against the object as it is now) or
  **Discard**. If someone saved the object in the meantime, the banner says
  who; fields only you changed are restored, and fields you both changed
  keep the saved value unless you pick yours in Compare. Unfinished create
  forms are offered too. Nothing reaches the server until Save; logging out
  clears the browser's copy, and passwords, files and read-only fields are
  never kept. Turn it off per model with `recover_changes = False`, keep
  fields out with `recover_changes_exclude`, or turn it off everywhere with
  the `RECOVER_CHANGES` setting; `RECOVERY_MAX_AGE` (7 days) sets how long
  changes are kept. System check `content_studio.W029` reports a
  `recover_changes_exclude` naming a field the model does not have.

### Fixes

- **The X on an active filter chip opened the filter** instead of
  removing it, for choice, boolean and custom filters, on the list page
  and in the media library.

## 1.18.1 (2026-11-20)

### Fixes

- **The first backups after a restore failed on PostgreSQL** with
  `duplicate key value violates unique constraint
  "content_studio_backups_backup_pkey"`. Emptying the database reset the
  id sequences, and the backup and restore records put back kept their
  ids. The sequences now move past them again. On a site that already
  restored, each failed backup moved the sequence on by one, so it heals
  by itself, or right away with `manage.py sqlsequencereset
  content_studio_backups | manage.py dbshell`.

## 1.18.0 (2026-11-20)

### Features

- **Restore a backup on the Backups page.** Each finished backup has a
  Restore button, and **Restore from a file…** uploads one. The dialog
  shows what the file holds and whether its migrations match, backs up
  the current data first (shown as *Before restore*), and asks for the
  database's name and your password. The restore runs as a Django task;
  the page shows it running and lists the latest restores. Override
  `has_restore_permission(request)` on the admin site to decide who may
  restore (superusers by default), and set `BACKUP_UPLOAD_MAX_SIZE` to
  limit uploads (1 GB by default).
- **Restore files made with `dumpdata`**, on the page and with
  `content_studio_restore`: `.json`, `.json.gz`, `.json.bz2`, `.json.xz`
  and `.json.lzma`. Content type and permission ids are matched by name,
  so a plain dump without `--natural-foreign` loads too.
- `content_studio_restore` backs up the current data before it restores.
  `--no-safety-backup` skips it.

### Fixes

- `content_studio_restore` failed on a plain `dumpdata` file: a `.json`
  file was read as gzip, and a `.json.gz` one clashed with the
  permissions migrate makes.

### Security

- **Backups could be downloaded by anyone who guessed the time.** With
  the default `BACKUP_STORAGE` (the media storage) and a web server that
  serves `MEDIA_ROOT`, a backup was public under a name made of the time
  it started, such as `2026-11-21T030000Z.json.gz`, a few seconds after
  the 03:00 schedule. A backup holds every password hash and two-factor
  secret. Three changes:
  - Each backup's name now ends in a random token
    (`2026-11-21T030000Z-<32 hex characters>.json.gz`), so it cannot be
    guessed. Backups made before keep their names: move them out of a
    served folder, or delete them.
  - A backup storage that may be public is now the error
    `content_studio.E052` instead of the warning `content_studio.W027`:
    a file system storage inside `MEDIA_ROOT`, or an object storage with
    a public ACL or unsigned URLs. **Projects that install
    `content_studio.contrib.backups` with the default storage now fail
    `manage.py check`** until they set `BACKUP_STORAGE` to a private
    storage, or silence `content_studio.E052` because their web server
    refuses the backup folder. W027 is retired.
  - Password reset codes are left out of backups, so a backup never
    holds a code that still works.

- **File fields accepted HTML files.** A `FileWidget` upload was only
  refused when its content started with `<`, so an editor with add or
  change permission on a model with a file field could upload
  `page.html` with text before a `<script>`. Served from the admin's
  domain, it ran in the session of whoever opened it, a superuser
  included. Now:
  - The new setting `UPLOAD_ALLOWED_EXTENSIONS` limits FileWidget uploads
    to a list of types, by default the media library's list (images,
    audio, video, PDF, office documents, CSV and text). **File fields
    that take other types, such as `.zip`, need them added**, for
    example `[*DEFAULT_ALLOWED_EXTENSIONS, "zip"]` from
    `content_studio.settings`, or `None` for every type.
    `content_studio.E014` checks it.
  - HTML, SVG, XML (RSS and every `+xml` type), JavaScript, CSS and the
    other types a browser runs are always refused, in file fields and in
    the media library, even when the allowed extensions are `None`, and
    under any of a name's extensions (`page.html.gz`).
  - A picked file waits in `UPLOAD_FOLDER` under a name without an
    extension, and gets its own name when the object is saved.
  - The Deployment page advises `X-Content-Type-Options: nosniff` for
    media files.

- **Staff could take over accounts with more permissions.** An editor
  with `change_user` could set the password, send a password link, reset
  the two-factor login or change the email of any account that was not a
  superuser's, such as a manager holding every permission, and then sign
  in as them. These four now need the editor to outrank the account: a
  superuser does, anyone else only when the account is not a superuser
  and holds no permission they lack (their own or a group's, active or
  not). Otherwise the email is read-only and the actions are not offered.

- **Staff could lock out every superuser.** With `change_user` or
  `delete_user`, a staff member could deactivate, revoke staff status from
  or delete every superuser. On an account they do not outrank (see
  above), `is_active` and `is_staff` are now read-only and deleting is
  refused, one by one and in bulk. This is part of `ModelStudio`'s
  `has_delete_permission`, so a user studio that overrides it should call
  `super()`.

- **A stolen session could take over the account.** The profile changed
  the email address with no password, after which a password reset to
  the new address set a new password, and turning on two-factor login
  needed no password either, which locked the owner out. Both now ask for
  the current password (users without a usable password are not asked),
  and the old address gets an email when the email changes. Wrong
  passwords count toward `LOGIN_THROTTLE_RATE`, like the password change.

- **An import file could exhaust the server's memory.** Imports read and
  parsed the whole file (up to `UPLOAD_MAX_SIZE`, 50 MB) before checking
  `IMPORT_MAX_ROWS`, so a small, highly compressed Excel file or a huge
  JSON list kept a web process busy for a long time. Reading now stops at
  the first row too many, files with more than 1,000 columns or deep JSON
  nesting are refused, and an Excel file may unpack to at most ten times
  the size limit. Two new settings: **`IMPORT_MAX_SIZE`** (10 MB) replaces
  `UPLOAD_MAX_SIZE` for imports, and **`IMPORT_FILE_MAX_ROWS`** (100,000)
  caps imports that run as a task, which had no row limit.

- **Uploads waiting to be saved sat in the public media storage.** Files
  picked in a `FileWidget` and import files are now kept in the new
  **`UPLOAD_STORAGE`** (an alias in `STORAGES`, by default `"default"`);
  the Deployment page advises a private one. Closing the import dialog
  after a background check now removes the checked file at once, instead
  of leaving it until `content_studio_clear_uploads` runs.

- **Rich text links could reveal the URL of any object.** The linked
  model and id come from the editor's HTML, and rendering resolved them
  on any installed model, without tenant scoping or a permission check:
  an editor could link to an unpublished object, or another tenant's,
  and the public page showed its URL. Rendering now only resolves models
  with a linkable studio, and saving refuses new links to objects the
  editor may not view.

- **View on site linked any URL.** The button used the URL from
  `get_absolute_url()` or `view_on_site` as it was, so a value built from
  stored data could be a `javascript:` URL that ran in the admin when
  another editor clicked it. The server and the browser now only link
  `http`, `https`, `mailto` and relative URLs, and hide the button
  otherwise.

- **The public admin page named the version and DEBUG.** The page every
  visitor gets, signed in or not, set `window.DCS_VERSION`, loaded its
  files with `?v=<version>`, and set `DCS_DEBUG` and `DCS_DEVTOOLS` while
  `DEBUG` was on. Its files are now cache-busted with a token made from
  the version and the `SECRET_KEY` (`window.DCS_ASSET_TOKEN`), and the UI
  showcase and the developer tools learn they are on from `discover`,
  behind sign-in.

- **Save and restore errors showed the database's text.** When a save or
  a restore broke a database constraint, the editor saw the database's
  message, with constraint names and sometimes values. Editors now see
  a plain conflict message; the details go to the `content_studio.viewsets`
  log (and the developer tools while `DEBUG` is on).

- **Wrong passwords were only limited per IP address.** Guessing one
  account's password from many addresses was not slowed down. Wrong
  passwords are now also counted per username, under the new
  **`LOGIN_ACCOUNT_THROTTLE_RATE`** (default `"20/hour"`, `None` turns it
  off): once it is reached, that username cannot log in until the hour
  has passed, not even with the right password. A malformed login rate is
  the new check error `content_studio.E053`.

- **Docs**: the Developer tools page warns that every staff user sees the
  same tracebacks and SQL, and advises `DEVTOOLS = False` on staging sites
  that run with `DEBUG`. The Authentication page says which secrets are
  stored readable (two-factor app secrets and live password reset codes).

### Changes

- **List pages: the toolbar sits on the list.** Search, filters, the
  list view's sorting and the table/list toggle moved from the page
  header onto the card that holds the list, so the header is one bar
  with the title and the actions, and the controls stay in place when
  switching between the table and the list view. Filters with a value
  show as chips ("Status is Published", with a clear button); the
  others are picked from a **Filter** menu, which opens the chosen
  filter's options right away. The count of matching objects moved
  from the title to the toolbar.

## 1.17.0 (2026-11-20)

### Features

- **View on site.** When a model has `get_absolute_url()`, the edit page
  header shows a "View on site" button that opens the object's public page
  in a new tab, as in the Django admin. Like Django, a studio sets
  `view_on_site = False` to hide it, or a `view_on_site(obj)` method that
  returns the URL (`None` hides it for that object). By default it follows
  the studio's `get_link_url`, so a headless site that overrides it for
  rich text links gets the right page here too. System check
  `content_studio.E045` reports any other value.

- **German, French, Spanish, Italian and Brazilian Portuguese.** The
  admin is translated into five more languages, next to English and
  Dutch: the interface, the date picker, Content Studio's field labels and
  errors, and the invite, password and reset emails. The new translations
  have not yet been reviewed by native speakers; corrections are welcome.
  The 11 strings the Dutch catalog was missing are translated too.

- **One language for the whole admin, and a language picker.** Content
  Studio now picks the editor's language for its own URLs: the choice in
  the new **Language** item of the user menu (Django's language cookie),
  then the browser's languages, then `LANGUAGE_CODE`, then English, limited
  to the project's `LANGUAGES`. The menus and the labels and errors from
  Django now always match: before, the interface followed the browser
  while Django followed `LANGUAGE_CODE` (or `LocaleMiddleware`), so a Dutch
  browser on an English project mixed the two. No `LocaleMiddleware` is
  needed, and the rest of the project is not affected. Emails sent from the
  admin, such as invites, follow the editor's language. The picker shows
  when the project allows more than one of the admin's languages. A new
  docs page, Languages, covers it.

- **Save and add another, and a save shortcut.** The edit page's Save
  button has a menu with "Save and add another", which opens an empty
  create form, and "Save and close", which goes back to the list, like the
  classic Django admin's buttons. Save itself still keeps you on the
  object. A message says what was saved, with a link to open it. Save and
  add another needs add permission; singletons and dialogs keep a single
  Save button. ⌘S on macOS, or Ctrl S elsewhere, saves from anywhere in the
  form, also inside a dialog, instead of opening the browser's "Save page".

- **Preferences on the profile page.** The new optional
  `content_studio.preferences` app adds a Preferences card to the profile's
  edit tab, kept on the account so it follows the editor to every device.
  Its first setting is the default save action: what the edit page's Save
  button does (Save, Save and add another or Save and close), with the
  others in the menu next to it. ⌘S or Ctrl S always saves and stays.
  Without the app the button saves, as before. Run `manage.py migrate`
  after adding it.

- **System status page.** The new `content_studio.contrib.status` app adds
  a System status page to the user menu, for superusers. It shows the
  services the site depends on with their status (the databases, the
  cache, the media storage, the task queue, outgoing email and the
  migrations are checked out of the box), the tasks that are queued,
  running or finished, and the recurring tasks with their latest and next
  run. Other apps add to it from `AppConfig.ready()` with
  `status.register_service()`, `status.register_task_adapter()`,
  `status.register_recurring_task()` and `status.register_task()`. The
  services are checked when the page opens and on Refresh, side by side
  with a time limit each, and the results are kept for
  `STATUS_CACHE_TIMEOUT` seconds (60). A dot on the avatar and the menu
  item shows while a service is degraded or down. Huey's queue shows
  without setup when Huey is installed. Task adapters gain the optional
  `get_pending_tasks()` and `get_health()`, `TaskStatus` gains `QUEUED`,
  and a `TaskRow` can carry a `key`, a `source` and a `schedule`.
  `has_status_permission()` on the admin site decides who may open the
  page, and system check `content_studio.E047` reports malformed
  registrations.
- **Automatic database backups.** The new `content_studio.contrib.backups`
  app backs up the database on a schedule: a gzipped Django fixture (the
  JSON `dumpdata` writes, with natural keys) per database in
  `BACKUP_DATABASES`, saved in the media storage under
  `content_studio/backups` (`BACKUP_STORAGE`, `BACKUP_FOLDER`) with a
  manifest of the versions, migrations and rows per model. With Huey
  installed a periodic task runs it on `BACKUP_SCHEDULE`, a cron expression
  (`"0 3 * * *"`); otherwise `manage.py content_studio_backup` runs it from
  cron. The newest `BACKUP_KEEP` backups (14) are kept. On the system status
  page, a Database backups service shows whether the latest backup is
  overdue or failed, and the backup shows as a recurring task. Superusers
  download backups and back up now on the new Backups page
  (`has_backup_permission()` on the admin site decides who may), and
  `manage.py content_studio_restore` restores one after checking its
  migrations. `status.register_service()` gains `url`, which makes the
  service's name a link. System checks `content_studio.E050` (settings
  that cannot work), `W027` (a backup storage that may serve backups
  publicly) and `W028` (a schedule without Huey to run it).

- **Estimated counts for large tables.** Every list page ran an exact
  `COUNT(*)`, which is slow on tables with millions of rows. A studio's new
  `list_count` option takes `"estimated"` to show "About 2.3M orders" from
  PostgreSQL's query planner once a list holds more than about 100,000
  objects, or `"none"` to skip the count and show only the page number.
  Lists without an exact total page with previous and next buttons.
  Searches and filters stay counted exactly with `"estimated"`, and other
  databases fall back to an exact count. The trash, inlines and the media
  library are always counted exactly. System check `content_studio.E046`
  reports an unknown value. A list whose exact count takes longer than half
  a second logs a warning that suggests `list_count`, and shows the hint
  in the developer tools while `DEBUG` is on. Counts and page numbers on the list
  page are now grouped (460,003), and page buttons widen to fit large page
  numbers.
- **Developer tools.** While `DEBUG` is on, staff see a button in the
  bottom-right corner with the number of issues to act on: amber for
  warnings, red for errors. Its panel lists system check warnings, slow
  counts (the hint moved here from below the list), unhandled exceptions in
  the admin API with their traceback, requests that run many alike queries,
  warnings and errors of Content Studio's loggers, and failed requests and
  uncaught errors in the browser. A Requests tab shows your last 50 admin
  API requests with their time and queries, and an Info tab the page's
  studio and the environment. `content_studio.devtools.report()` adds your
  own issues. New settings `DEVTOOLS` (`False` turns them off) and
  `DEVTOOLS_LOGGERS`; system check `content_studio.E049`. Nothing is
  recorded or loaded without `DEBUG`.

- **Import from CSV, Excel or JSON.** A studio's new `allow_import` (or
  `import_fields`) adds Import to the list page. Import and Export now
  sit in a ⋯ menu next to Create, each export with its formats in a
  submenu. Editors pick a file and
  see first what it creates, updates and leaves unchanged, with the
  failing rows and their errors; then they import every row, or only the
  valid ones. Rows are matched on the primary key, or on
  `import_id_fields` such as a unique slug: a match is updated, other rows
  create objects. `import_lookups` gives relations by a field of the
  related model, such as an author's username. Rows go through the edit
  page's validation, save hooks, permissions and tenant, and are logged in
  the activity log and the history. Export for import downloads the raw
  values as an import reads them back (also as JSON), and the dialog
  offers a template. Files with at least `IMPORT_TASK_ROWS` rows (1,000)
  run as a Django task when the task backend runs in the background; in
  the request, files over `IMPORT_MAX_ROWS` rows (10,000) are refused.
  System checks `content_studio.E048` and `content_studio.W026` report
  misconfigured import options.

- **Actions that ask for values.** `@bulk_action` and `Button` take
  `fields`: the action opens a dialog with those fields before it runs, and
  the method receives the validated values as a `data` argument (`def
  assign(self, request, queryset, data)`). Model field names look and
  validate like on the edit page (widgets, choices, related object pickers
  limited to what the editor may see); `Field(name, form_field=...)` adds
  inputs that are not on the model, validated by the Django form field.
  `when=` shows a field only for some values. Errors show under the fields.
  A `Button`'s dialog starts from the object's values.

- **Row actions.** Each row of the list has a ⋯ menu with actions on that
  object: by default Delete, and Duplicate for studios with
  `allow_duplication`. The new `row_actions` attribute picks `@bulk_action`
  methods and the built-ins by name; `row_actions = []` removes the menu.
  On reorderable lists the moves join the same menu.

- **Actions on the edit page.** The new `edit_actions` attribute lists
  `@bulk_action` methods the edit page's ⋯ menu offers on the object.

- System check `content_studio.E051` reports misconfigured action fields;
  `content_studio.E007` now also checks `row_actions` and `edit_actions`.

## 1.16.0 (2026-11-16)

### Features

- **Two-factor login.** The new `content_studio.contrib.two_factor` app
  asks for a six-digit code from an authenticator app after the password.
  Editors turn it on from their profile page by scanning a QR code, and
  get ten recovery codes that each log in once without the phone. New
  setting `TWO_FACTOR_REQUIRED` (`"superusers"` or `"all"`) makes it
  required: editors without it set it up in the login card, and sessions
  that skipped the code step end at once. Admins reset it from the user's
  more actions menu, which emails the user. No session exists before the
  code is right; five wrong codes send the editor back to the password and
  `TWO_FACTOR_THROTTLE_RATE` limits wrong codes per account. Turning it on
  or off ends the editor's other sessions. Invite and password links lead
  to the code step too. `TWO_FACTOR_ISSUER` names the account in the app.
  No new Python dependency. New system check `content_studio.E044`.

- **Create related objects from a picker.** Foreign key and many-to-many
  pickers end with "New <model>", or "Create <model> "…"" once a search is
  typed. It opens the related studio's create form in a dialog, with that
  studio's layout, widgets, validation and save hooks, and the typed text
  in the studio's first search field. The saved object is chosen, and the
  rest of the form keeps its unsaved changes. A pencil next to a chosen
  foreign key, or a click on a chosen many-to-many object, edits it in the
  same dialog. It needs the related model to be registered with a studio
  and the editor's add permission (view permission to edit, read-only
  without change permission). An object the picker would not offer, such as
  one of another tenant, is created but not chosen. `ForeignKeyWidget` and
  `ManyToManyWidget` take `allow_create=False` to turn it off for a field.

- **Custom list filters and filters across relations.** `list_filter`
  takes filter classes: subclass the new
  `content_studio.filters.ListFilter` with a `title`, a `parameter_name`,
  `options` (or `get_options(request)` to build them per request) and
  `queryset(request, queryset, value)`. The list page shows a dropdown of
  the options, single or multiple choice (`multiple = True`), and only
  passes values among them. Django's own `SimpleListFilter` classes work
  unchanged. Paths across relations such as `"author__country"` filter
  with the control of their last field, with the lookups that field has.
  Only the declared paths filter, and never through the user model's
  password or a field the model's studio excludes. A `(field,
  FieldListFilter)` tuple now filters on its field. New system checks:
  `content_studio.E042` for paths that cannot be filtered on and
  `content_studio.E043` for broken custom filters; `content_studio.W005`
  now only warns about ignored entries and filter classes in tuples.

- **New login and password pages.** The login page, the password reset
  and the page an invite or a password link opens are redesigned as one
  card on a quiet page that follows the light or dark theme. Fields have
  labels and a button to show the password. The reset takes three steps
  (email, the code from the email, the new password), shows how long the
  code stays valid, can send a new code, and ends on the login page with
  a confirmation. The pages that choose a password list the rules of your
  project's `AUTH_PASSWORD_VALIDATORS`. An invite welcomes the new editor
  by name and shows the account the password is for. The login page no
  longer shows the "Remember me" checkbox and the online badge, which did
  nothing, and offers "Forgot password?" only when the password reset app
  is installed and editors log in with an email address; without it, the
  reset pages say to ask an administrator for a link.

- **Type hints for type checkers.** The package ships a `py.typed` marker,
  so mypy and Pyright check project code against Content Studio's type
  hints instead of ignoring them. The hints accept what Content Studio
  accepts: lazy translations (`gettext_lazy`) wherever text is shown,
  components such as `Callout` and `SEOPreview` in form sets, widget
  instances in `default_widget_mapping`, `Q(...) & Condition()` and
  `None` for optional arguments. Hooks a project overrides, such as
  `get_id_parts`, `get_data`, `get_url` and `handle`, are typed so an
  override with its own return value or model type is not reported, and
  `@register` keeps the studio class's type. With mypy, use the
  django-stubs plugin.

### Bug fixes

- **Filters on positive and big integer fields were missing.** A
  `PositiveIntegerField`, `BigIntegerField` or other integer field in
  `list_filter` showed no filter; it now gets the minimum and maximum.
- **Many filters pushed the list page sideways.** The filters now wrap
  onto a second row instead of widening the page.
- **Rows of fields stack on a phone.** A `FieldLayout` puts its fields
  side by side only where its card has room for them. On a phone, and in
  the sidebar, they now stack, so fields such as a user's username and
  email address no longer squeeze into narrow columns.
- **Read-only checkboxes look like checkboxes.** A read-only boolean
  field, such as a superuser's status for staff who are not superusers,
  showed as a dashed box with a check mark under its label. It now shows
  as a disabled checkbox (or switch) with its label beside it, like the
  editable fields around it.

## 1.15.0 (2026-11-15)

### Features

- **Images, tables and internal links in rich text.** `RichTextWidget`
  gets two features, `"image"` and `"table"`. Images come from the media
  library, through the picker or by pasting or dropping a file, which is
  uploaded to the library's root folder; a selected image has a placement
  (left, center, wide), a size, alt text and a caption. Tables have rows,
  columns and a header row. Links can point to an object in the studio:
  the link dialog searches the models whose objects have a URL
  (`get_absolute_url()`, or the new `ModelStudio.get_link_url(obj)`), and
  the new `link_models` and `image_sizes` options narrow the choice. The
  HTML keeps the media id and the linked object next to each URL, and the
  new `rich_text` template filter refreshes them on render, so a changed
  slug or a moved file does not break the page; a link to a deleted object
  becomes plain text. New links open in the same tab unless editors check
  **Open in a new tab**. System check `content_studio.W025` warns about
  options that cannot work.

- **Changed fields in the activity log.** Every save in the admin now logs
  which fields it changed, like the classic Django admin. The `ActivityLog`
  component shows them under each entry ("Changed Title and Body."), and
  so does the classic admin's history page.

- **History with restore.** The new optional app `content_studio.history`
  keeps a version of an object on every create and save in the admin. An
  entry on the Activity card opens its version: each field the change
  touched, text as a word diff and other values before and after. **Restore
  this version** puts the version's values in the form as unsaved changes,
  so the editor reviews them and saves, with validation, save hooks and
  permissions applying as usual. Files, read-only fields and secrets are
  not restored. Each object keeps its latest `HISTORY_MAX_VERSIONS`
  versions (default 50, `None` keeps all), and the
  `content_studio_prune_history` command removes the versions of deleted
  objects. Add the app to `INSTALLED_APPS` and run `migrate`.

- **Invite users.** Adding a user in the admin emails them an invite with
  a link to set their password, which logs them in. The add page asks for
  an email address and starts with Staff status checked; the new user has
  no password until they set one. Existing users get **Send password
  link** in the more actions menu, or **Resend invite** when they never
  logged in. Links are signed by Django's password reset token generator:
  no table or extra app, they work once and expire after
  `PASSWORD_RESET_TIMEOUT`. The emails are sent as Django tasks; links use
  `ADMIN_URL` when set, else the request's address.

- **Set a user's password.** Admins set another user's password from the
  user's edit page, with **Set password** in the more actions menu: typed
  twice, or generated to copy and pass on. The password must pass
  `AUTH_PASSWORD_VALIDATORS`, setting it logs the user out on every device,
  and it is recorded in the activity log. Until now the password was left
  out of the admin entirely. Offered to editors who may change the user,
  never for their own account (that stays on the profile page) and only by
  a superuser for a superuser.

- **Permission matrix and groups.** Permissions (a user's
  `user_permissions`, a group's `permissions`) are now picked in a matrix:
  a row per model, grouped by app, with add, change, view and delete
  columns, the model's own permissions after them, a search box, and
  toggles per row, column and app. Django's groups are registered out of
  the box (`GroupStudio`), and the default user studio (`UserStudio`) has
  an edit page laid out for users (see below) and list columns, search and
  filters. Both are in `content_studio.user_studios` to subclass; your own
  studios still take precedence. Editors who are not superusers can only
  grant or revoke permissions they have themselves, and only add users to
  or remove them from groups whose permissions they all have; the server
  refuses anything else. The new `PermissionMatrixWidget` is the default
  for many-to-many fields to `Permission`.

- **A user edit page laid out for the job.** The default user studio's
  edit page is built from the form components any studio can use. A
  **Profile** tab holds the account (username and email address) and the
  personal info, a **Permissions** tab the groups and the permission
  matrix. The sidebar shows the status on every tab (active, staff and
  superuser), the login dates and the user's activity log. Callouts tell
  what a status means: an inactive user cannot log in, only staff users
  log in to the admin, an invited user has not logged in yet (with where
  to resend the invite), and for a superuser a callout takes the place of
  the permission matrix, since a superuser has every permission. The add
  page leaves out the dates and the activity log.

### Fixes

- **The sidebar no longer covers the form on a phone.** On a narrow
  screen, or in a narrow dialog, the edit page's sidebar now sits under
  the main column instead of on top of it.

- **No empty cards and gaps on the edit page.** A component that shows
  nothing, such as the activity log on the create form or a callout
  without text for this object, no longer leaves a gap in its form set,
  and a form set that shows nothing at all no longer leaves an empty
  card.

- **Staff can no longer make themselves superuser.** Editors who are not
  superusers but may change users could set `is_superuser`, on themselves
  too, or change a superuser's email address and reset its password. For
  them `is_superuser` is now read-only, and so is a superuser's email
  address; superusers still change everything. This holds for any studio
  registered for the user model.

- **No empty Password field on users.** The default user edit page showed
  a required Password field that was never saved, so a user could only be
  created after typing a password that was then thrown away. The field is
  gone; admins set passwords with **Set password**.

## 1.14.0 (2026-11-14)

### Features

- **Save hooks.** Studios and inline studios have `save_model(request,
  obj, data, change)`, `save_related(request, obj, data, change)`,
  `delete_model(request, obj)` and `delete_queryset(request, queryset)`,
  like the classic Django admin's. The admin saves and deletes through
  them: the edit page, inline objects, the objects a duplicate copies, the
  Delete bulk action and permanent deletes from the trash. `data` holds the
  written values by field name, in place of the classic admin's form.
  Raising Django's `ValidationError` in one of them refuses the save or
  delete and shows the message to the editor, on the field when it is
  keyed by field.

- **Model validation on save.** Saving an object now runs the model's
  `clean()`, its unique checks and its `Meta.constraints`, as the classic
  Django admin does. Until now these rules were skipped, so an object that
  broke them was saved anyway, or a constraint the serializer could not
  check answered with a generic database error. An error for a field on
  the form shows under the field; an error for no field, or for a field the
  editor cannot change, shows above the form. Changes that `clean()` makes
  to the object are saved with it. Fields that are not on the form, are
  read-only or are hidden by their condition are left out of the checks.

### Fixes

- **Refused deletes on the edit page.** When a delete was refused, such
  as by objects that refer to the object with `on_delete=PROTECT`,
  Delete on the edit page did nothing. It now shows why.

- **Per-object permissions on the edit page.** The edit page only knew
  the model's permissions, so an object the studio refuses to change
  (`has_change_permission(request, obj)`) still opened with Save, and
  saving failed. The edit page now asks the studio about the object
  itself: an object the editor may not change opens read-only, without
  Save, and Delete is only offered when `has_delete_permission(request,
  obj)` allows it. Inline rows follow the inline's methods the same way.

## 1.13.3 (2026-11-11)

### Fixes

- **Filtering a nullable boolean for null.** `?field=null` (or `none`,
  `empty`) only matched the removed `NullBooleanField`, so on a
  `BooleanField(null=True)` it was compared as text. It now matches
  empty values.

- **Request bodies that are not a JSON object.** A JSON body that was a
  list, a string, a number or null, such as `[]`, made many endpoints
  answer 500 (bulk actions, relation pickers, moves, the profile,
  notifications). Every endpoint now answers 400: the body must be an
  object.

- **Models whose manager is not called objects.** A registered model
  whose only manager has another name (`items = models.Manager()`)
  stopped the project from starting. Content Studio now uses the model's
  default manager, whatever its name.

- **Restoring from the trash.** A model whose unique constraint holds
  among live objects only (a `UniqueConstraint` with a condition on the
  soft delete field) answered 500 when a trashed object was restored
  while a live object had taken its value. The restore now answers 400
  with the conflict, and the object stays in the trash.

- **Deleting media that is in use.** Deleting a media item, a selection
  of media items or a folder answered 500 when content refers to an item
  with `on_delete=PROTECT` or `RESTRICT` (on a `MediaField`, for
  example). The media library now answers 409 and names what refers to
  the item, like the content lists do.

- **List filters on numeric choices.** A list filter on an integer field
  with choices never showed a picked choice as checked, so picking it
  again added it twice ("Paid, Paid") instead of removing it. Picked
  choices are checked now, and picking one again removes it.

- **Date and time fields in another time zone.** The date and time
  picker showed the time in the browser's time zone but sent it without
  one, so the server read it in its own time zone. In a browser whose
  time zone differs from the server's, opening and closing the picker
  moved the stored time by the difference. The picker now sends the time
  with its offset, leaves the value alone when nothing changed, and
  stays empty after Clear.

- **Saving an inline row with an invalid value.** In the dialog of an
  inline row, Save with a value that cannot be saved (JSON that does not
  parse, a key used twice) closed the dialog without saving, and the
  edits were lost. The dialog now stays open and shows the field's
  message.

- **Date range filters on date and time fields.** The range ended at
  23:59 on its last day, so objects from the last minute of that day
  were left out, and the days were the server's while the list shows
  times in the browser's time zone. The range now covers the picked days
  entirely, in the browser's time zone.

## 1.13.2 (2026-11-09)

### Fixes

- **Toasts.** Toasts followed the operating system's theme instead of the
  admin's, so with a dark OS and a light admin their description was
  near-white on white. They now follow the admin's theme and use its
  colors. The text keeps a readable width: buttons that don't fit beside
  it move below it, to the right.

- **Notifications footer.** The note on how long read notifications are
  kept has a line of its own, above the links, instead of being squeezed
  into three lines beside them.

## 1.13.1 (2026-11-09)

### Fixes

- **Rich text in dark mode.** The rich text editor's text was a fixed
  dark gray, so in dark mode it was barely readable against the editor's
  background. It now follows the theme's text color, and quotes use the
  theme's muted text and border colors.

- **Long media names.** A media item whose name is long and has no
  spaces widened its form field past the edit page, pushing the Replace
  button out of sight. The name is cut off with an ellipsis, in fields
  side by side too, and in the media library's table view.

## 1.13.0 (2026-11-08)

- **Profile page.** Every editor has a profile page, opened with Profile at
  the top of the user menu. The overview shows their card (picture or
  initials, name, email address, superuser and group badges, member since,
  last login), how many objects they created, updated and deleted in a
  period against the period before, with a chart, the content they changed
  last, and their changes per model. It counts the activity log on the
  models the editor may view. The Edit profile tab saves the user model
  fields in the new `ContentStudioSite.profile_fields` (default
  `first_name`, `last_name` and `email`), without any permission on the
  user model, and changes the password in a dialog, so password managers
  leave the page alone. Changing the password logs the editor out on other
  devices and keeps them logged in where they changed it; attempts share
  `LOGIN_THROTTLE_RATE`, per user. System check `content_studio.E041`
  reports `profile_fields` entries that are not user model fields, the
  password, or fields that decide what a user may do without
  `readonly=True`.

### Fixes

- **User menu initials.** The user menu shows the initials of the first
  and last name: "Alex Morgan" is AM, not AL.
- **Users icon.** The user model's default studio showed the generic model
  icon in the menu; it now shows a users icon.

## 1.12.0 (2026-11-06)

- **Conditional fields.** `when` on a `Field`, a component, a `FormSet` or
  a `FormSetGroup` shows it only while the form's values meet a condition,
  written as a Django `Q` object: a discount code once the type is "Sale"
  (`when=Q(type="sale")`), a callout while the publication date lies ahead
  (`when=Q(published_at__gt=Now())`). The edit page applies it as the
  editor types. Conditions combine with `&`, `|` and `~`, compare with
  other fields (`F()`) and the current time (`Now()`, with an offset), and
  support the common lookups. A hidden field is not saved and not
  required: its stored value stays, which the server decides again on
  save. For rules a `Q` cannot express, subclass `Condition` and decide in
  Python, such as a house style check on the description; the admin asks
  the server as the editor types. System check `content_studio.E040`
  reports conditions on fields the form does not hold, and
  `content_studio.W024` required fields that only show under a condition.
- **Docs for AI agents.** The docs website publishes
  [`llms.txt`](https://djangocontentstudio.org/llms.txt), an index of the
  documentation, and `llms-full.txt`, every page in one file, both
  generated from the docs when the website is built. Each page is also
  available as Markdown at its address plus `.md`. An agent skill
  (`SKILL.md`) for AI coding agents such as Claude Code covers the setup,
  the main APIs and the common mistakes; the new
  [AI agents](https://djangocontentstudio.org/docs/ai-agents) page says how
  to install it.

### Fixes

- **`UmamiProvider` import.** `from content_studio.analytics import
  UmamiProvider`, as the analytics docs show it, now works. The
  `content_studio.analytics` names are listed in the public API.

## 1.11.0 (2026-11-05)

- **Year stepper in the date pickers.** The calendar of the date, date and
  time, and date range pickers has buttons to go a year back or forward
  next to the month buttons, so a date a few years away is a couple of
  clicks instead of dozens.
- **File names in the media inputs.** A media field shows the chosen
  item's name, type and size again after the page is loaded, not only
  right after picking it, so a chosen file no longer looks like an empty
  field. Clicking the thumbnail opens the item's details, where its name,
  alt text, tags, crop and focal point can be edited without leaving the
  form; fields with several items show file names on their tiles too.

### Fixes

- **Active menu item on the edit page.** A model's main menu item stays
  highlighted on its edit and trash pages, not only on its list page.

## 1.10.0 (2026-11-04)

- **`ModelStudio.get_queryset(request)`.** Override it to narrow the objects
  an editor sees: the list, the trash, exports, bulk actions, the site
  search, relation pickers, saves of relations and the single-object
  endpoints all start from it. The [access control](/docs/permissions)
  docs said per-object `has_view_permission` hid objects from lists, which
  it never did; it guards single objects, and the docs now say so.

### Fixes

- Fixed: a list filter with one value for a `range` lookup or an invalid
  regular expression answered 500; it is now a 400 like any other invalid
  filter value.
- Fixed: the system checks `E006`, `E010`, `E015` and `E022` rejected a
  model `@property` named in `table_display`, `edit_main`, `edit_sidebar`,
  `readonly_fields` or `export_fields`, although the admin shows it there;
  exports now write a property's value too.
- Fixed: the system check `W003` warned about a `MultiSelectWidget` on a
  `MultipleChoiceField`, although the field's options are its choices.
- Fixed: `DELETE .../<id>/destroy` deleted an object permanently even when
  it was not in the trash; it now answers 400 for a live object.
- Fixed: a list filter on a `DurationField` answered 500; the value is now
  parsed as a duration (`02:30:00`, seconds or ISO 8601), and 400 when it
  is not one.
- Fixed: asking the widget data endpoint for a `SpacingWidget` answered
  500; it is now 404 like an unknown widget.
- Fixed: saving an object that violates a unique constraint the form
  cannot check, such as a conditional constraint or `unique_together` with
  the tenant field, answered 500; it is now a 400 that names the conflict.
- Fixed: the media library accepted any JSON value as an item's `tags`
  (a string, an object); it now requires a list of strings.
- Fixed: an inline whose model points at its parent with a
  `OneToOneField` failed at startup (or, with `fk_name`, the `E012` check
  refused it); one-to-one fields are now accepted like foreign keys.
- Fixed: inlining the same model twice on one studio, or an inline whose
  model has no (or more than one) foreign key to the parent and no
  `fk_name`, crashed at startup before the system checks could run. The
  inline is now skipped and reported by the checks (`E038`, `E012`).
- Fixed: the system check `E005` rejected one `Button` (or other
  component) class used on two studios, although components are looked
  up per studio. IDs now only need to be unique within a studio, or within
  an inline together with the inlined model's own studio.
- Fixed: a model with two foreign keys to the tenant model made
  `/api/discover` and every request on the model answer 500; the new
  system check `E039` reports it at startup.
- Fixed: the demo's example `get_thumbnail` hook lacked the `size`
  argument the site passes, so copying it raised a `TypeError`.
- Fixed: moving an object whose `reorder_field` is unique (alone or with
  other fields, such as `unique_together` with the parent) answered 500
  with an integrity error; the keys are now rewritten in two passes.
- Fixed: the command palette offered "go to", "create" and "trash" entries
  for models that are only inlined, which led to a list page that does not
  exist; `/api/discover` now marks such models as `inline_only`.
- Fixed: an inline whose foreign key to the parent is named `page` (or
  another reserved query parameter) could not list its rows: the
  pagination parameter was read as a second parent.
- Fixed: the live duplicate check on the create form answered 403 for an
  editor with add permission but no view permission.

## 1.9.0 (2026-11-04)

- **Analytics.** Show your website's visitor statistics in the admin, from
  an analytics tool through a provider. `UmamiProvider` reads Umami Cloud
  or your own Umami server with an API key; subclass `AnalyticsProvider`
  for another tool. Add an `AnalyticsExtension` with the provider, and:
  - `AnalyticsPage`, with `AnalyticsLink` in the main menu or
    `AnalyticsUserMenuLink` in the user menu: visitors, pageviews, visits,
    bounce rate and visit duration against the period before, a chart, and
    the top pages, sources, locations and devices. The period is a preset
    (today, 7, 30 or 90 days, 12 months) or a range of dates, and top pages
    link to their objects.
  - The `Analytics` component for `edit_sidebar` (compact) or `edit_main`
    (the full report): the statistics of the edited object's page, found
    with `path_field`, `path_prefix` and `path_suffix` or
    `get_absolute_url()`.
  - `AnalyticsStatisticWidget` and `AnalyticsTopPagesWidget` for the
    dashboard.

  Reports are cached (`cache_timeout`), and every active staff user sees
  them unless you override `is_visible`. New checks: `E037` and `W023`.
- **Maps.** The new `MapWidget` picks a location on a map: click or drag
  the pin, search for an address, or type the coordinates. It stores
  `{"lat", "lng"}` in a `JSONField`, or the latitude and longitude in two
  number fields (`lng_field`). The map (Leaflet) is loaded only on pages
  that have a map field. New settings: `MAP_TILE_URL`,
  `MAP_TILE_ATTRIBUTION` and `MAP_GEOCODER_URL`; by default the map uses
  OpenStreetMap's tiles and Nominatim.
- **Embeds.** The new `EmbedWidget` takes the URL of a video, song or post
  on YouTube, Vimeo, Spotify, SoundCloud and other oEmbed sites and shows
  its title and thumbnail, fetched by the server from the site. New
  setting: `OEMBED_PROVIDERS`.
- **SEO preview.** The new `SEOPreview` component shows how the object
  would look in a search result, from the title, description and slug
  fields as the editor types, and notes a title or description that search
  engines would cut off.
- `ContentListWidget` rows can be plain rows without a model and ID and
  show a `value`, and the widget takes a `view_all` link.

### Fixes

- With a manifest static files storage, such as Django's
  `ManifestStaticFilesStorage` or WhiteNoise's
  `CompressedManifestStaticFilesStorage`, and `DEBUG = False`, every
  admin page returned a server error ("Missing staticfiles manifest entry
  for ''"). The admin now finds its static files from `STATIC_URL`.

## 1.8.0 (2026-11-04)

- **Number formats.** `NumberFormat` now groups digits in the editor's
  language (45,940) and shows 0 instead of an empty cell. It takes
  `decimals`, `compact=True` (45.9K, exact on hover), `prefix` and
  `suffix`. The new `CurrencyFormat("EUR")` shows amounts and
  `PercentFormat` percentages (`fraction=True` reads 0.91 as 91%).
- **Badges.** The new `BadgeFormat(colors={...})` shows a value as a
  colored badge with its choice's label, in `"gray"`, `"blue"`, `"green"`,
  `"yellow"`, `"red"` or `"purple"`.
- **Links.** `URLField` values show as links that open in a new tab
  (`LinkFormat`) and `EmailField` values as `mailto:` links
  (`EmailFormat`). A click on a link opens the link, not the row.
- **Related objects.** `ManyToManyField` values show as chips
  (`ManyToManyFormat`). Tags show as pills and many-media fields as a
  stack of thumbnails; each list shows the first three, then "+N".
- **Rich text.** `HtmlFormat` shows a plain-text excerpt on the list page
  and the formatted text in a read-only field, keeping only the rich text
  editor's formatting.
- **Dates.** `DateFormat(style=...)` and `DateTimeFormat(style=...)` take
  `"short"`, `"medium"` (the default) or `"long"`, in the editor's
  language. `DateTimeFormat` shows the exact time on hover, and
  `relative=False` shows it instead of "3 hours ago".
- **Radio buttons.** `RadioButtonWidget` now shows a field's choices as
  radio buttons; it used to show a read-only value.
- **Email, URL and phone fields.** `EmailField` and `URLField` get
  `EmailWidget` and `URLWidget`, with a button that writes to the address or
  opens it. `PhoneWidget` shows phones the number pad.
- **Files.** `FileField` and `ImageField` can now be edited with the new
  `FileWidget`: a picked or dropped file is uploaded right away and attached
  when the editor saves. Run `manage.py content_studio_clear_uploads` daily
  to remove uploads that were never saved. New settings: `UPLOAD_FOLDER`
  and `UPLOAD_MAX_SIZE`. In the API, a file field's value is now
  `{"name", "url"}`.
- **Secrets.** The new `PasswordWidget` masks a value, with a button that
  shows it. With `write_only=True`, the value never leaves the server and
  is left out of exports.
- **Sliders and durations.** The new `SliderWidget(min_value, max_value)`
  picks a number on a slider. `DurationField` gets `DurationWidget`, with
  boxes for hours, minutes and seconds (and days with `show_days=True`).
- **Character counter.** Text fields with a `max_length` show a counter
  once the text nears the limit. `show_count` turns it on or off, and
  `recommended_length` sets a soft limit it warns about.
- **Long text.** `TextField` columns show two lines on the list page, with
  the full text on hover. `TextFormat(max_length=..., lines=...)` sets it
  for any column.
- **More formats.** `DurationField` values read as "1h 20m"
  (`DurationFormat(style=...)`), `UUIDField` values show in a monospace
  font with a copy button (`CodeFormat`), and `ImageField` values as a
  small thumbnail (`ImageFormat`). The new `ProgressFormat(max_value=100)`
  shows a number as a meter. `BooleanFormat(labels=..., colors=...)` shows
  words or badges instead of a check and a dash.
- **JSON fields.** `JSONField`s can now be edited: `JSONWidget` is a JSON
  editor with syntax highlighting. JSON that does not parse is underlined
  and keeps the form from saving. They used to show `[object Object]`.
- **Code.** The new `CodeWidget(language=...)` is a code editor with line
  numbers, highlighting CSS, HTML, JavaScript or JSON. The editor is
  loaded only on pages that have a code or JSON field.
- **Markdown.** The new `MarkdownWidget` edits Markdown as text, with a
  formatting toolbar and a Preview tab.
- **More widgets.** `IconPickerWidget` picks a Phosphor icon from a
  searchable grid and saves its class (`"ph-bold ph-star"`).
  `ListWidget` edits a `JSONField` list of strings as rows that can be
  dragged into order. `KeyValueWidget` edits a dict of strings as rows;
  those rows have no order, since PostgreSQL sorts a JSON object's keys.
  `RatingWidget(max_value=5)` shows a small integer as stars.
- In the API, an `ImageField`'s value now also has a `"thumbnail"`.
- **Fixed:** text columns showed `0` and `false` as empty.

## 1.7.0 (2026-11-03)

- **Colors.** The new `ColorField` stores a CSS color in the notation set
  with `color_format`: `"hex"` (the default), `"rgb"` or `"hsl"`.
  `alpha=True` allows transparent colors and saves every color with its
  alpha. Colors in any of the three notations are accepted and converted
  to the field's on save; anything else is rejected. `ColorValidator`
  validates colors on any field, in one notation or all three.
- **Color picker.** `ColorPickerWidget`, the default widget of `ColorField`,
  shows a swatch that opens a color picker, with a transparency slider
  when the field allows it. `show_input=False` leaves out the text input
  next to the swatch, and `swatches` offers preset colors, such as a brand
  palette. On the list page, `ColorFormat` shows a swatch next to the
  value.

- **Text components.** The new form components `Title`, `Subtitle`, `Text`
  and `Callout` show information on the edit page, between the fields of
  `edit_main`, `edit_sidebar` and form sets. `Text` and `Callout` take
  Markdown (bold, italic, links, lists; HTML is not rendered). A `Callout`
  has an optional `title`, a `variant` of `"info"`, `"success"`,
  `"warning"` or `"danger"` with a matching icon, and an optional `icon`.
  Override `get_text(obj, request)` to show text computed for the object.
  System check `content_studio.E020` reports text components in
  `edit_header`.

- **Dashboard statistics.** `StatisticWidget` shows its number compact
  and in the editor's language (45.9K, 1.2M), with the exact value on
  hover. Set `number_format` to `"full"`, `"percent"` or `"currency"`
  (with `currency`, such as `"EUR"`) to show it otherwise. The value may
  now be a decimal. New optional fields: an `icon`, a `footnote`, a
  `trend_label` such as "vs last month", a `series` drawn as a sparkline
  and a `max_value` drawn as a meter. The trend shows as a colored pill.
- **Dashboard lists.** Items of a `ContentListWidget` take an optional
  `status` badge (colored by `status_variant`), a `thumbnail` and a
  `timestamp`, shown relative to now. The activity log groups changes by
  day and marks each kind of change on the avatar, and the notifications
  widget shows the unread count with a button to mark all as read.

- **Menu icons.** The icons of the main menu are hidden from screen
  readers, so an icon font glyph no longer ends up in a menu item's name.
  In the collapsed menu, each item is named by its label.

### Fixes

- In dark mode, the backdrop behind dialogs and the command palette
  lightened the page instead of dimming it. It now dims in both themes.
- The command palette and the fields of a block start model names and
  field labels with a capital letter, like the rest of the admin
  ("Media items", not "media items").
- A `BlockField` no longer grows past its card when a collapsed block's
  summary is long.

## 1.6.0 (2026-11-02)

- **Image sizes.** The new `IMAGE_SIZES` setting names the sizes every media
  library image is also made in, for your site and other consumers: a
  `width` and/or `height`, a `fit` of `"contain"` or `"cover"` (filled
  around the focal point), a `format`, `quality` and `upscale`. With the
  `images` extra installed, a Django task makes them after an image is
  uploaded, replaced, cropped or reset, and makes the cover sizes again when
  its focal point moves. They are saved under the new `IMAGE_SIZE_FOLDER`
  (`"content_studio/sizes"`) and recorded in the item's metadata; replaced
  sizes and those of deleted images are removed.
  `content_studio.media_library.sizes.get_image_sizes` and the `image_size`
  and `image_url` template tags return them; a size not made yet is the
  image's own file with `ready` set to `False`.
  `content_studio_image_sizes` makes missing and out-of-date sizes
  (`--all` makes every size again) and removes sizes no longer configured.
  System check `content_studio.E033` reports an invalid size and
  `content_studio.W022` sizes set while none can be made.

- **Notifications (backend).** The new optional app
  `content_studio.notifications` notifies editors about changes made in the
  admin. Without a choice of their own, editors hear about updates,
  deletions and restores of the objects they created; they can subscribe to
  an event on every object of a model, or follow one object to hear about
  every change to it. Nobody is notified about their own changes, or about
  models they may not view. A bulk action writes one summary per editor, and
  an unread notification is bumped rather than repeated when the same object
  changes again. A studio opts a model out with `notifications = False`.
  `register_event` adds events of your own, and `notify` sends them to their
  subscribers or to given users and groups.
- **Pruning notifications.** `content_studio_prune_notifications` removes
  read notifications older than the new `NOTIFICATION_RETENTION` setting
  (90 days by default), unread ones older than
  `NOTIFICATION_UNREAD_RETENTION` (`None` by default, which keeps them),
  and follows and subscriptions of objects and models that no longer
  exist. System check `content_studio.E030` reports a retention that is not
  `None` or a positive whole number of days, and `content_studio.E031` an event registered with a
  malformed key or twice with different definitions.

- **Notifications in the admin.** With `content_studio.notifications`
  installed, the main menu shows **Notifications** with the number of unread
  ones. It opens a list with Unread and All tabs, where editors open a
  notification, mark it as read or mark all as read; on narrow screens it
  opens as a page. New notifications appear as toasts, at most three at a
  time and never the ones there when the admin loaded. The admin asks for
  them every 30 seconds while its tab is visible.
- **Notification settings.** A settings page lets editors choose per model
  which changes notify them, about every object or the ones they created;
  turn the registered events on and off (required ones stay on); stop
  following objects; and turn toasts off in their browser. Changes are
  saved as they are made.
- **Follow.** The edit page's header has a Follow button: following an
  object notifies the editor about every change to it.
- **One polling tab per browser.** With several tabs of the admin open, one
  visible tab asks for new notifications and shares the answer with the
  others; marking notifications as read in one tab updates them all.
  Browsers without `BroadcastChannel` or Web Locks keep polling in every
  visible tab.
- **Notification defaults.** Override
  `ContentStudioSite.get_default_subscriptions(user)` to set what editors
  get before they choose, per model (which changes, about every object or
  their own) and per registered event, for example per group. An editor's
  own choice always wins, and the settings page shows the defaults.
- **Webhook failures notify.** With both apps installed, a webhook delivery
  that fails after its last attempt notifies the editors who may change the
  webhook (event `webhooks.delivery_failed`, on by default). A webhook that
  keeps failing bumps its unread notification.
- **Notifications widget.** `NotificationsWidget` shows the editor's latest
  notifications on a dashboard, with the unread count. System check
  `content_studio.W021` reports it on a site without the notifications app.
- **Notification email digest.** With `NOTIFICATION_EMAIL_DIGEST` on and the
  new `ADMIN_URL` setting set to the admin's address,
  `content_studio_send_notification_digest` emails each editor the
  notifications they left unread for an hour (`--delay` changes it), once,
  in one email with links to the admin. Editors turn it off on their
  notification settings page. The email's templates can be overridden.
  System check `content_studio.E032` reports a malformed
  `NOTIFICATION_EMAIL_DIGEST` or `ADMIN_URL`, or the digest without
  `ADMIN_URL`. Run `manage.py migrate` for the notifications app's new
  migration.
- **Notifications page filters and search.** The notifications page filters
  by model and event and searches the object's name, the text, the named
  objects and who made the change. The filters are kept in the address.
- **Dutch translations.** The notifications strings (models, digest email,
  admin UI) and other untranslated strings are translated into Dutch.
  The reset-code label on the password reset page now shows its English
  text instead of its key.

## 1.5.0 (2026-11-02)

- **Task dashboard.** `TaskDashboard` is a dashboard page with the state of
  a task backend: statistics such as queued, running and failed tasks, the
  periodic tasks and the latest runs. It works with any backend through a
  `TaskAdapter`. Only superusers see it by default. Its widgets,
  `TaskStatisticWidget` and `TaskListWidget`, also work on other
  dashboards. The demo project has one with made-up data. An adapter
  reports setup problems as system check warnings through `check()`.
- **Huey adapter.** `content_studio.contrib.huey.HueyAdapter` shows a Huey
  queue on the task dashboard: its counts, periodic tasks and latest runs,
  recorded by Huey's stats app. Install it with the `huey` extra. Without
  the stats app, system check `content_studio.W020` warns that runs are not
  shown.
- **Dashboard pages.** The new `DashboardPage` extension adds a page to
  the admin with a dashboard of its own: a `path`, a `title`, an optional
  `description` and a `Dashboard` with its widgets. `is_visible(request)`
  decides who sees the page, and its widgets load their data only for
  them. Widget IDs must be unique across the start page and the dashboard
  pages (`content_studio.E004`); system check `content_studio.E028`
  reports a path that one of the admin's own pages uses.
- **Widget refresh.** A dashboard widget's `refresh_interval` reloads its
  data every so many seconds while it is shown. System check
  `content_studio.E029` reports an interval that is not a positive number.
- **User menu extensions.** `UserMenuLink` and `UserMenuButton` add links
  and buttons to the user menu, between the theme and logging out. They
  take the same options as `MainMenuLink` and `MainMenuButton`.
- **Hiding links.** Links take `is_visible(request)`, like buttons: a
  subclass that returns `False` hides the link from that user.
- **External links open in a new tab.** Menu links whose `url` starts with
  `http://` or `https://` open in a new tab; paths stay in the admin.
- **Thumbnails.** With the `images` extra installed, Content Studio makes
  thumbnails of media library images in two sizes: small (fits 480
  pixels) for the media library, pickers and list pages, and large (fits
  1600 pixels) for the cover image widget, cropping and the focal point.
  They are WebP images saved in the image's own storage, in the folder
  set by the new `THUMBNAIL_FOLDER` setting (`"content_studio/thumbnails"`
  by default; `None` turns them off). They are made when an image is
  uploaded, replaced or cropped, or first shown, and removed with it.
  Without Pillow, the admin shows the image file itself.
  `manage.py content_studio_thumbnails` makes the thumbnails of the images
  you already have. Which thumbnails exist is remembered in the cache set
  by the new `THUMBNAIL_CACHE` setting (`"default"` by default); system
  check `content_studio.E027` reports an alias that is not in `CACHES`.
- ⚠️ **Breaking:** the site's `get_thumbnail` hook takes the size:
  `get_thumbnail(obj, size="small")`, where `size` is `"small"` or
  `"large"`. Add the argument to your override.
- **Image cropping, built in.** With the `images` extra installed and a
  `metadata` field on the media model (the built-in `Media` model has one),
  editors can crop images without a `crop_image` hook of your own. A crop is
  cut from the image at full size, never resized, and becomes the item's
  file; the original is kept and named in the item's metadata under
  `"crop"`, together with the crop as percentages of the original. Cropping
  again starts from the original, and **Reset to original** in the crop
  dialog puts it back. The focal point moves along with a crop or reset; a
  focal point outside a new crop moves to its nearest edge. Replacing or
  deleting the item removes the original, and
  `manage.py content_studio_media_metadata --all` keeps the crop. Your own
  `crop_image` method still replaces the built-in crop, and the new
  `reset_crop(obj)` hook undoes a crop.

## 1.4.0 (2026-11-01)

- **Widget options.** Widgets take options: pass an instance instead of
  the class, such as `Field("body", widget=widgets.TextAreaWidget(rows=12))`.
  `InputWidget` takes `placeholder`, `prefix`, `suffix` and the number
  limits `min_value`, `max_value` and `step`; `TextAreaWidget` takes
  `rows` and `placeholder`; `RichTextWidget` takes `features`, which
  limits the editor's formatting and its toolbar, and `heading_levels`;
  `DateWidget` and `DateTimeWidget` take `min_date` and `max_date`, as a
  date or a callable such as `datetime.date.today`. Invalid options raise
  an error when the studio is defined. `default_widget_mapping`,
  `default_format_mapping` and `TableColumn(format=...)` accept instances
  too, and the system checks `content_studio.E006`, `E010` and `E013`
  accept them.
- **Media metadata.** The media library stores facts read from a file
  when it is uploaded or replaced, in the media model's `metadata`
  `JSONField` (another name can be set with the new `MEDIA_METADATA_ATTR`
  setting): an image's width and height, read with Pillow (install the new
  `images` extra). The site's new
  `get_media_metadata(file, type)` hook decides what is read; override it
  to add, for example, a video's duration and frame rate. The built-in
  `Media` model has a `metadata` field (run `migrate`), and
  `manage.py content_studio_media_metadata` reads the files you already
  have. The admin shows the metadata in a file's details, and the cover
  image widget uses the stored size. System check `content_studio.E025`
  reports a misconfigured `MEDIA_METADATA_ATTR` you set.
- **Media properties.** Values editors set for some types of media are
  stored in the media model's `properties` `JSONField` (another name can
  be set with the new `MEDIA_PROPERTIES_ATTR` setting). Unlike metadata,
  properties are kept when the file is replaced, and their known keys are
  validated. The built-in `Media` model has a `properties` field (run
  `migrate`). System check `content_studio.E026` reports a misconfigured
  `MEDIA_PROPERTIES_ATTR` you set.
- ⚠️ **Breaking:** the focal point is a media property,
  `properties["focal_point"]`, and the `FOCAL_POINT_ATTR` setting is
  removed; system check `content_studio.E009` now reports it when it is
  still set. To keep your focal points, add a `properties` `JSONField` to
  your media model, copy the values into it in a data migration and remove
  the setting:

  ```python
  def move_focal_points(apps, schema_editor):
      MediaItem = apps.get_model("blog", "MediaItem")

      for item in MediaItem.objects.exclude(focal_point=None):
          item.properties = {**item.properties, "focal_point": item.focal_point}
          item.save(update_fields=["properties"])
  ```

- **The built-in `Media` model has no `crop` field.** Content Studio never
  wrote it: cropping goes through the site's `crop_image` hook, which
  decides where a crop is stored. Run `migrate` to drop the column; a
  `crop_image` method that stored crops in it needs a field of your own
  media model. `CropField` stays available for your models.
- **Cover image options.** `CoverImageWidget` takes `aspect_ratio`, such
  as `"21:9"` or `"1:1"`, for the frame's shape (16:9 when unset), and
  `min_width` and `min_height` in pixels: a smaller image gets a warning,
  and the image's size shows next to its file size.

## 1.3.0 (2026-10-30)

- **Cover images.** `CoverImageWidget` shows the image of a `MediaField`
  large, in a 16:9 frame cropped around its focal point. Editors drop an
  image on it, upload one or choose one from the media library, and edit
  the image's alt text and focal point without leaving the page; both are
  saved on the media item. Set it on a field with
  `Field("cover", widget=widgets.CoverImageWidget)`. System check
  `content_studio.W019` reports it on a field that is not a `MediaField`.
- **Thumbnails in the list view.** `list_item_display` takes a
  `thumbnail`, shown as a square on the left of each list item. It names
  an image or file field, a media field (images only) or a method or
  property that returns an image URL; `ListItemDisplay` takes it as
  `thumbnail`. Once one item on the page has a thumbnail, items without
  one show a placeholder, so the titles stay aligned.
- **Edit pages keep a readable width.** The main column of the edit page
  is now at most 800px wide, with the sidebar next to it, so fields no
  longer stretch across the screen on a studio without a sidebar. The
  dialogs of inline objects fit their editor: 848px without a sidebar,
  1192px with one. For wide content, such as inlines with many columns,
  set `edit_width = "wide"` on the studio to keep the previous width; on
  an inline studio, it widens the inline's dialogs. System check
  `content_studio.E024` reports any other value.

### Fixes

- File sizes in the media library and in media fields were shown a
  thousand times too large: a 20 KB image read as 20 MB. They now show
  the actual size.

## 1.2.1 (2026-10-30)

- **New documentation address.** The documentation moved to
  [djangocontentstudio.org](https://djangocontentstudio.org/). The links in
  the README, the package metadata and the settings error messages point to
  the new address.

### Security

- **Webhooks could reach private addresses through NAT64.** A webhook
  URL with an address in the NAT64 prefix `64:ff9b::/96`, such as
  `http://[64:ff9b::7f00:1]/`, passed the public-address check. On a
  network with a NAT64 gateway, that reaches the IPv4 address it
  embeds, such as `127.0.0.1`. These addresses are now checked on the
  IPv4 address they embed.

- **Another site could sign editors out.** A page on another site could
  clear an editor's session cookie, so they had to sign in again once
  their current session expired. Signing out now only clears the cookie
  when the request comes from the admin itself.

- **A warning for password reset emails sent during the request.**
  Without a task backend that runs Django tasks in a worker, password
  reset emails are sent during the request, which then takes longer for
  an address that has an account. `manage.py check --deploy` now warns
  about this (`content_studio.W018`).

- **Expired password reset codes answered differently.** An expired code
  that was the right one got a different error than a wrong code. Both
  now get the same error and count as a failed attempt.

- **Logging out could fail silently.** When the server could not be
  reached, the admin showed the login page although the session was not
  ended, and the next visit signed the same user back in. The admin now
  says that logging out failed and keeps the user signed in, so they can
  try again.

### Fixes

- The admin no longer stays blank in browsers that block site data, such
  as Safari with "Block all cookies". It works there without remembering
  the theme, the selected tenant and other choices between visits.
- `URLPathField` no longer accepts a value that ends with a line break,
  which was saved as a path that looks like the one without it but
  never matches.

## 1.2.0 (2026-10-29)

- **Duplicate (save as new).** A studio with `allow_duplication = True`
  offers Duplicate in the edit page's actions menu. It opens the create
  form filled in with a copy of the object; nothing is saved until the
  editor creates it, so the usual validation runs. Field values, foreign
  keys, media, block fields and plain many-to-many fields are copied. The
  primary key, read-only, excluded and non-editable fields, one-to-one
  fields and files are not. Unique slugs and URL paths get the first free
  number suffix (`spring-sale-2`), within the tenant and counting the
  trash; other unique fields start empty. The objects of the inlines in
  `duplicate_inlines` are copied when the duplicate is saved, which is
  also how a many-to-many field with a through model is copied.
  `get_duplicate_initial(request, obj)` adjusts the copy. Duplicating
  needs add permission and view permission on the object, and is not
  available for singletons. The new object's history records that it was
  duplicated, and `content_changed` reports it as created. System checks
  `content_studio.E021` (a `duplicate_inlines` entry that is not in
  `inlines`) and `content_studio.W014` (duplication options without
  effect) report misconfiguration.
- **Export.** A studio with `export_fields` (the columns, like
  `table_display`) or `allow_export = True` (the `table_display` columns)
  offers Export in the list page's toolbar. It downloads every object
  that matches the current search and filters, on all pages, in the
  current order; in the trash, it downloads the trash. The built-in
  Export bulk action, next to Delete, downloads the selected objects
  only. Exports are CSV files, streamed; with the new `excel` extra
  (`pip install "django-content-studio[excel]"`, which installs openpyxl)
  Excel files (`.xlsx`) are offered as well. Headers are the capitalized
  verbose names (or the `TableColumn` header); cells hold the displayed
  values: choice labels, the names of related objects, dates in ISO
  format, Yes or No, rich text without markup. Exporting needs view
  permission and respects the tenant, the trash and `exclude`. Values
  starting with `=`, `+`, `-` or `@` get a leading apostrophe against
  formula injection. Not available for singletons. `"export"` names the
  built-in in an explicit `actions` list. System checks
  `content_studio.E022` (`export_fields` entries that do not resolve) and
  `content_studio.W015` (export options without effect) report
  misconfiguration; `content_studio.E007` also reports a `@bulk_action`
  named `export` that shadows the built-in, and `"export"` in `actions`
  without export.
- **Duplicate warnings for combinations of fields.** The duplicate warning
  on the edit page now also covers `Meta.unique_together` and
  `UniqueConstraint`s over several fields. When the combination of values
  in the form matches another object, the warning shows under the field
  of the combination you edited last and names the other fields. Like the
  warning for unique fields, it is scoped to the tenant, counts objects in
  the trash, leaves out the object you are editing and never blocks
  saving. A constraint's `condition` is applied to both objects; a tenant
  field in the combination is left out, because only objects of the
  current tenant are compared. Functional and deferrable constraints are
  not checked, and an empty value only clashes when the constraint sets
  `nulls_distinct=False` and the database supports it.

- **Presence.** The edit page's header shows the avatars of the other
  editors who have the object open, with a tooltip naming each and
  whether they are viewing or editing it (their form has unsaved
  changes); an editing editor's avatar gets a ring in the warning color.
  The table view and the list view mark the rows of objects someone else
  has open. The admin sends a heartbeat about every 15 seconds while an
  edit page is visible and pauses while the tab is hidden; the list page
  asks for its visible page in one request on the same interval. Leaving
  the page removes the editor; otherwise the entry expires after 45
  seconds. Editors only see presence for objects they may view, within
  the tenant for tenant-scoped models; trashed objects and inlines have
  none. Presence is kept in Django's cache: on by default, turned off
  everywhere with the `PRESENCE` setting or per studio with
  `presence = False`, and stored in the cache named by `PRESENCE_CACHE`
  (default `"default"`). It locks nothing and checks nothing on save.
  System checks `content_studio.E023` (a `PRESENCE_CACHE` that is not in
  `CACHES`), `content_studio.W016` (a `DummyCache`) and, with
  `manage.py check --deploy`, `content_studio.W017` (a per-process
  `LocMemCache`) report caches presence cannot work with. A new
  `UserAvatar` component in the design system shows editors in the user
  menu, the activity logs and presence.
- **Throttles ignore a spoofed `X-Forwarded-For`.** The login and
  password reset limits used the `X-Forwarded-For` header as the client's
  address when Django REST Framework's `NUM_PROXIES` was unset (the
  default), so a client sending a different header with every request was
  never limited. Without `NUM_PROXIES`, they now count per connection
  address (`REMOTE_ADDR`) and ignore the header; with `NUM_PROXIES` set,
  the address the proxies add is used as before. Behind a proxy, set
  `NUM_PROXIES`, or all clients share the proxy's limit.
- **A remembered tenant you can no longer access is replaced.** The
  admin remembers the selected tenant in the browser. When that tenant
  was no longer yours (access revoked, or another user signed in on the
  same browser), every page failed with a permission error until you
  picked another tenant. The admin now checks the remembered tenant
  against your tenants before loading anything and otherwise opens the
  first one. Signing out forgets the selected tenant.
- **`MediaField()` and `ManyMediaField()` without a model.** Without a
  model as the first argument, both fields pointed at an app that does
  not exist, so the project failed its system checks. They now point at
  the built-in media library's `Media` model, as intended. Fields that
  name their model, such as `MediaField("blog.MediaItem")`, are
  unchanged.

- **Logins go through Django's login plumbing.** Logging in passes the
  request to `authenticate()` and sends Django's `user_logged_in` and
  `user_login_failed` signals, so django-axes and other audit tools see
  Content Studio logins and refused attempts. `last_login` is updated by
  Django's `update_last_login` receiver, as for any Django login.

- **Length limits on the login and password reset fields.** The username
  is capped at the user model's field length, email addresses at 254
  characters and passwords at 4096 characters, so a request cannot keep
  a worker busy hashing a very long password.

- **Rotating `SECRET_KEY` keeps the sessions.** Sessions are checked
  against `SECRET_KEY_FALLBACKS` as well as `SECRET_KEY`, like Django's
  own sessions, so a key rotation that keeps the old key in the fallbacks
  no longer logs every editor out. New sessions are signed with the
  current key.

- **Media files are removed from storage.** Deleting an item of the
  built-in media library models now removes its file from storage once
  the deletion is committed, also when it is deleted in bulk or with its
  folder. Replacing an item's file removes the previous file, for the
  built-in and your own media models alike. Files of items deleted
  before this release stay in storage.

- **The media library's tag options come from a distinct query.** The
  options of the tags filter were collected by loading every media
  item's tags into Python; the database now returns the distinct values.

- **`IFramePage` embeds its page in a sandbox.** The iframe gets a
  `sandbox` attribute that lets the embedded page run scripts, keep its
  origin, submit forms, open windows and offer downloads, but not
  navigate the admin away, show modal dialogs or lock the pointer, and a
  referrer policy that keeps the admin's URLs from reaching another
  origin. The new `sandbox` option takes another set of sandbox tokens,
  or `None` for no sandbox.

- **The `d` key no longer switches the theme.** The shortcut also fired
  while a select or menu had the focus. The theme is switched in the
  main menu and the command palette.

- **Relation pickers no longer refetch on every keystroke.** A foreign
  key picker listened to the whole form, so while it was open every
  change to any field fetched its options again. The picker now reads
  the form once, when it opens.

### Security

- **Buttons and bulk actions need change permission by default.** A
  `Button` or `@bulk_action` without `allowed_permissions` was available
  to everyone who could view the object or the list, so a viewer could
  run an action that changes content. Both now need change permission
  unless `allowed_permissions` says otherwise. To keep a button or
  action open to viewers, set `allowed_permissions = []`.

- **The duplicate check revealed excluded fields.** While an editor
  types, the edit page asks whether another object already uses the
  value of a unique field. The check answered for every unique field,
  including fields in the studio's `exclude`, so an editor could find
  out which values such a field holds. Excluded fields, and combinations
  that include one, are no longer checked.

- **Bulk actions ignored per-object permissions.** Bulk actions, the
  built-in Delete included, only checked the model-level permissions
  they list. A studio whose `has_delete_permission(request, obj)` refused
  an object blocked deleting it from its edit page, but not deleting it
  with the Delete bulk action; the same went for custom actions and
  per-object `has_change_permission`. A bulk action now also checks the
  permissions it lists on each selected object, and an action that lists
  none checks `has_view_permission(request, obj)`. If any selected
  object fails the check, the action runs on none of them.

- **Singletons ignored per-object permissions.** Viewing and editing a
  singleton only checked the model-level permissions. A singleton studio
  whose `has_view_permission(request, obj)` or
  `has_change_permission(request, obj)` refused the object still let
  editors view or change it. These checks now apply to singletons, as
  they do to other objects.

- **Logging out did not end the session on the server.** Sessions were
  only checked for their signature and expiry: after logging out, a copy
  of the session cookie still renewed the session, a renewed cookie left
  the previous one working, and every renewal granted another week, so
  one copied cookie gave access for as long as it was used. Logging out
  now ends the session on the server, a renewal invalidates the previous
  cookie, and a cookie presented again after its renewal ends the whole
  session. A session now also ends 30 days after logging in, however
  active (the new `MAX_SESSION_LIFETIME` setting; `None` turns it off).
  Ended sessions are recorded in the cache named by the new `TOKEN_CACHE`
  setting (default `"default"`), which must be shared across worker
  processes and servers. Sessions started before the upgrade continue and
  their 30 days count from their last renewal.

- **Relation pickers could search password hashes.** When the related
  model's studio had no `search_fields`, such as the default user
  studio, a relation picker searched every `CharField` of the related
  model, including the user model's `password`. An editor who could view
  users could recover a user's password hash piece by piece. Relation
  pickers now only search the related studio's `search_fields`; without
  them, the picker lists all objects but a search term matches nothing.
  Set `search_fields` on the related model's studio to make its picker
  searchable.

- **The login page's return path could leave the admin.** After
  signing in, the admin went to the path in the login page's `redirect`
  parameter without checking it. With the admin mounted at the site
  root, a crafted link sent a user who signed in to another site
  (`//evil.example`) or ran script in the admin (`javascript:`). The
  admin now only returns to one of its own pages and otherwise opens the
  dashboard; the return path also keeps the page's query string.

- **A slow webhook endpoint could hold a request for minutes.**
  `WEBHOOK_TIMEOUT` applied to each read rather than to the whole
  request, so an endpoint that sent its response a few bytes at a time
  kept the request open far longer. Without a task backend that runs
  deliveries in the background, that was the editor's save request, and
  "Trigger now" and "Retry" always wait for the delivery. A webhook
  request is now cut off once `WEBHOOK_TIMEOUT` has passed.

- **A media folder could be moved into itself.** Changing a folder's
  parent accepted the folder itself or one of its subfolders, which made
  the folder part of a cycle: it disappeared from the media library's
  folder tree, and deleting it cascaded through the cycle. Moving a
  folder into itself or its subfolders is now rejected with a validation
  error.

- **Inline lists could include a hidden parent's objects.** The inline
  list endpoint checked view permission on one parent but filtered on
  every parent in the request: repeating the parent filter
  (`?article=<hidden>&article=<visible>`) listed the hidden parent's
  inline objects too. Inline lists now take exactly one plain parent
  value and filter on the parent they checked; repeated or
  comma-separated values, lookups and exclusions on the parent field
  are rejected with a 400.

- **Inline objects respect their parent's permissions.** Only the
  inline's list checked that the editor may view the parent object, so
  an editor who could not see an object could still open, edit and
  delete its inline objects, and read their history. Every action on an
  inline object now requires view permission on its parent, including a
  `has_view_permission(request, obj)` that denies that one object.

- **Inline lists showed other tenants' objects.** An inline list looked
  up its parent object without the tenant, so an editor who passed the
  id of another tenant's object got that object's inline rows. The
  parent is now looked up within the selected tenant and outside the
  trash, like the parent's own edit page.

- **A rejected retry could refresh the session in a loop.** When a
  request ran into a 401, the admin refreshed the access token and
  retried the request, but did not recognize the retry as one. If the
  retry ran into a 401 as well, for example behind a proxy that strips
  the `Authorization` header, the admin refreshed and retried again for
  as long as the refresh succeeded, issuing a new refresh token every
  time. The admin now retries a request once; a second 401 ends the
  request with the error.

- **Bulk actions and relation pickers included trashed objects.** A
  bulk action ran on every selected id, so a custom action such as
  publish also acted on objects in the trash, and a relation picker
  offered trashed objects to link to. Bulk actions now only act on
  objects the list shows, and relation pickers leave out trashed
  objects when the related model's studio configures `soft_delete`.

- **Save errors that are not about fields are shown.** When saving an
  object or setting up a tenant failed for another reason than invalid
  fields (no permission, a server error), the admin asked you to fix
  the fields without marking any and hid the real reason. Only invalid
  fields are now marked on the form; any other failure shows its
  message.

- **Malformed requests caused server errors.** Several requests the
  admin never sends answered with a 500 instead of a client error. List
  filters now accept a field name with at most one lookup
  (`?title__icontains=x`, not `?title__icontains__exact=x`) and cast
  relation values to the related object's primary key type, so
  `?category=abc` is a 400. A tenant value that is not a valid primary
  key for `TENANT_MODEL` is answered like an unknown tenant, with a 403.
  A malformed folder in the media library's item and folder lists and
  folder path answers with a 404, like an unknown folder. A delete
  blocked by an `on_delete=PROTECT` or `RESTRICT` reference, from the
  edit page, the Delete bulk action or the trash, answers with a 409
  that names what still refers to the object, and records no change.

- **Every model property reached the admin.** List rows and edit pages
  carried every public `@property` of the model, including `pk` and the
  user model's `is_anonymous` and `is_authenticated`, whatever
  `exclude` and `table_display` said. A property holding a secret was
  visible to every editor with view permission, and every property ran
  for every row of every list page. Properties are now only serialized
  when the studio names them in `table_display`, `edit_main`,
  `edit_sidebar` or `readonly_fields`. Name the properties your studio
  shows there.
- **Password reset failed for some email addresses.** An address with
  `+`, `&` or `#`, such as `jane+admin@example.com`, reached the reset
  step changed or cut off, so the code sent to it was always rejected.
  The address now arrives unchanged.
- **Relation columns made lists slow.** Every foreign key and
  many-to-many column in `table_display`, and every foreign key in
  `list_item_display`, cost extra database queries for each row of the
  list and the trash. Lists now fetch those related objects along with
  the rows, like exports do.
- **The app shell and the main menu.** Every page shares one header: the
  title on the left, the page's actions on the right and, where a page
  has them, a toolbar row underneath. The main menu sits flush against
  the page, lists the model groups as headings with their models visible,
  and becomes a rail of icons when collapsed or on narrow screens. Icons
  are in the gray family; the `color` of a `ModelGroup` or a
  `MainMenuLink` is no longer shown. `ModelGroup(collapsed=True)` starts
  a group collapsed; the group of the current model always opens.
- **Tables.** The list page's table, inlines and the media library's
  table share one shape: a 40px header on the gray family with
  capitalized labels, 44px rows with a 16px gutter, the object's name
  as the only medium-weight column, numbers right-aligned in tabular
  figures, selected rows on `accent`. Booleans show a check or a dash
  in the text color instead of green and red circles; a user column
  shows the avatar with the name instead of the avatar alone. The media
  library's table uses the admin's checkboxes.
- **The list page.** Search and filters sit in a toolbar under the page
  header; a filter reads "Status is Published" once set, with an inline
  clear. Selecting rows shows a floating bar with the bulk actions
  instead of replacing the filters, in the list view as well as the
  table. The footer counts the objects and the pages; the empty states
  show an icon with the invitation to create or to clear the filters.
  A model with a trash gets "All" and "Trash" tabs under its title,
  with the number of objects in the trash, instead of a Trash button.
- **The edit page.** Form groups and inlines switch through line tabs
  instead of the pill list. Form sets are cards with a small header
  row; labels are capitalized, required fields carry a mark, help text
  sits under the control, read-only fields render as a dashed box, and
  a checkbox field shows its help text under its label. The header says
  "Unsaved changes" while the form is dirty. Inlines sit in a card with
  the title, the count and the add button in its header. The media
  picker is a row with the file, its type and size, and replace and
  remove buttons, instead of a large preview with buttons on hover.
- **The media library.** Folders are a tree on the left, with their
  counts, nested folders behind carets and "New folder" at its foot; a
  breadcrumb above the files repeats the path. Files are cards with the
  thumbnail, or the type icon and extension, on the gray family; a
  checkbox on hover selects a card or a list row for the floating bulk
  bar (move, delete), and a more button holds the file's actions. A
  file opens in a sheet from the right with its preview, Copy URL,
  Download and Move, the name, alt text and tags, and Delete in the
  footer; crop and focal point open in their own dialog from the sheet.
  An empty folder is a dashed drop zone inviting the first upload. The
  media picker in the editor shares the tree and the cards.
- **The dashboard.** The greeting is the page's title, with today's
  date under it. Every widget shares one card anatomy: a header row
  with the title, a muted description and, for a content list of one
  model, "View all"; rows separated by hairlines. The statistic shows
  its trend as a signed percentage colored by sentiment (a negative
  trend is shown too); the activity log shows an avatar, the editor,
  the action and the object with the model and the time under it; a
  scheduled task's status is a badge with a dot, or a spinner while it
  runs. Wide widgets fill the row instead of overflowing it on narrow
  screens.
- **Buttons** are lower and wider: 32px high with 14px of horizontal
  padding (`sm` 28px, `xs` 24px, `lg` 36px, icon buttons 32px), so they
  line up with the toolbar's controls.

- **`FlexField` shows its inputs.** The edit page never received the
  field's schema, so a `FlexField` showed a warning instead of an input
  per property. Inputs are labeled with the property's `title`, or its
  name when it has none.

## 1.1.0 (2026-10-27)

- **Block fields.** `BlockField` stores an ordered list of content
  blocks that editors add (also between two blocks), reorder by dragging
  or with the keyboard, duplicate and remove in the admin, to
  build a page body from predefined blocks such as text and images.
  Define a block as a `Block` subclass with plain model fields, which
  pick the widgets and validate the block's data; blocks are not models
  and need no migrations. `max_num` and `min_num` limit the number of
  blocks, relations in blocks (such as `MediaField`) are stored as
  primary keys and scoped to the tenant, and HTML in blocks is sanitized
  on save. In templates, `{% render_blocks page.sections %}` (from the
  `content_studio` template library) renders each block with its own
  template, with related objects loaded in one query per model. A block
  can have block fields of its own, one level deep, for layouts such as
  columns; editors drag blocks between those lists and the page's own.
  System check `content_studio.E018` reports misconfigured block fields.
- **Read-only fields on the studio.** `readonly_fields` and
  `get_readonly_fields(request, obj=None)` work like the classic Django
  admin's, on studios and inlines: the edit page shows the fields
  without an input, and saving never changes them. The hook receives
  the object (`None` on the create form), so a field can be read-only
  per editor or once the object exists. System check
  `content_studio.E015` reports entries that are not model fields, and
  `content_studio.W002` now also reports required fields in
  `readonly_fields`.
- **Prepopulated fields.** `prepopulated_fields` and
  `get_prepopulated_fields(request, obj=None)` work like the classic
  Django admin's, on studios and inlines: on the create form, a field
  such as a slug follows its source fields until you edit it yourself.
  Existing objects are never prepopulated. System check
  `content_studio.E016` reports misconfigurations. The slug widget now
  drops accents instead of turning them into hyphens.
- **Duplicate warnings for unique fields.** While you type a value in a
  field with `unique=True`, such as a prepopulated slug, the edit page
  checks whether another object already uses it and shows a warning
  under the field that names that object (only if you may view it).
  Saving is not blocked; Django's uniqueness validation still decides.
  Objects in the trash count, and on tenant-scoped models only the
  current tenant's objects are compared. `unique_together` and
  multi-field `UniqueConstraint`s are not checked.
- **Reordering.** Set `reorder_field` to a number field on a studio or
  inline and editors drag rows into their own order in the table view,
  the list view and inlines, with the pointer or the keyboard. A row menu
  moves an object one step up or down, or to the top or the bottom of the
  list, also across pages. `reorder_scope` orders objects within a group (inlines are
  always ordered per parent, tenant-scoped models per tenant), and
  overriding `reorder()` on the studio plugs in any other ordering
  implementation. Reordering needs change permission, is recorded in the
  object's history and is off while the list is sorted by a column or
  searched. System checks `content_studio.E017` and `content_studio.W013`
  report misconfigurations.
- **`ManualOrderModel.reorder()` is scoped and fast.** It renumbers only
  the objects that share the model's new `order_scope` fields, in a single
  update query, instead of saving every object of the model one by one.
- **`Field(readonly=True)` is enforced on save.** The edit page already
  showed these fields without an input; saving now ignores any value
  sent for them as well.
- **Buttons on the edit page.** The new `Button` component runs your
  code for the object being edited: subclass it and implement
  `handle(obj, request)`. It takes a `label`, an `icon`, a `confirm`
  question, a `destructive` style and `allowed_permissions`, and
  `is_visible(obj, request)` hides it per object. The editor sees the
  returned message as a notification; a `ButtonResult` can also carry a
  value shown once in a dialog with a copy button.
- **Webhooks in the admin.** The webhooks app registers its own studio:
  editors create webhooks, choosing events and models from lists, and
  copy the secret, which is shown once after creating and after
  **Regenerate secret**. **Trigger now** sends a request without changes
  (event `webhook.triggered`) and reports how the webhook responded. Each
  webhook shows its delivery log, read-only, with **Retry** on failed
  deliveries for one more attempt. Unsafe URLs are refused on save, and
  changes to webhooks themselves never trigger a webhook.
- **A deploy button and a webhooks widget.** `DeployButton`, a
  `MainMenuButton`, triggers the active webhooks (or the ones named in
  `webhooks`) from the main menu, for editors who may change webhooks;
  with multi-tenancy, the current tenant's and the global ones.
  `WebhookDeliveriesWidget` shows each webhook's latest delivery on the
  dashboard. Neither is added to the site by itself.
- **The scheduled tasks widget shows missing values and errors properly.**
  Tasks without a last run, a duration or a next run showed "null" or
  an invalid date; those values are now left out. A failed task shows
  its `error_message`, and the widget no longer depends on another
  widget to format its times.
- **`MultipleChoiceField` shows its options.** The admin's multi-select
  for a `MultipleChoiceField` had no options to choose from: the field's
  `options` were never sent to the admin.
- **Excluded fields stay out of the admin.** Fields in a studio's
  `exclude` are no longer sent to the admin read-only: they are left out
  of the edit page's data entirely.
- **Buttons in the main menu.** The new `MainMenuButton` extension runs
  your code from the admin's main menu: subclass it and implement
  `handle(request)`. It takes a `label`, an `icon`, a `color`, a
  `weight` and a `confirm` question, and `is_visible(request)` decides
  who sees and runs it. Its result is shown like a `Button`'s.
- **Components in the edit page's header.** `edit_header` on a studio
  places components, such as buttons, next to the save button; on an
  inline studio, in the header of the inline object's editor. System
  check `content_studio.E020` reports entries that are not components.
- **`MainMenuLink(weight=...)` orders the menu.** The weight was accepted
  but ignored; the main menu now orders its links and buttons by weight,
  lowest first, keeping equal weights in the order of `extensions`.
- **Components work in inline objects' editors.** Links and buttons of an
  inline model's own studio failed in the dialog in which an editor opens
  one of the inline's objects; they now work there, gated by the inline
  studio's permissions.
- **Read-only inlines.** Inlines follow their studio's permissions in the
  admin: without add permission there is no create button, and without
  change permission objects open read-only, deletable only with delete
  permission.
- **A message after creating.** A studio's
  `get_created_result(request, obj)` returns a message or a
  `ButtonResult` the editor sees after creating an object, with a value
  shown once in a dialog with a copy button.
- **The `content_changed` signal.** `content_studio.signals.content_changed`
  is sent after changes made in the admin are committed: creating,
  editing, deleting, restoring and reordering objects, including the
  built-in bulk delete and the media library. One request sends one
  signal with all its changes, each a `Change` with the action, the
  model, the object's pk and label, the tenant, the user and a
  timestamp. Changes that are rolled back are not sent. Custom bulk
  actions record their changes with `record_change`.
- **Webhooks.** The optional `content_studio.webhooks` app sends a
  signed POST request to a URL after changes made in the admin, for
  example to rebuild a static site. A `Webhook` chooses the events, the
  models and the tenant it fires on; one request in the admin makes one
  delivery per webhook, with all its matching changes. Deliveries are
  sent as Django tasks (directly on Django 5.2 without django-tasks),
  stored as `WebhookDelivery` with their outcome, and retried with a
  growing wait by the `content_studio_deliver_webhooks` command.
  Webhooks only reach public addresses over HTTPS and never follow
  redirects, unless the host is in the new `WEBHOOK_ALLOWED_HOSTS`
  setting. The same command removes finished deliveries after
  `WEBHOOK_DELIVERY_RETENTION` days (30 by default). New settings
  `WEBHOOK_MAX_ATTEMPTS` and `WEBHOOK_TIMEOUT`; system check
  `content_studio.E019` reports malformed webhook settings.
- **Media library changes are recorded in the history.** Uploading,
  editing, deleting, cropping and moving media items are logged in the
  activity log, like changes to content, and so are creating, renaming,
  moving and deleting folders. Deleting a folder also records the
  subfolders and media items deleted with it.
- **Bulk deletes are logged with the object's pk.** The built-in bulk
  delete and the media library's bulk delete recorded their history
  entries without the deleted object's pk.

## Unreleased

- **Readable text and visible focus in the admin.** In the light theme,
  supporting text (`muted-foreground`), text on hover fills
  (`accent-foreground`) and the `success` and `warning` colors now meet
  4.5:1 contrast; focus rings are solid and meet 3:1 in both themes. The
  dark theme's active menu item uses the mist palette instead of a stray
  blue.
- **Shadows that were missing now render.** Controls using `shadow-xs`
  (buttons, checkboxes, switches, toggles) and the few that used the bare
  `shadow` or `shadow-2xl` had no shadow at all; the theme now defines
  `shadow-xs` and those controls use the defined scale.

- **No migrations inside the installed package.** The password reset
  app did not pin its primary key type, so a project with
  `DEFAULT_AUTO_FIELD = "django.db.models.AutoField"` got a pending
  migration that `makemigrations` wrote into the installed package. The
  password reset and media library apps now pin it, and a test checks
  the shipped migrations against both settings.

- **`Link` components render.** A `Link` on the edit page showed
  nothing; it is now a text link to the URL from `get_url`, next to the
  `ButtonLink` button.
- **Dashboard widgets keep their display when renamed.** The admin chose
  a widget's display by its `name`, so a subclass with its own name
  disappeared. Built-in widgets now carry a `widget_type` for that, and
  system check `content_studio.W012` reports widgets that are not a
  built-in type.
- **The startup banner only announces newer releases.** It compared
  versions as text and announced older pre-releases as new; releases are
  now compared by version order (`packaging` is a new dependency).

### Security

A security review fixed the following issues in 1.0.0-rc.1 and the
betas. Upgrading is strongly recommended.

- **Dashboard data was readable without signing in.** The dashboard
  widget endpoint set no permission classes and fell back to Django
  REST Framework's default (`AllowAny`, unless the project configured
  `DEFAULT_PERMISSION_CLASSES`): statistics, content lists and the
  activity log were public. It now requires an active staff user, and
  the activity log widget only shows entries on models the user may
  view.
- **Non-staff users could sign in.** Login and token authentication
  only checked `is_active`, so any active account with a password got
  working tokens (what it could see then depended on its model
  permissions). Both now require an active staff user, like the Django
  admin.
- **Tokens outlived a password change.** Access and refresh tokens are
  now bound to the user's password: changing or resetting it signs the
  user out everywhere.
- **Password reset codes could be brute-forced.** Requesting a new code
  reset the failed-attempt count. Attempts now count per email across
  codes, with a one-hour lockout; the endpoints are throttled per IP
  (`PASSWORD_RESET_THROTTLE_RATE`); only active staff users can reset;
  new passwords go through `AUTH_PASSWORD_VALIDATORS`; and an email
  shared by several users no longer causes a server error.
- **Uploads were not checked.** The media library stored any file, so
  an HTML or SVG upload served from the site's domain was stored XSS.
  Uploads are now checked against `MEDIA_LIBRARY_ALLOWED_EXTENSIONS`
  and `MEDIA_LIBRARY_MAX_UPLOAD_SIZE`, and markup is rejected whatever
  its extension.
- **The model schema was public.** The interface's discovery data
  (models, fields, extensions) answered anonymous requests; it now
  requires signing in, and the public sign-in information no longer
  includes the exact version.
- **The refresh cookie could travel over HTTP** behind a
  TLS-terminating proxy. It is now `Secure` whenever `DEBUG` is off
  (`REFRESH_COOKIE_SECURE` forces either value).
- **Password reset mails are Django tasks.** Configure a task backend
  that runs them in a worker and the request only enqueues the mail, so
  its response time no longer reveals which emails belong to an account.
  Without one (or on Django 5.2 without the `django-tasks` backport) the
  mail is sent during the request, as before.
- Signing out clears the interface's cached data, so the next user in
  the same browser does not see the previous user's.
- **List filters could read fields of related models.** A foreign key
  in `list_filter` let a filter continue into the related model, so an
  editor could probe its fields, such as the password hashes of the
  users behind an `author` filter. Filters on a relation now only take
  the relation's own lookups.
- **Content could move to another tenant.** Saving an object could set
  its tenant to any tenant, including ones the editor may not access,
  and creating an object without a selected tenant was allowed. The
  tenant now always comes from the selected tenant and cannot be
  changed, relation pickers only offer the selected tenant's objects,
  and related objects from other tenants are refused.
- **Fields left out of the edit page could still be saved.** Like the
  classic Django admin's form, saving now only writes the fields the
  edit page shows: fields left out through `exclude`, or missing from
  `edit_main` and `edit_sidebar`, keep their value whatever is sent.

- **The media library was readable without permission.** Any staff
  user could browse the media items and folders. Browsing now needs the
  media model's view or change permission, like other content.
- **Password reset codes could be guessed past the attempt limit.**
  Guesses sent at the same time could each be checked before the failed
  attempts were counted, and in projects with `ATOMIC_REQUESTS` a wrong
  code was not counted at all. Attempts are now checked one at a time
  and always counted.
- **Recent activity showed other tenants' changes.** The dashboard's
  `ActivityLogWidget` listed changes to tenant content from every
  tenant. It now only shows changes to objects in the selected tenant;
  deletions of tenant content cannot be placed in a tenant and are no
  longer shown.

### Fixes

- Moving or deleting media items with an invalid item or folder is
  reported as an error instead of failing on the server.
- Editors with change permission but without add permission can use
  relation pickers again.
- Custom user models without a `username` field can be edited.
- Models whose primary key is not called `id` work in the admin.
- Malformed input, such as an invalid id in a bulk action or a
  relation, is reported as an error instead of failing on the server.
- An `ActivityLog` component no longer answers with a server error when
  requested directly.

**Upgrade notes:** only active staff users can sign in from now on;
everyone is signed out once after upgrading (existing tokens carry no
password binding); SVG and other file types outside the allowlist can no
longer be uploaded — extend `MEDIA_LIBRARY_ALLOWED_EXTENSIONS` if you
need them; and run your deployment through the new Security page's
checklist.

- **A defined public API.** The public modules declare `__all__`, and
  the new Public API docs page lists every public name, the studio and
  site hooks, the settings and the system check IDs — the surface that
  semantic versioning covers from 1.0. Everything else is internal.
  Custom widgets, formats, login backends and token backends are
  documented as not supported in v1.

- **The dashboard widget base class is `DashboardWidget`.**
  `content_studio.dashboard.BaseWidget` is renamed, so it no longer
  shares its name with the form widgets' `content_studio.widgets.BaseWidget`.
  Derived widget IDs are unchanged.

- **`list_display` means what it means in the Django admin.** The
  list view's role mapping moves to `list_item_display` (and its hook
  to `get_list_item_display`, returning a `ListItemDisplay`).
  `list_display` is now an alias of `table_display` — a studio ported
  from the classic admin keeps its columns — and system check
  `content_studio.W010` asks to rename it. A mapping in `list_display`
  is reported by `content_studio.E001`, an overridden
  `get_list_display` (no longer called) by `content_studio.W011`.
  The quickstart examples, which configured the table through
  `list_display`, now use `table_display`.

- **Docs, branding and package metadata.** The documentation site
  adopts the mist grayscale and the Content Studio logo; code samples
  use `ContentStudioSite` and `ModelStudio` (the `AdminSite` and
  `ModelAdmin` names they showed do not exist); the setup guide no
  longer claims `django.contrib.admin` must precede `content_studio`
  (it stays installed for the activity log's `LogEntry`). The package
  now ships classifiers, keywords and project URLs.

- **Django 5.2 is the minimum.** Django 5.0 and 5.1 are out of
  support and were no longer tested; the requirement is now
  `Django>=5.2,<7`.

- **No more stray console scripts.** Installing the package no longer
  adds `test`, `test-cov`, `test-verbose`, `build` and `publish`
  commands to the environment; they pointed at development scripts
  that were never part of the package.

- **Django Blueprint is merged in and deprecated.** The content fields
  (`HTMLField`, `TagField`, `FlexField`, `MultipleChoiceField`,
  `URLPathField`, `HashTagField`) and base models (`ContentModel`,
  `SingletonModel`, `SoftDeletableModel` and the other base classes)
  formerly provided by the optional django-blueprint integration now
  ship first-class in Content Studio — `content_studio.fields`,
  `content_studio.models`, `content_studio.managers`,
  `content_studio.sanitizers` and `content_studio.validators` — and are
  always mapped to their dedicated widgets and formats.

- **A built-in media library app.** `content_studio.media_library`
  ships `Media` and `Folder` models with migrations: add the app to
  `INSTALLED_APPS` and point `MEDIA_LIBRARY_MODEL` /
  `MEDIA_LIBRARY_FOLDER_MODEL` at its models. Custom media models keep
  working as before.

- **The HTML sanitizer setting moves to the `CONTENT_STUDIO`
  namespace.** `CONTENT_STUDIO["HTML_SANITIZER"]` (a callable or dotted
  import path) replaces the old `BLUEPRINT["HTML_SANITIZER"]` setting;
  unset, the built-in allowlist sanitizer applies.

- The media library focal point setting is renamed
  `FOCAL_POINT_ATTR` (formerly `FOCUS_POINT_ATTR`), and the built-in
  media library models use the `content_studio_media` and
  `content_studio_folder` tables.

## v1.0.0-rc.1

- 🎉 **The beta era closes.** Twenty-eight pre-releases (beta.1 →
  beta.28) grew Content Studio from an initial prototype into a
  complete alternative to the Django admin: a React interface over a
  generated REST backend, model registration with a widget, filter
  and format system, bulk actions, dashboards, a media library, soft
  delete, JWT authentication, multi-tenancy, internationalization
  and password reset — working with any plain Django model, with or
  without django-blueprint. No per-version backfill: the tag history
  and PyPI releases remain the record for the individual betas; the
  entries below cover everything since beta.28.

- **Media library state joins the remembered-state model.** The
  media library's view, its type and tags filters and its ordering
  are remembered per media model, like the content list's state,
  instead of the URL; the URL keeps only the folder, the search term
  and the page. Remembered values that no longer apply (an unknown
  view or file type) are dropped, and the table's headers expose
  their sort state through aria-sort.
- **List page polish.** Narrowing or re-sorting a list returns to the
  first page instead of stranding the current one; the empty state
  invites creation (permission-checked) and, while a search term or
  filters are active, shows a no-results notice that offers clearing
  them; remembered filters and ordering are validated against the
  current studio configuration so stale values are dropped instead
  of sent; and sortable headers expose their sort state through
  aria-sort with visible focus rings.
- **List filters and ordering move to local storage.** The content
  list's filters and sort are now remembered per content type, like
  the view choice, instead of living in the URL: returning to a
  content type restores them, and the URL keeps only the page and
  the search term.
- **List view sorting.** The list view no longer inherits the table's
  sorting: without a `sortable_by` declaration it always uses the
  studio's default ordering, and with one it gains a select (to the
  left of the view toggle) that sorts by exactly the declared fields,
  with a direction toggle next to it. The table view keeps sorting by
  every sortable column when `sortable_by` is absent and by exactly
  the declared columns otherwise — and the API now enforces the same
  restriction, dropping `ordering` parameters outside `sortable_by`
  instead of applying them.
- **Media library v2.** The library grows from a grid into a full
  list page: grid, list and table views behind a toggle (the table
  with sortable columns for whatever the model carries), type and
  tags filters with any-of semantics (the tags filter a
  searchable select of the tags currently on the library's items),
  and bulk actions — delete
  (confirmed) and move to folder — over a per-page selection. The
  search, filters, view and ordering all live in the URL, so any
  state is deep-linkable; the media API gains the type and tags
  filters, explicit ordering with a stable newest-first default, a
  permission-checked bulk endpoint, and folder item counts. Files
  can be dragged onto the library (per-file progress), and each
  item's context menu offers Copy URL and Download.
- 🐛 **Opening a media item crashed the editor.** The demo's media
  model declared `tags` as a plain character field while the
  interface's tags input expects a list — the item editor failed with
  "e.map is not a function". The demo now models the documented
  contract (a list-typed `tags` field, like Blueprint's `TagField`),
  the docs state the field type explicitly, and an e2e test opens an
  uploaded item so the editor cannot regress silently.
- 🐛 **Saving a media item did nothing.** Integer primary keys
  arrive from the API as JSON numbers while the editor's form schema
  treats ids as strings — the resolver rejected the id and the save
  was silently dropped, because the id has no rendered field to show
  the error. The id is now normalized at the form boundary, and the
  e2e test saves a rename through the dialog.
- **Theme colors only, and new status tokens.** The interface no
  longer uses raw palette colors: every surface rides on the theme's
  tokens, which fixes several dark mode gaps (the FK and date widget
  triggers, selects, menus, the scrollbar, tooltips and overlays now
  flip correctly). The gray scale is redefined on the theme's mauve
  family instead of Tailwind's blue-leaning default, and a `success`
  and a `warning` token join `destructive` — saturated in light mode,
  lightened in dark — carrying the dashboard's trend and status
  colors. A dark mode e2e spec pins the computed colors so raw palette
  values cannot creep back in.
- **Command palette with global search.** ⌘K (or Ctrl K, or the search
  button on the main menu) opens a palette over the whole studio:
  jump to the dashboard, the media library or any model you may view,
  create a new object in any model you may add, open a model's trash,
  switch the theme or log out — entries filter as you type. Typing
  two characters or more also searches objects across every
  registered model with `search_fields`: the same match the model's
  own list view runs, permission- and tenant-scoped, trashed objects
  excluded, capped at five results per model. Picking a result opens
  the object in the editor.
- **Soft delete and the trash.** A model studio can opt into a trash by
  naming the model's nullable timestamp field in `soft_delete`
  (django-blueprint's `SoftDeletableModel` uses `"removed_at"`).
  Deleting then stamps the field instead of removing the row — the
  bulk delete action included, with a confirm message that announces
  the trash instead of claiming the change is irreversible — the
  object disappears from the lists, and the list view links to the
  model's trash — a deep-linkable page at `/content/<model>/trash`
  where trashed objects can be restored (change permission) or
  permanently deleted (delete permission). Restoring is recorded in
  the object's history. Models without the option keep the classic
  hard delete; a misconfigured field is reported by the
  `content_studio.E008` system check.
- **Per-object history.** The activity recorded for an object — its
  additions, changes and deletions, most recent first, with the acting
  user — is available in the edit view through the `ActivityLog` form
  component: opt-in, placed like any component
  (`edit_sidebar = ["published_at", ActivityLog(title="History")]`),
  with a translated default title of "Activity". The entries come
  from the generated API's activity endpoint, gated by view
  permission on the object.
- **Filter controls for every field type on the list view.** A field
  listed in `list_filter` now renders a control that fits the field,
  instead of silently showing nothing for everything but choices:
  boolean fields get a tri-state all/yes/no filter, date and datetime
  fields a range calendar (datetime bounds cover the full picked days),
  integer, decimal and float fields a min/max range, foreign keys a
  searchable select over the related model's objects and many-to-many
  fields a searchable multi-select matching any of the picked objects.
  Choice fields keep the multi-select. Filters live in the URL as
  `filters.<field>[__lookup]` values, so filtered views are
  deep-linkable and survive the back button; everything is plain
  Django — the filtering runs through the generated API's existing
  lookup support, with no new model requirements.
- **Bulk actions on the table view.** Model studios can declare batch
  operations with the `@bulk_action` decorator (`label`, `icon`,
  `confirm`, `allowed_permissions`, `destructive`); the built-in delete
  is offered by default, gated on delete permission, and deletes
  through Django's Collector so deletion signals fire like the classic
  admin. The `actions` attribute selects what is offered (None = delete
  plus every declared action, [] disables them, an explicit list picks
  exactly those names). Selecting rows in the table view shows a bulk
  bar; selection is per page and the actions run through one endpoint,
  permission-filtered per user and tenant-scoped like any list.
  Misconfigurations are reported by the `content_studio.E007` system
  check.
- **The content editor is a route, not a dialog.** Objects open at
  `/content/<model>/<id>`, creation at `/content/<model>/new` and
  singletons on the model's index route — editor URLs are deep-linkable,
  and the browser's back and forward buttons work as expected. Saving
  keeps the editor open (after a create, the route becomes the new
  object's), and leaving with unsaved changes asks for confirmation
  (including reloads, via the browser's own prompt). Inline creation
  stays dialog-based; list state (filters, page, view) is preserved on
  the way back since it lives in the URL.
- **System check `content_studio.W001`:** required model fields missing
  from the edit form are now reported as a warning by `manage.py check`.
  A field counts as required when a save without it would fail validation
  (editable, not nullable, not blank, no default), minus the fields
  Content Studio fills itself (the created/edited stamps and the tenant
  relation) and the user model's password. Required fields dropped
  through `exclude` are reported as well; a warning is issued rather
  than an error because fields can legitimately be filled
  programmatically outside the form.
- **Table columns:** `table_display` accepts `TableColumn` objects
  alongside field names — `TableColumn(field, header, format)` sets a
  custom column header, an explicit format, and references studio
  methods (`(obj, request)` returning a JSON-safe value) for computed
  columns. Method columns render through `TextFormat` when no format
  is set, cannot be sorted (ordering is now restricted to real model
  fields — ordering by `__str__` previously raised a server error),
  and misconfiguration is reported by the `content_studio.E006`
  system check.
- ⚠️ **Breaking:** Content Studio no longer inherits from Django's
  `ModelAdmin` and `AdminSite`. The configuration classes are now
  `ModelStudio` and `ContentStudioSite` (`InlineModelStudio` for
  inlines), implementing only the surface the studio actually uses:
  list, edit, relation display and permission options. The permission
  hooks are uniform (`has_*_permission(self, request, obj=None)`), the
  `check()` workaround is gone and configuration errors surface as
  Django system checks (`content_studio.E001`–`E005`, reported by
  `manage.py check`).
- ⚠️ **Breaking:** Content Studio keeps its own registry. Models
  registered only with the classic Django admin no longer appear in the
  studio — register them with `content_studio.register`. The user model
  is registered automatically with a default studio when no custom one
  is registered.
- ⚠️ **Breaking:** `content_studio.display` (the alias of Django's
  `@display`) is removed. The admin payload no longer carries column
  labels or `empty_value` metadata; table columns render raw values
  until the upcoming display API.
- ⚠️ **Breaking:** `ModelStudio` no longer supports per-model
  `widget_mapping` and `format_mapping`. Widget and format choices live
  on the `ContentStudioSite` (`default_widget_mapping` /
  `default_format_mapping`); a dedicated override API will follow.
- The site's identity defaults (`site_header`, `site_title`) now say
  "Content Studio" instead of Django's administration defaults.
- ⚠️ **Breaking:** Content Studio now ships its own JSON Web Token backend
  and no longer depends on `djangorestframework-simplejwt`. All token
  configuration lives in the `CONTENT_STUDIO` namespace, so projects that
  use simplejwt for their own API no longer share global JWT settings with
  the admin.
- ⚠️ **Breaking:** the login response returns `{"access": ...}` only. The
  refresh token moved to an httpOnly, `SameSite=Lax` cookie scoped to the
  token endpoints and never reaches the browser; sessions restore silently
  on reload, a 401 triggers one shared refresh with a retry, and logout
  clears the cookie server-side. Outstanding sessions invalidate once.
- 🔐 New settings: `TOKEN_BACKEND`, `TOKEN_LIFETIME` (default one hour),
  `REFRESH_TOKEN_LIFETIME` (default seven days), `TOKEN_SIGNING_KEY`
  (default the Django `SECRET_KEY`) and `TOKEN_ALGORITHM` (default HS256).
- 🐛 The frontend previously sent an `Authorization: JWT` header prefix,
  which simplejwt's default configuration rejects; requests now send the
  standard `Bearer` prefix.
