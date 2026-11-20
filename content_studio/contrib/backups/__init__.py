"""
Automatic database backups: a Django fixture of each database in
BACKUP_DATABASES, gzipped, saved in the BACKUP_STORAGE on
BACKUP_SCHEDULE (by Huey when it is installed, otherwise by
content_studio_backup from cron). The newest BACKUP_KEEP are kept.

Add "content_studio.contrib.backups" to INSTALLED_APPS. With the status
app installed, the backups show on the system status page; superusers
download them, back up on demand and restore a backup or an uploaded
dumpdata file on the Backups page. The content_studio_restore command
restores one too.
"""

__all__: list[str] = []
