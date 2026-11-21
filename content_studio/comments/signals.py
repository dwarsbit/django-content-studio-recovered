from django.dispatch import Signal

# Sent after a comment is saved, once its transaction commits. sender
# is the Comment model; the arguments are comment, target (the object)
# and author (None for a comment from code without one).
comment_added = Signal()


def delete_comments(sender, instance, **kwargs):
    """An object deleted for good takes its comments along. Trashed
    objects (soft delete) keep them."""
    from django.contrib.contenttypes.models import ContentType

    from ..settings import cs_settings
    from .models import Comment

    if sender is Comment or sender not in cs_settings.ADMIN_SITE._registry:
        return

    Comment.objects.filter(
        content_type=ContentType.objects.get_for_model(sender),
        object_id=str(instance.pk),
    ).delete()
