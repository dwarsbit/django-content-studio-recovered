"""
Temporary uploads for the FileWidget.

The content API takes JSON, so a file picked in a FileWidget is uploaded
first, on its own: it waits in UPLOAD_FOLDER (in UPLOAD_STORAGE)
and the editor gets a signed token for it. The waiting copy has no
extension, so a web server never serves it as a page. Saving the object sends the
token as the field's value, and the file is attached to the object then;
an object that is never saved is never changed. Uploads that were not
attached are removed by the content_studio_clear_uploads command.
"""

import posixpath
import uuid
from datetime import timedelta

from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files import File
from django.core.files.storage import storages
from django.template.defaultfilters import filesizeformat
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import serializers

from .file_types import extension_of, is_active_file
from .settings import cs_settings

SALT = "content_studio.uploads"

# How long an upload can be attached after it was made; older uploads
# are removed by content_studio_clear_uploads.
MAX_AGE = timedelta(days=1)


class TemporaryUpload(File):
    """A temporary upload, opened to be attached to an object."""

    def __init__(self, file, name, temporary_name):
        super().__init__(file, name)
        self.temporary_name = temporary_name


def get_upload_storage():
    """
    The storage uploads wait in until they are attached, and import files
    until they are imported: UPLOAD_STORAGE in STORAGES.
    """
    return storages[cs_settings.UPLOAD_STORAGE]


def upload_key(model, field_name) -> str:
    return f"{model._meta.label_lower}.{field_name}"


def validate_upload(model_field, file):
    """
    The upload policy: the field's own validators (an ImageField checks
    that the file is an image), UPLOAD_ALLOWED_EXTENSIONS,
    UPLOAD_MAX_SIZE, and never a type or content a browser would run when
    the file is opened from MEDIA_URL (HTML, SVG, XML, scripts).
    """
    from .media_library.serializers import looks_like_markup

    max_size = cs_settings.UPLOAD_MAX_SIZE
    allowed = cs_settings.UPLOAD_ALLOWED_EXTENSIONS
    name = getattr(file, "name", "") or ""

    if is_active_file(name) or (
        allowed is not None
        and extension_of(name) not in {extension.lower() for extension in allowed}
    ):
        raise serializers.ValidationError(_("Files of this type cannot be uploaded."))

    if max_size is not None and file.size > max_size:
        raise serializers.ValidationError(
            _("The file is larger than %(size)s.") % {"size": filesizeformat(max_size)}
        )

    if looks_like_markup(file):
        raise serializers.ValidationError(_("Files of this type cannot be uploaded."))

    try:
        model_field.formfield(required=True).clean(file)
    except DjangoValidationError as error:
        raise serializers.ValidationError(error.messages)


def save_upload(request, model, model_field, file) -> dict:
    """
    Keep an upload until the object is saved; the token the editor sends
    with the object to attach it.
    """
    validate_upload(model_field, file)

    original_name = posixpath.basename(file.name or "upload")
    # Without the original name or extension: until the object is saved,
    # the copy is never served under a type a browser renders.
    path = posixpath.join(cs_settings.UPLOAD_FOLDER, uuid.uuid4().hex, "upload")
    path = get_upload_storage().save(path, file)

    token = signing.dumps(
        {
            "path": path,
            "name": original_name,
            "field": upload_key(model, model_field.name),
            "user": str(request.user.pk),
        },
        salt=SALT,
    )

    return {"upload": token, "name": original_name, "size": file.size}


def open_upload(request, model, field_name, token) -> TemporaryUpload:
    """
    The upload a token names, opened to be attached: only by the user
    who uploaded it, to the field it was uploaded for, within MAX_AGE.
    """
    try:
        data = signing.loads(token, salt=SALT, max_age=MAX_AGE)
    except signing.BadSignature:
        raise serializers.ValidationError(
            _("The upload has expired. Choose the file again.")
        )

    if data.get("field") != upload_key(model, field_name) or data.get("user") != str(
        getattr(request.user, "pk", None)
    ):
        raise serializers.ValidationError(_("The upload is not valid."))

    path = data["path"]

    if not get_upload_storage().exists(path):
        raise serializers.ValidationError(
            _("The upload has expired. Choose the file again.")
        )

    return TemporaryUpload(get_upload_storage().open(path), data["name"], path)


def discard_upload(upload: TemporaryUpload):
    """Remove an attached upload's temporary copy."""
    try:
        upload.close()
    finally:
        get_upload_storage().delete(upload.temporary_name)


def clear_expired_uploads(max_age: timedelta = MAX_AGE) -> int:
    """
    Remove the uploads older than max_age, attached or not; the number
    of files removed.
    """
    folder = cs_settings.UPLOAD_FOLDER
    cutoff = timezone.now() - max_age
    removed = 0

    try:
        directories, _files = get_upload_storage().listdir(folder)
    except (FileNotFoundError, NotImplementedError):
        return 0

    for directory in directories:
        path = posixpath.join(folder, directory)

        for name in get_upload_storage().listdir(path)[1]:
            file_path = posixpath.join(path, name)

            try:
                modified = get_upload_storage().get_modified_time(file_path)
            except (NotImplementedError, FileNotFoundError):
                continue

            if timezone.is_naive(modified):
                modified = timezone.make_aware(modified)

            if modified < cutoff:
                get_upload_storage().delete(file_path)
                removed += 1

    return removed
