"""
The studios Content Studio registers for the user model and for Django's
groups when a project does not register its own. Subclass them to start
from their layout:

    from content_studio.user_studios import UserStudio

    @register(User)
    class MyUserStudio(UserStudio):
        list_filter = ["is_staff", "groups"]
"""

__all__ = ["GroupStudio", "UserStudio"]

from django.core.exceptions import FieldDoesNotExist
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .admin import ModelStudio
from .form import ActivityLog, Callout, Field, FieldLayout, FormSet, FormSetGroup


def _editable_fields(model) -> list[str]:
    return [
        field.name
        for field in model._meta.get_fields()
        if getattr(field, "editable", False)
        and not field.auto_created
        and field.name != "password"
    ]


def _email_field(model) -> str:
    getter = getattr(model, "get_email_field_name", None)

    return getter() if getter else "email"


def _existing(model, names) -> list[str]:
    result = []

    for name in names:
        try:
            model._meta.get_field(name)
        except FieldDoesNotExist:
            continue

        result.append(name)

    return result


class InviteStatus(Callout):
    """
    Tells that a user who may log in has not done so yet, and where to
    resend their invite when the editor may send it.
    """

    def get_text(self, obj, request):
        from .password_links import can_log_in, is_invite
        from .settings import cs_settings
        from .users import can_send_password_link, sends_invites

        if not (sends_invites(type(obj)) and is_invite(obj) and can_log_in(obj)):
            return None

        text = _("This user has not logged in yet.")
        studio = cs_settings.ADMIN_SITE._registry.get(type(obj))

        if studio is not None and can_send_password_link(studio, request, obj):
            text = "%s %s" % (
                text,
                _("**Resend invite** in the more actions menu sends the invite again."),
            )

        return text


class TwoFactorStatus(Callout):
    """
    Tells that the user logs in with two-factor login, and where to reset
    it when the editor may (a lost phone).
    """

    variant = "success"
    icon = "ph-bold ph-shield-check"

    def get_text(self, obj, request):
        from .login import has_two_factor
        from .settings import cs_settings
        from .users import can_reset_two_factor

        if not has_two_factor(obj):
            return None

        text = _("Two-factor login is on.")
        studio = cs_settings.ADMIN_SITE._registry.get(type(obj))

        if studio is not None and can_reset_two_factor(studio, request, obj):
            text = "%s %s" % (
                text,
                _(
                    "Lost their phone? **Reset two-factor login** in the more "
                    "actions menu."
                ),
            )

        return text


class TwoFactorRequiredStatus(Callout):
    """Tells that the user must set up two-factor login at their next
    login (TWO_FACTOR_REQUIRED)."""

    def get_text(self, obj, request):
        from .login import has_two_factor, two_factor_required

        if has_two_factor(obj) or not two_factor_required(obj):
            return None

        return _(
            "Two-factor login is required: this user sets it up at their " "next login."
        )


class UserStudio(ModelStudio):
    """
    The user model's studio: the account and personal details on a
    Profile tab, groups and permissions on a Permissions tab, and the
    status (active, staff, superuser), the login dates and the activity
    log in the sidebar. Callouts tell what a status means for the user,
    and the permission matrix makes room for one while the user is a
    superuser. Fields a custom user model lacks are left out, and fields
    the layout does not know get a Details card on the first tab.
    """

    icon = "ph-bold ph-users"

    def __init__(self, model, admin_site):
        super().__init__(model, admin_site)
        username = getattr(model, "USERNAME_FIELD", "username")
        email = _email_field(model)

        # The defaults adapt to the user model's fields; what a subclass
        # sets itself is kept.
        if not self._overrides("edit_main") and not self._overrides("edit_sidebar"):
            self.edit_main, self.edit_sidebar = self._default_layout(username, email)

        if not self._overrides("table_display") and not self._overrides("list_display"):
            self.table_display = _existing(
                model, [username, email, "first_name", "last_name", "is_staff"]
            ) or ["__str__"]

        if not self._overrides("search_fields"):
            self.search_fields = _existing(
                model, [username, "first_name", "last_name", email]
            )

        if not self._overrides("list_filter"):
            self.list_filter = _existing(
                model, ["is_staff", "is_superuser", "is_active", "groups"]
            )

        if not self._overrides("ordering"):
            self.ordering = _existing(model, [username])

        if not self._overrides("readonly_fields"):
            self.readonly_fields = _existing(model, ["last_login", "date_joined"])

    def _overrides(self, name: str) -> bool:
        """Whether a subclass sets the attribute itself."""
        return any(
            name in vars(klass)
            for klass in type(self).__mro__
            if issubclass(klass, UserStudio) and klass is not UserStudio
        )

    def _default_layout(self, username, email):
        model = self.model
        editable = _editable_fields(model)
        dates = _existing(model, ["last_login", "date_joined"])
        names = _existing(model, ["first_name", "last_name"])
        status = [
            name
            for name in _existing(model, ["is_active", "is_staff", "is_superuser"])
            if name in editable
        ]
        groups = [name for name in _existing(model, ["groups"]) if name in editable]
        permissions = [
            name for name in _existing(model, ["user_permissions"]) if name in editable
        ]
        account = [username] if username in editable else []
        account.extend(
            name
            for name in _existing(model, [email])
            if name in editable and name != username
        )
        placed = {
            username,
            email,
            *names,
            *status,
            *groups,
            *permissions,
            *dates,
        }
        other = [name for name in editable if name not in placed]

        profile_tab = []

        if account:
            profile_tab.append(
                FormSet(
                    _("Account"),
                    fields=(
                        [FieldLayout(account, columns=2)]
                        if len(account) == 2
                        else account
                    ),
                )
            )

        if names:
            profile_tab.append(
                FormSet(
                    _("Personal info"),
                    fields=(
                        [FieldLayout(names, columns=2)] if len(names) == 2 else names
                    ),
                )
            )

        if other:
            profile_tab.append(FormSet(_("Details"), fields=other))

        superuser = "is_superuser" in status
        permissions_tab = []

        if groups or permissions:
            fields = []

            if superuser:
                fields.append(
                    Callout(
                        _(
                            "A superuser has every permission. To pick "
                            "permissions one by one, turn off superuser "
                            "status first."
                        ),
                        when=Q(is_superuser=True),
                    )
                )

            fields.extend(groups)
            # The matrix means nothing for a superuser, so it makes room.
            fields.extend(
                Field(name, when=~Q(is_superuser=True)) if superuser else name
                for name in permissions
            )
            permissions_tab.append(FormSet(fields=fields))

        main = [FormSetGroup(_("Profile"), profile_tab)]

        if permissions_tab:
            main.append(FormSetGroup(_("Permissions"), permissions_tab))

        sidebar = []

        if status:
            fields = [InviteStatus()]

            if "is_active" in status:
                fields.append(
                    Callout(
                        _("Inactive users cannot log in."),
                        variant="warning",
                        when=Q(is_active=False),
                    )
                )

            if "is_staff" in status:
                fields.append(
                    Callout(
                        _("Only staff users can log in to the admin."),
                        when=Q(is_staff=False)
                        & (Q(is_active=True) if "is_active" in status else Q()),
                    )
                )

            from .login import two_factor_installed

            if two_factor_installed():
                fields += [TwoFactorStatus(), TwoFactorRequiredStatus()]

            fields.extend(status)
            sidebar.append(FormSet(_("Status"), fields=fields))

        if dates:
            # A new user has no dates yet: the card shows once one is set.
            shown = Q()

            for name in dates:
                shown |= Q(**{f"{name}__isnull": False})

            sidebar.append(
                FormSet(
                    _("Important dates"),
                    # Each date shows once it is set: an invited user
                    # has no last login.
                    fields=[
                        Field(name, when=Q(**{f"{name}__isnull": False}))
                        for name in dates
                    ],
                    when=shown,
                )
            )

        sidebar.append(FormSet(fields=[ActivityLog()]))

        return main, sidebar


class GroupStudio(ModelStudio):
    """Django's groups: a name and the permissions of the group's users."""

    icon = "ph-bold ph-users-three"
    table_display = ["name"]
    search_fields = ["name"]
    ordering = ["name"]
    edit_main = [FormSet(fields=["name", "permissions"])]
