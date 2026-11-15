"""
Input forms of actions: the values a bulk action, a row action or a
Button asks for in a dialog before it runs.

An action declares its inputs with fields=[...]: names of model fields,
which take their type, label, choices and widget from the model and
validate like a save, and Field(name, form_field=...) for inputs that
are not on the model, which validate through the Django form field. The
handler receives the validated values as a dict, model instances for
related objects.
"""

import copy
from typing import Any, Optional

from django import forms
from django.core.exceptions import FieldDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.settings import api_settings

from . import conditions

# The model field type each form field renders as: the frontend picks
# the widget and the format by that name. Subclasses come first.
FORM_FIELD_TYPES: tuple[tuple[type, str], ...] = (
    (forms.ModelMultipleChoiceField, "ManyToManyField"),
    (forms.ModelChoiceField, "ForeignKey"),
    (forms.TypedMultipleChoiceField, "MultipleChoiceField"),
    (forms.MultipleChoiceField, "MultipleChoiceField"),
    (forms.TypedChoiceField, "CharField"),
    (forms.ChoiceField, "CharField"),
    (forms.NullBooleanField, "BooleanField"),
    (forms.BooleanField, "BooleanField"),
    (forms.EmailField, "EmailField"),
    (forms.URLField, "URLField"),
    (forms.SlugField, "SlugField"),
    (forms.UUIDField, "UUIDField"),
    (forms.DateTimeField, "DateTimeField"),
    (forms.DateField, "DateField"),
    (forms.TimeField, "TimeField"),
    (forms.DurationField, "DurationField"),
    (forms.DecimalField, "DecimalField"),
    (forms.FloatField, "FloatField"),
    (forms.IntegerField, "IntegerField"),
    (forms.JSONField, "JSONField"),
    (forms.CharField, "CharField"),
)


def get_form_field_type(form_field: forms.Field) -> Optional[str]:
    """The model field type a form field renders as, or None when the
    dialog cannot show it."""
    for klass, name in FORM_FIELD_TYPES:
        if isinstance(form_field, klass):
            # A text area is long text, like a TextField.
            if name == "CharField" and isinstance(form_field.widget, forms.Textarea):
                return "TextField"

            return name

    return None


def serialize_form_field(form_field: forms.Field) -> dict[str, Any]:
    """A form field described like a model field (see
    serializers.ModelSerializer.get_field), for the dialog's widgets."""
    from .utils import is_jsonable

    data: dict[str, Any] = {
        "verbose_name": None if form_field.label is None else str(form_field.label),
        "required": bool(form_field.required),
        "type": get_form_field_type(form_field),
    }

    if form_field.help_text:
        data["help_text"] = str(form_field.help_text)

    if isinstance(form_field, forms.ModelChoiceField):
        data["related_model"] = form_field.queryset.model._meta.label_lower
    elif isinstance(form_field, forms.ChoiceField):
        data["choices"] = [
            (value, str(label))
            for value, label in form_field.choices
            # The empty choice of a select stays out: the widget offers
            # clearing on its own.
            if value not in ("", None)
        ]

    initial = form_field.initial
    if callable(initial):
        initial = initial()
    if initial is not None and is_jsonable(initial):
        data["default"] = initial

    max_length = getattr(form_field, "max_length", None)
    if max_length is not None:
        data["max_length"] = max_length

    return data


class ActionForm:
    """
    The inputs of one action: its Field objects, in order, and the
    model they belong to. Serializes the dialog and validates what it
    sends.
    """

    def __init__(self, model: type[models.Model], fields):
        from .form import Field

        self.model = model
        self.fields: list[Field] = [
            field if isinstance(field, Field) else Field(field) for field in fields
        ]

    def model_field(self, field) -> Optional[models.Field]:
        """The model field an input edits, or None for a form field."""
        if field.form_field is not None:
            return None

        try:
            return self.model._meta.get_field(field.name)
        except FieldDoesNotExist:
            return None

    def serialize(self) -> list[dict[str, Any]]:
        """The dialog's fields, like the edit form's: a form field input
        carries its own description under "input"; model fields are
        described by the model."""
        return [field.serialize() for field in self.fields]

    def clean(self, request, serializer, raw) -> dict[str, Any]:
        """
        The validated values for the dialog's raw values: the shown
        fields only, model fields through the serializer's field for
        that name (as a save validates them), form fields through the
        form field. Raises a ValidationError with the errors per field.
        """
        if raw is None:
            raw = {}

        if not isinstance(raw, dict):
            raise ValidationError(
                {api_settings.NON_FIELD_ERRORS_KEY: ["The values must be an object."]}
            )

        values = {name: conditions.normalize(value) for name, value in raw.items()}
        data: dict[str, Any] = {}
        errors: dict[str, list[str]] = {}

        for field in self.fields:
            # A field the dialog hides is left out, and so not required.
            if field.when is not None and not conditions.evaluate(
                conditions.serialize(field.when), values
            ):
                continue

            try:
                if field.form_field is not None:
                    data[field.name] = self._clean_form_field(
                        request, field.form_field, raw.get(field.name)
                    )
                else:
                    data[field.name] = self._clean_model_field(
                        serializer, field.name, raw
                    )
            except serializers.ValidationError as error:
                errors[field.name] = _messages(error.detail)
            except DjangoValidationError as error:
                errors[field.name] = list(error.messages)

        if errors:
            raise ValidationError(errors)

        return data

    def _clean_model_field(self, serializer, name, raw):
        field = serializer.fields.get(name)

        # Excluded and read-only fields are reported by the system checks
        # (or read-only for this request): the dialog cannot write them.
        if field is None or field.read_only:
            raise serializers.ValidationError("This field cannot be set.")

        value = raw.get(name, serializers.empty)

        # An empty value of an optional field is no value.
        if value in ("", None) and not field.required and field.allow_null:
            return None

        return field.run_validation(value)

    def _clean_form_field(self, request, form_field, value):
        form_field = copy.deepcopy(form_field)

        if isinstance(form_field, forms.ModelChoiceField):
            from .serializers import studio_queryset
            from .utils import get_tenant_scoped_queryset

            # Related objects come from what the editor may see, as in
            # the edit form's pickers.
            queryset = form_field.queryset
            form_field.queryset = get_tenant_scoped_queryset(
                request,
                queryset.model,
                studio_queryset(request, queryset.model, queryset),
            )

            # The pickers send related objects as {"id": ...}.
            value = conditions.normalize(value)

        return form_field.clean(value)


def _messages(detail) -> list[str]:
    if isinstance(detail, dict):
        return [str(message) for messages in detail.values() for message in messages]

    if isinstance(detail, (list, tuple)):
        return [str(message) for message in detail]

    return [str(detail)]


def get_action_form(model, fields) -> Optional[ActionForm]:
    """The action form for the fields an action declares, or None."""
    return ActionForm(model, fields) if fields else None

