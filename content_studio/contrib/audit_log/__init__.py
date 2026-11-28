"""
Audit log: one page listing every change made in the admin (the activity
log, Django's LogEntry) together with sign-ins, failed sign-ins and
sign-outs, filterable by user, model, action, date and text, with the
field changes of each update and a CSV or Excel export.

Add "content_studio.contrib.audit_log" to INSTALLED_APPS and migrate.
Superusers open the page from the user menu; override the admin site's
has_audit_log_permission() to let others in. AUDIT_LOG_KEEP_DAYS prunes
entries older than that many days (None, the default, keeps them).
"""
