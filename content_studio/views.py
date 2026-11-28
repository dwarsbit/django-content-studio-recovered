import uuid

from django.apps import apps
from django.conf import settings
from django.contrib.auth.password_validation import password_validators_help_texts
from django.urls import reverse, NoReverseMatch
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.decorators import method_decorator
from django.utils.translation import get_language, gettext_lazy as _
from django.views.decorators.cache import never_cache
from django.views.generic import TemplateView
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from . import __version__, devtools
from .admin import AdminSerializer, ModelStudio, ModelGroup
from .exceptions import NotConfigured
from .extensions import MainMenuButton
from .languages import (
    LANGUAGES,
    get_enabled_languages,
    get_locale,
    match_language,
)
from .media_library.cropping import get_crop_hook
from .media_library.metadata import get_metadata_attr, get_properties_attr
from .media_library.sizes import get_size_specs
from .oembed import OEmbedError, fetch as fetch_oembed
from .permissions import IsActiveStaff
from .serializers import ModelSerializer, get_session_user_serializer
from .settings import cs_settings
from .signals import collect_changes
from .utils import as_instance


def asset_token():
    """
    Returns the cache key of the studio's static files: it changes with
    the version, but without the SECRET_KEY it does not tell which one.
    """

    return salted_hmac(
        "content_studio.assets", __version__, algorithm="sha256"
    ).hexdigest()[:12]


@method_decorator(never_cache, name="dispatch")
class ContentStudioWebAppView(TemplateView):
    """
    View for rendering the content studio web app.
    """

    template_name = "content_studio/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # The page is public, so it names neither the version nor DEBUG:
        # the static files are cache-busted with a token that changes
        # with the version but does not reveal it, and the debug tools
        # learn they are on from discover, behind sign-in.
        context["asset_token"] = asset_token()
        # The editor's language (content_studio.languages picked it) and
        # the ones the language picker offers.
        language = get_language()
        context["language"] = get_locale(language)
        context["languages"] = [
            {"code": code, "locale": get_locale(code), "name": LANGUAGES[code]}
            for code in get_enabled_languages()
        ]
        return context


class AdminApiViewSet(ViewSet):
    """
    View set for content studio admin endpoints.
    """

    permission_classes = [IsActiveStaff]
    renderer_classes = [JSONRenderer]
    admin_site = cs_settings.ADMIN_SITE

    def __init__(self, *args, **kwargs):
        # Forward kwargs: action-level overrides (permission_classes,
        # authentication_classes) arrive through the viewset init.
        super().__init__(*args, **kwargs)

        self.authentication_classes = [
            self.admin_site.token_backend.active_backend.authentication_class
        ]

    @action(
        methods=["get"],
        detail=False,
        url_path="info",
        permission_classes=[AllowAny],
    )
    def info(self, request):
        """
        Returns public information about the Content Studio admin: what
        the sign-in pages need, and nothing that maps the project (the
        version and the models are in discover, behind sign-in).
        """

        data = {
            "site_header": self.admin_site.site_header,
            "site_title": self.admin_site.site_title,
            "index_title": self.admin_site.index_title,
            "site_url": self.admin_site.site_url,
            "health_check": get_health_check_path(),
            # What the password pages show: the rules a new password must
            # meet, and how long a reset code stays valid.
            "password_rules": password_validators_help_texts(),
            "password_reset": get_password_reset_info(),
            "login_backends": [
                backend.get_info()
                for backend in self.admin_site.login_backend.active_backends
            ],
            "token_backend": self.admin_site.token_backend.active_backend.get_info(),
            "formats": {
                (
                    model_class
                    if isinstance(model_class, str)
                    else model_class.__name__
                ): as_instance(frmt).serialize()
                for model_class, frmt in self.admin_site.default_format_mapping.items()
            },
            "widgets": get_widgets(),
            "settings": {
                "created_by_attr": cs_settings.CREATED_BY_ATTR,
                "created_at_attr": cs_settings.CREATED_AT_ATTR,
                "edited_by_attr": cs_settings.EDITED_BY_ATTR,
                "edited_at_attr": cs_settings.EDITED_AT_ATTR,
                # Days unsaved changes stay in the browser for recovery.
                "recovery_max_age": cs_settings.RECOVERY_MAX_AGE,
            },
        }

        return Response(data=data)

    @action(
        methods=["post"],
        detail=False,
        url_path="extensions/(?P<extension_id>[^/.]+)/run",
    )
    def run_extension(self, request, extension_id):
        """
        Run a main menu button. Signing in as staff is the gate here;
        the button decides with is_visible who may run it.
        """
        try:
            extension_uuid = uuid.UUID(extension_id)
        except ValueError:
            raise NotFound()

        button = next(
            (
                extension
                for extension in getattr(cs_settings.ADMIN_SITE, "extensions", None)
                or []
                if isinstance(extension, MainMenuButton)
                and extension.extension_id == extension_uuid
            ),
            None,
        )

        if button is None:
            raise NotFound()

        if not button.is_visible(request):
            raise PermissionDenied()

        # Changes the button records are sent as one content_changed
        # signal, like those of any request in the admin.
        with collect_changes(request):
            result = button.run(request)

        return Response(result.serialize())

    @action(
        methods=["get"],
        detail=False,
        url_path="discover",
    )
    def discover(
        self,
        request,
    ):
        """
        Returns information about the Django app (models, admin models, admin site, settings, etc.).
        """
        data = {
            "version": __version__,
            # Development tools: the UI showcase (DEBUG) and the
            # developer tools button.
            "debug": settings.DEBUG,
            "devtools": devtools.is_enabled(),
            "models": get_models(request),
            "model_groups": get_model_groups(),
            "user_model": settings.AUTH_USER_MODEL,
            "extensions": get_extensions(request),
            # The server's time zone: conditions compare dates in it, so
            # the browser decides "today" the way a save does.
            "time_zone": timezone.get_current_timezone_name(),
        }

        media_model = cs_settings.MEDIA_LIBRARY_MODEL
        folder_model = cs_settings.MEDIA_LIBRARY_FOLDER_MODEL

        data["media_library"] = {
            "enabled": media_model is not None,
            "folders": folder_model is not None,
            # Cropping is offered when the site's crop_image hook can
            # run: its own, or the built-in one (Pillow and metadata).
            "crop": get_crop_hook(self.admin_site, "crop_image") is not None,
            # Resetting a crop, through the site's reset_crop hook.
            "crop_reset": get_crop_hook(self.admin_site, "reset_crop") is not None,
            # The media item attribute holding the properties editors set,
            # such as an image's focal point; None when off.
            "properties": get_properties_attr(),
            # The media item attribute holding the metadata read from its
            # file (such as an image's width and height); None when off.
            "metadata": get_metadata_attr(),
            # The names of IMAGE_SIZES, in order: the sizes rich text
            # images can have.
            "image_sizes": list(get_size_specs()),
            "models": {
                "media_model": (media_model._meta.label_lower if media_model else None),
                "folder_model": (
                    folder_model._meta.label_lower if folder_model else None
                ),
            },
        }

        if self.admin_site.dashboard:
            data["dashboard"] = self.admin_site.dashboard.serialize()
        else:
            data["dashboard"] = {"widgets": []}

        # The notifications app: the main menu item, the settings page
        # and the retention line under the list.
        data["notifications"] = {
            "enabled": apps.is_installed("content_studio.notifications"),
            "retention": cs_settings.NOTIFICATION_RETENTION,
            "unread_retention": cs_settings.NOTIFICATION_UNREAD_RETENTION,
            "digest": bool(
                cs_settings.NOTIFICATION_EMAIL_DIGEST and cs_settings.ADMIN_URL
            ),
        }

        # The system status page: the user menu's item and its dot.
        data["status"] = {
            "enabled": apps.is_installed("content_studio.contrib.status")
            and bool(self.admin_site.has_status_permission(request)),
        }

        # The Backups page (content_studio.contrib.backups).
        data["backups"] = {
            "enabled": apps.is_installed("content_studio.contrib.backups")
            and bool(self.admin_site.has_backup_permission(request)),
        }

        # The Email activity page (content_studio.contrib.email_activity).
        data["email_activity"] = {
            "enabled": apps.is_installed("content_studio.contrib.email_activity")
            and bool(self.admin_site.has_email_activity_permission(request)),
        }

        # The Audit log page (content_studio.contrib.audit_log).
        data["audit_log"] = {
            "enabled": apps.is_installed("content_studio.contrib.audit_log")
            and bool(self.admin_site.has_audit_log_permission(request)),
        }

        # What MapWidget's map shows and searches with.
        data["map"] = {
            "tile_url": cs_settings.MAP_TILE_URL,
            "tile_attribution": cs_settings.MAP_TILE_ATTRIBUTION,
            "geocoder_url": cs_settings.MAP_GEOCODER_URL,
        }

        multitenancy = cs_settings.TENANT_MODEL is not None

        data["multitenancy"] = {
            "enabled": multitenancy,
            "tenant_model": (
                cs_settings.TENANT_MODEL._meta.label_lower if multitenancy else None
            ),
        }

        return Response(data=data)

    @action(methods=["get"], detail=False, url_path="oembed")
    def oembed(self, request):
        """
        The preview EmbedWidget shows of a URL (its title and thumbnail),
        fetched from the URL's oEmbed provider. 404 when no provider
        embeds the URL, 502 when the provider fails.
        """
        url = request.query_params.get("url", "").strip()

        if not url:
            return Response(
                {"detail": _("Pass the address to preview as url.")}, status=400
            )

        try:
            return Response(fetch_oembed(url))
        except OEmbedError as exc:
            return Response({"detail": str(exc)}, status=exc.status)

    @action(methods=["get"], detail=False, url_path="devtools")
    def get_devtools(self, request):
        """
        The developer tools: the issues to act on, the user's recent
        requests to the admin API and the environment. Only while DEBUG
        is on; a 404 otherwise.
        """
        if not devtools.is_enabled():
            raise NotFound()

        devtools.ensure_system_checks()

        return Response(
            {
                "seq": devtools.store.seq,
                "issues": devtools.store.get_issues(),
                "requests": devtools.store.get_requests(request.user.pk),
                "info": devtools.get_info(self.admin_site),
            }
        )

    @action(methods=["delete"], detail=False, url_path="devtools/issues")
    def clear_devtools_issues(self, request):
        if not devtools.is_enabled():
            raise NotFound()

        devtools.store.remove()

        return Response(status=204)

    @action(methods=["delete"], detail=False, url_path="devtools/requests")
    def clear_devtools_requests(self, request):
        if not devtools.is_enabled():
            raise NotFound()

        devtools.store.clear_requests(request.user.pk)

        return Response(status=204)

    @action(methods=["post"], detail=False, url_path="devtools/checks")
    def run_devtools_checks(self, request):
        """Runs the system checks again, as after a code change."""
        if not devtools.is_enabled():
            raise NotFound()

        devtools.run_system_checks()

        return Response(status=204)

    @action(methods=["post"], detail=False, url_path="language")
    def set_language(self, request):
        """
        Sets the editor's language: Django's language cookie, which
        content_studio.languages reads first. The page reloads after it.
        """

        language = match_language(
            str(request.data.get("language") or ""), get_enabled_languages()
        )

        if not language:
            return Response(
                {"language": [_("This language is not available.")]}, status=400
            )

        response = Response({"language": language})
        response.set_cookie(
            settings.LANGUAGE_COOKIE_NAME,
            language,
            max_age=settings.LANGUAGE_COOKIE_AGE,
            path=settings.LANGUAGE_COOKIE_PATH,
            domain=settings.LANGUAGE_COOKIE_DOMAIN,
            secure=settings.LANGUAGE_COOKIE_SECURE,
            httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
            samesite=settings.LANGUAGE_COOKIE_SAMESITE,
        )
        return response

    @action(methods=["get"], detail=False, url_path="me")
    def me(self, request):
        """
        Returns information about the current user.
        """
        return Response(get_session_user_serializer()(request.user).data)

    @action(
        methods=["get"],
        detail=False,
        url_path="tenants",
    )
    def list_tenants(self, request):
        tenant_model = cs_settings.TENANT_MODEL

        if not tenant_model:
            raise NotConfigured("The tenant model is not defined.")

        class TenantSerializer(serializers.ModelSerializer):
            class Meta:
                model = tenant_model
                fields = ["id", "__str__"]

        tenants = self.admin_site.get_tenants(
            tenant_model=tenant_model, request=request
        )

        return Response(TenantSerializer(tenants, many=True).data)


def get_models(request):
    models = []
    admin_site = cs_settings.ADMIN_SITE
    registered_models = admin_site._registry

    for model, admin_class in registered_models.items():
        models.append(
            {
                **ModelSerializer(model).serialize(),
                "admin": AdminSerializer(admin_class).serialize(request),
                "inline_only": False,
            }
        )
        for inline in admin_class.inlines:
            if inline.model not in registered_models:
                models.append(
                    {
                        **ModelSerializer(inline.model).serialize(),
                        # Only reachable through its parent: it has no
                        # list page of its own.
                        "inline_only": True,
                        # The inline model has no studio of its own; serialize a
                        # default one so the frontend's editor can render the
                        # inline's create and edit forms (they read the admin
                        # payload like any other model).
                        "admin": AdminSerializer(
                            ModelStudio(inline.model, admin_site)
                        ).serialize(request),
                    }
                )

    return models


def get_model_groups():
    admin_site = cs_settings.ADMIN_SITE

    default_group = [
        ModelGroup(
            label=_("Content"),
            name="default",
            icon=None,
            models=list(admin_site._registry.keys()),
        )
    ]
    # Get custom model groups or use the default one
    model_groups = getattr(admin_site, "model_groups", None) or default_group

    return [
        {
            "name": group.name,
            "icon": group.icon,
            "color": group.color,
            "label": group.label,
            "collapsed": group.collapsed,
            "models": [m._meta.label_lower for m in group.models],
        }
        for group in model_groups
    ]


def get_widgets():
    admin_site = cs_settings.ADMIN_SITE

    return {
        (m if isinstance(m, str) else m.__name__): as_instance(widget).serialize()
        for m, widget in admin_site.default_widget_mapping.items()
    }


def get_password_reset_info():
    """The password reset app's settings for the login pages, or None."""
    if not apps.is_installed("content_studio.contrib.password_reset"):
        return None

    return {"code_minutes": cs_settings.PASSWORD_RESET_EXPIRATION_TIME}


def get_health_check_path():
    try:
        return reverse("healthcheck")
    except NoReverseMatch:
        return None


def get_extensions(request):
    """The site's extensions, without those the request may not see."""
    admin_site = cs_settings.ADMIN_SITE

    return [
        extension.serialize()
        for extension in getattr(admin_site, "extensions", None) or []
        if extension.is_visible(request)
    ]
