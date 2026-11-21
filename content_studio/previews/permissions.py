"""The "Can share" permission: share_<model_name>, made after migrate for
every studio that previews content (it has publishing)."""

from django.db import router


def get_codename(model) -> str:
    """The codename of a model's share permission."""
    return f"share_{model._meta.model_name}"


def get_sharing_studios(site=None) -> list:
    from . import preview_enabled
    from ..settings import cs_settings

    site = site or cs_settings.ADMIN_SITE

    return [studio for studio in site._registry.values() if preview_enabled(studio)]


def create_permissions(sender=None, using="default", apps=None, **kwargs):
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    for studio in get_sharing_studios():
        model = studio.model
        opts = model._meta

        if sender is not None and getattr(sender, "label", None) not in (
            opts.app_label,
            "content_studio_previews",
        ):
            continue

        if not router.allow_migrate_model(using, Permission):
            continue

        content_type = ContentType.objects.db_manager(using).get_for_model(
            model, for_concrete_model=False
        )
        Permission.objects.using(using).get_or_create(
            content_type=content_type,
            codename=get_codename(model),
            defaults={"name": f"Can share {opts.verbose_name_raw}"[:255]},
        )
