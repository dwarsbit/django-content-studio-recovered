from django.dispatch import Signal

# Sent after an object was submitted for review, with request,
# review (the ReviewRequest) and target (the object).
review_submitted = Signal()

# Sent after a reviewer decided, with request, review and target;
# review.status is "approved" or "changes_requested".
review_decided = Signal()


def delete_requests(sender, instance, **kwargs):
    """An object deleted for good takes its review requests along.
    Trashed objects (soft delete) keep them."""
    from django.contrib.contenttypes.models import ContentType

    from ..settings import cs_settings
    from .models import ReviewRequest

    if sender is ReviewRequest or sender not in cs_settings.ADMIN_SITE._registry:
        return

    ReviewRequest.objects.filter(
        content_type=ContentType.objects.get_for_model(sender),
        object_id=str(instance.pk),
    ).delete()
