"""
The comment endpoints of the edit page's Comments card. Every request
names the object (model and id); the studio's has_comment_permission
on it decides who reads and writes its comments.

Internal: the admin is the only client.
"""

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from ..admin import is_comments_enabled
from ..parsers import ObjectJSONParser
from ..permissions import IsActiveStaff
from ..presence import describe_user
from ..settings import cs_settings
from ..utils import get_tenant_scoped_queryset
from .api import MAX_LENGTH, add_comment
from .models import Comment
from .notifying import notify_comment

# The @ list's length.
MAX_PEOPLE = 8
MAX_QUERY_LENGTH = 100


def get_studio_for_label(label: str):
    for model, studio in cs_settings.ADMIN_SITE._registry.items():
        if model._meta.label_lower == label:
            return model, studio

    return None, None


def may_view(user, studio, obj, tenant: str) -> bool:
    """Whether a user other than the request's may see obj's comments:
    the check notifications use for their recipients."""
    from ..admin import ModelStudio
    from ..notifications.permissions import may_receive, recipient_request

    if type(studio).has_comment_permission is not ModelStudio.has_comment_permission:
        # A studio deciding per object is asked with a request that
        # carries the user (and the tenant).
        try:
            return bool(
                studio.has_comment_permission(recipient_request(user, tenant), obj)
            )
        except Exception:
            return False

    return may_receive(user, type(obj), tenant, obj)


class CommentViewSet(ViewSet):
    permission_classes = [IsActiveStaff]
    parser_classes = [ObjectJSONParser]
    renderer_classes = [JSONRenderer]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.authentication_classes = [
            cs_settings.ADMIN_SITE.token_backend.active_backend.authentication_class
        ]

    # The object.

    def _target(self, source):
        """The object named by model and id, which the request may
        comment on, and its studio."""
        model, studio = get_studio_for_label(str(source.get("model", "")))

        if model is None or not is_comments_enabled(studio):
            raise NotFound("Unknown model.")

        try:
            pk = model._meta.pk.to_python(source.get("id"))
        except (DjangoValidationError, ValueError, TypeError):
            raise NotFound()

        obj = (
            get_tenant_scoped_queryset(self.request, model, model._base_manager.all())
            .filter(pk=pk)
            .first()
        )

        if obj is None or not studio.has_comment_permission(self.request, obj):
            raise NotFound()

        return obj, studio

    def _comment(self, pk):
        """A comment the request may see, with its object and studio."""
        comment = Comment.objects.filter(pk=pk).select_related("content_type").first()

        if comment is None:
            raise NotFound()

        model = comment.content_type.model_class()
        obj, studio = self._target(
            {"model": model._meta.label_lower if model else "", "id": comment.object_id}
        )

        return comment, obj, studio

    def _thread_of(self, comment):
        return comment.parent if comment.parent_id else comment

    # Serializing.

    def _serialize(self, comments, obj, studio):
        request = self.request
        User = get_user_model()
        user_ids = set()

        for comment in comments:
            user_ids.update(
                pk for pk in (comment.author_id, comment.resolved_by_id) if pk
            )
            user_ids.update(comment.mentions or [])

        users = {
            user.pk: describe_user(user, request)
            for user in User._default_manager.filter(pk__in=user_ids)
        }
        can_resolve = studio.has_change_permission(request, obj)
        can_moderate = request.user.is_superuser

        def one(comment):
            deleted = comment.deleted_at is not None
            mine = comment.author_id == request.user.pk

            return {
                "id": comment.pk,
                "author": users.get(comment.author_id),
                "body": "" if deleted else comment.body,
                "mentions": (
                    []
                    if deleted
                    else [users[pk] for pk in comment.mentions or [] if pk in users]
                ),
                "created_at": comment.created_at,
                "edited_at": comment.edited_at,
                "deleted": deleted,
                "can_edit": mine and not deleted,
                "can_delete": (mine or can_moderate) and not deleted,
            }

        threads = []
        replies = {}

        for comment in comments:
            if comment.parent_id:
                replies.setdefault(comment.parent_id, []).append(comment)

        for comment in comments:
            if comment.parent_id:
                continue

            mine = comment.author_id == request.user.pk
            threads.append(
                {
                    **one(comment),
                    "resolved_at": comment.resolved_at,
                    "resolved_by": users.get(comment.resolved_by_id),
                    "can_resolve": can_resolve or mine,
                    "replies": [one(reply) for reply in replies.get(comment.pk, [])],
                }
            )

        return threads

    def _threads(self, obj, studio):
        comments = list(
            Comment.objects.filter(
                content_type=ContentType.objects.get_for_model(type(obj)),
                object_id=str(obj.pk),
            )
        )

        return self._serialize(comments, obj, studio)

    def _response(self, obj, studio, status=200):
        threads = self._threads(obj, studio)

        return Response(
            {
                "threads": threads,
                "open": sum(1 for thread in threads if not thread["resolved_at"]),
                "resolved": sum(1 for thread in threads if thread["resolved_at"]),
            },
            status=status,
        )

    # Validating.

    def _body(self, data) -> str:
        body = data.get("body")

        if not isinstance(body, str) or not body.strip():
            raise ValidationError({"body": ["Write a comment."]})

        if len(body) > MAX_LENGTH:
            raise ValidationError(
                {"body": [f"A comment has at most {MAX_LENGTH} characters."]}
            )

        return body.strip()

    def _mentions(self, data, obj, studio, tenant):
        """The mentioned users the comment may name: active staff who
        may see the object's comments."""
        ids = data.get("mentions") or []

        if not isinstance(ids, list):
            raise ValidationError({"mentions": ["A list of user ids."]})

        User = get_user_model()
        valid = []

        for user in User._default_manager.filter(
            pk__in=[pk for pk in ids if isinstance(pk, (int, str))][:50],
            is_active=True,
            is_staff=True,
        ):
            if may_view(user, studio, obj, tenant):
                valid.append(user.pk)

        return sorted(valid)

    # Endpoints.

    def list(self, request):
        """The object's comment threads: GET ?model=&id=."""
        obj, studio = self._target(request.query_params)

        return self._response(obj, studio)

    def create(self, request):
        """
        Comment on an object: {"model", "id", "body", "parent"?,
        "mentions"?}. parent (a comment id) makes it a reply. Answers
        with the threads.
        """
        data = request.data
        obj, studio = self._target(data)
        body = self._body(data)
        parent = None

        if data.get("parent") is not None:
            parent = Comment.objects.filter(
                pk=data.get("parent"),
                content_type=ContentType.objects.get_for_model(type(obj)),
                object_id=str(obj.pk),
            ).first()

            if parent is None:
                raise ValidationError({"parent": ["Unknown comment."]})

        from .api import tenant_of

        mentions = self._mentions(data, obj, studio, tenant_of(obj))

        with transaction.atomic():
            add_comment(obj, request.user, body, parent=parent, mentions=mentions)

        return self._response(obj, studio, status=201)

    def partial_update(self, request, pk=None):
        """Edit your own comment: {"body", "mentions"?}. People newly
        mentioned are notified."""
        comment, obj, studio = self._comment(pk)

        if comment.author_id != request.user.pk or comment.deleted_at:
            raise PermissionDenied()

        body = self._body(request.data)
        mentions = self._mentions(request.data, obj, studio, comment.tenant)
        added = sorted(set(mentions) - set(comment.mentions or []))

        with transaction.atomic():
            comment.body = body
            comment.mentions = mentions
            comment.edited_at = timezone.now()
            comment.save(update_fields=["body", "mentions", "edited_at"])

            if added:
                notify_comment(comment, obj, request.user, mentioned_ids=added)

        return self._response(obj, studio)

    def destroy(self, request, pk=None):
        """
        Delete your own comment (superusers: any). A comment with
        replies stays as "Comment deleted"; a deleted thread whose last
        reply goes is removed with it.
        """
        comment, obj, studio = self._comment(pk)

        if comment.deleted_at or not (
            comment.author_id == request.user.pk or request.user.is_superuser
        ):
            raise PermissionDenied()

        with transaction.atomic():
            if comment.parent_id is None and comment.replies.exists():
                comment.body = ""
                comment.mentions = []
                comment.deleted_at = timezone.now()
                comment.save(update_fields=["body", "mentions", "deleted_at"])
            else:
                parent = comment.parent
                comment.delete()

                if (
                    parent is not None
                    and parent.deleted_at
                    and not parent.replies.exists()
                ):
                    parent.delete()

        return self._response(obj, studio)

    @action(methods=["post"], detail=True, url_path="resolve")
    def resolve(self, request, pk=None):
        """Resolve or reopen a thread: {"resolved": true | false}. Its
        author and anyone who may change the object may."""
        comment, obj, studio = self._comment(pk)
        thread = self._thread_of(comment)

        if not (
            thread.author_id == request.user.pk
            or studio.has_change_permission(request, obj)
        ):
            raise PermissionDenied()

        resolved = bool(request.data.get("resolved", True))
        thread.resolved_at = timezone.now() if resolved else None
        thread.resolved_by = request.user if resolved else None
        thread.save(update_fields=["resolved_at", "resolved_by"])

        return self._response(obj, studio)

    @action(methods=["get"], detail=False, url_path="people")
    def people(self, request):
        """Who can be mentioned on the object: active staff who may see
        its comments, matching ?q= (name, username or email)."""
        obj, studio = self._target(request.query_params)

        from .api import tenant_of

        tenant = tenant_of(obj)
        User = get_user_model()
        query = (request.query_params.get("q") or "")[:MAX_QUERY_LENGTH].strip()
        users = User._default_manager.filter(is_active=True, is_staff=True)

        for word in query.split()[:5]:
            match = Q(**{f"{User.USERNAME_FIELD}__icontains": word})

            for name in ("first_name", "last_name", "email"):
                try:
                    User._meta.get_field(name)
                except Exception:
                    continue
                match |= Q(**{f"{name}__icontains": word})

            users = users.filter(match)

        people = []

        for user in users.order_by(User.USERNAME_FIELD)[:200]:
            if user.pk == request.user.pk or not may_view(user, studio, obj, tenant):
                continue

            people.append(describe_user(user, request))

            if len(people) == MAX_PEOPLE:
                break

        return Response({"results": people})
