"""
Tests for actions with an input form (fields= on @bulk_action and
Button), row actions (row_actions) and edit page actions (edit_actions):
serialization, validation of the dialog's values, the endpoints and the
system checks.
"""

from unittest import mock

from django import forms
from django.contrib.auth.models import User
from django.db.models import Q
from django.test import TestCase

from content_studio.action_forms import ActionForm, serialize_form_field
from content_studio.actions import (
    bulk_action,
    get_bulk_actions,
    get_edit_actions,
    get_row_actions,
)
from content_studio.checks import action_form_errors, bulk_action_errors
from content_studio.form import Button, ButtonResult, Field
from tests.test_e2e_crud import AuthenticatedTestCase
from tests.testapp.admin import ArticleAdmin
from tests.testapp.models import Article, Category

BULK = "/api/content/testapp.article/bulk"

# The handlers are module-level functions, patched onto the studio:
# class bodies resolve names through the module.
received = {}


@bulk_action(
    label="Assign",
    fields=[
        "author",
        Field("note", form_field=forms.CharField(required=False)),
        Field(
            "notify",
            form_field=forms.BooleanField(required=False),
            when=~Q(note=""),
        ),
    ],
)
def assign(self, request, queryset, data):
    received.clear()
    received.update(data)
    count = queryset.update(author=data["author"])
    return f"Assigned {count}."


@bulk_action(fields=["status", Field("published_at", when=Q(status="published"))])
def set_status(self, request, queryset, data):
    received.clear()
    received.update(data)
    queryset.update(status=data["status"])


@bulk_action(
    fields=[
        Field(
            "category",
            form_field=forms.ModelChoiceField(queryset=Category.objects.all()),
        )
    ]
)
def categorize(self, request, queryset, data):
    received.clear()
    received.update(data)
    for article in queryset:
        article.categories.add(data["category"])


def with_actions(**attributes):
    """Patch the test studio with the module's actions and attributes."""
    patches = [
        mock.patch.object(ArticleAdmin, name, handler, create=True)
        for name, handler in (
            ("assign", assign),
            ("set_status", set_status),
            ("categorize", categorize),
        )
    ] + [
        mock.patch.object(ArticleAdmin, name, value, create=True)
        for name, value in attributes.items()
    ]

    class Patches:
        def __enter__(self):
            for patch in patches:
                patch.start()

        def __exit__(self, *exc):
            for patch in reversed(patches):
                patch.stop()

    return Patches()


class SerializationTests(TestCase):
    def test_an_action_with_fields_serializes_them(self):
        with with_actions():
            action = next(
                action
                for action in get_bulk_actions(ArticleAdmin(Article, None))
                if action.id == "assign"
            )

        fields = action.serialize()["fields"]

        self.assertEqual([field["name"] for field in fields], ["author", "note", "notify"])
        # A model field is described by the model.
        self.assertNotIn("input", fields[0])
        # A form field describes itself like a model field.
        self.assertEqual(fields[1]["input"]["type"], "CharField")
        self.assertFalse(fields[1]["input"]["required"])
        self.assertEqual(fields[2]["input"]["type"], "BooleanField")
        self.assertIsNotNone(fields[2]["when"])

    def test_an_action_without_fields_serializes_none(self):
        action = next(
            action
            for action in get_bulk_actions(ArticleAdmin(Article, None))
            if action.id == "publish"
        )

        self.assertNotIn("fields", action.serialize())

    def test_form_fields_map_to_model_field_types(self):
        cases = [
            (forms.CharField(widget=forms.Textarea), "TextField"),
            (forms.EmailField(), "EmailField"),
            (forms.IntegerField(), "IntegerField"),
            (forms.DateTimeField(), "DateTimeField"),
            (forms.ChoiceField(choices=[("a", "A")]), "CharField"),
            (forms.MultipleChoiceField(choices=[("a", "A")]), "MultipleChoiceField"),
            (forms.ModelChoiceField(queryset=Category.objects.all()), "ForeignKey"),
            (
                forms.ModelMultipleChoiceField(queryset=Category.objects.all()),
                "ManyToManyField",
            ),
        ]

        for form_field, expected in cases:
            with self.subTest(form_field=form_field.__class__.__name__):
                self.assertEqual(serialize_form_field(form_field)["type"], expected)

    def test_choices_and_related_models_are_described(self):
        choice = serialize_form_field(
            forms.ChoiceField(choices=[("", "---"), ("a", "Apple")], initial="a")
        )
        related = serialize_form_field(
            forms.ModelChoiceField(queryset=Category.objects.all())
        )

        self.assertEqual(choice["choices"], [("a", "Apple")])
        self.assertEqual(choice["default"], "a")
        self.assertEqual(related["related_model"], "testapp.category")

    def test_a_button_serializes_its_fields(self):
        class Schedule(Button):
            label = "Schedule"
            fields = ["published_at"]

        self.assertEqual(
            [field["name"] for field in Schedule().serialize()["fields"]],
            ["published_at"],
        )


class EndpointTests(AuthenticatedTestCase):
    def setUp(self):
        self.superuser = self.create_user(superuser=True)
        self.author = User.objects.create(username="priya")
        self.articles = [
            Article.objects.create(title="one"),
            Article.objects.create(title="two"),
        ]
        self.ids = [str(article.pk) for article in self.articles]

    def post(self, action, data=None, ids=None, user=None):
        client = self.client_for(user or self.superuser)
        payload = {"action": action, "ids": ids or self.ids}

        if data is not None:
            payload["data"] = data

        return client.post(BULK, payload, format="json")

    def test_the_handler_gets_the_validated_values(self):
        with with_actions():
            response = self.post(
                "assign",
                {"author": {"id": self.author.pk}, "note": "Hi", "notify": True},
            )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {"message": "Assigned 2."})
        self.assertEqual(received, {"author": self.author, "note": "Hi", "notify": True})
        self.assertEqual(
            set(Article.objects.values_list("author", flat=True)), {self.author.pk}
        )

    def test_a_hidden_field_is_left_out(self):
        with with_actions():
            response = self.post(
                "assign", {"author": None, "note": "", "notify": True}
            )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(received, {"author": None, "note": ""})

    def test_invalid_values_return_errors_per_field_and_run_nothing(self):
        with with_actions():
            response = self.post(
                "set_status", {"status": "archived", "published_at": "soon"}
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()), {"status"})
        self.assertEqual(
            set(Article.objects.values_list("status", flat=True)), {"draft"}
        )

    def test_a_required_model_field_is_required(self):
        with with_actions():
            response = self.post("set_status", {})

        self.assertEqual(response.status_code, 400)
        self.assertIn("status", response.json())

    def test_a_condition_shows_a_field(self):
        with with_actions():
            response = self.post(
                "set_status",
                {"status": "published", "published_at": "2026-11-15T10:00:00Z"},
            )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(received["status"], "published")
        self.assertEqual(received["published_at"].year, 2026)

    def test_an_unknown_related_object_is_refused(self):
        with with_actions():
            response = self.post("assign", {"author": {"id": 9999}})

        self.assertEqual(response.status_code, 400)
        self.assertIn("author", response.json())

    def test_model_choice_form_fields_take_related_objects_by_id(self):
        category = Category.objects.create(name="News")

        with with_actions():
            response = self.post("categorize", {"category": {"id": category.pk}})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(received, {"category": category})

    def test_model_choice_form_fields_are_scoped_to_the_studio(self):
        category = Category.objects.create(name="Hidden")

        with with_actions(), mock.patch(
            "content_studio.serializers.studio_queryset",
            lambda request, model, queryset: queryset.none(),
        ):
            response = self.post("categorize", {"category": {"id": category.pk}})

        self.assertEqual(response.status_code, 400)
        self.assertIn("category", response.json())

    def test_values_must_be_an_object(self):
        with with_actions():
            response = self.post("assign", ["nope"])

        self.assertEqual(response.status_code, 400)


class RowAndEditActionTests(AuthenticatedTestCase):
    def setUp(self):
        self.superuser = self.create_user(superuser=True)
        self.articles = [
            Article.objects.create(title="one"),
            Article.objects.create(title="two"),
        ]

    def test_default_row_actions_are_delete_and_duplicate_when_allowed(self):
        studio = ArticleAdmin(Article, None)

        self.assertEqual([a.id for a in get_row_actions(studio)], ["delete"])

        with mock.patch.object(ArticleAdmin, "allow_duplication", True):
            self.assertEqual(
                [a.id for a in get_row_actions(studio)], ["duplicate", "delete"]
            )

    def test_row_actions_select_and_order(self):
        with with_actions(row_actions=["assign", "delete"], allow_duplication=True):
            actions = get_row_actions(ArticleAdmin(Article, None))

        self.assertEqual([action.id for action in actions], ["assign", "delete"])
        # A row's delete asks about the one item.
        self.assertIn("this item", actions[1].serialize()["confirm"])

    def test_an_empty_list_removes_the_menu(self):
        with mock.patch.object(ArticleAdmin, "row_actions", [], create=True):
            self.assertEqual(get_row_actions(ArticleAdmin(Article, None)), [])

    def test_a_row_action_outside_the_bulk_bar_runs_on_one_object(self):
        client = self.client_for(self.superuser)

        with with_actions(actions=["delete"], row_actions=["publish"]):
            one = client.post(
                BULK,
                {"action": "publish", "ids": [str(self.articles[0].pk)]},
                format="json",
            )
            two = client.post(
                BULK,
                {"action": "publish", "ids": [str(a.pk) for a in self.articles]},
                format="json",
            )

        self.assertEqual(one.status_code, 200)
        self.assertEqual(two.status_code, 404)

    def test_edit_actions_default_to_none(self):
        self.assertEqual(get_edit_actions(ArticleAdmin(Article, None)), [])

    def test_an_edit_action_runs_on_one_object(self):
        client = self.client_for(self.superuser)

        with with_actions(actions=[], edit_actions=["set_status"]):
            response = client.post(
                BULK,
                {
                    "action": "set_status",
                    "ids": [str(self.articles[0].pk)],
                    "data": {"status": "published"},
                },
                format="json",
            )

        self.assertEqual(response.status_code, 200, response.content)
        self.articles[0].refresh_from_db()
        self.assertEqual(self.articles[0].status, "published")

    def test_the_payload_lists_row_and_edit_actions(self):
        client = self.client_for(self.superuser)

        with with_actions(row_actions=["assign", "delete"], edit_actions=["assign"]):
            response = client.get("/api/discover")

        article = next(
            model
            for model in response.json()["models"]
            if model["label"] == "testapp.article"
        )
        self.assertEqual(
            [a["id"] for a in article["admin"]["list"]["row_actions"]],
            ["assign", "delete"],
        )
        self.assertEqual(
            [a["id"] for a in article["admin"]["edit"]["actions"]], ["assign"]
        )


class ScheduleButton(Button):
    label = "Schedule"
    fields = ["status", Field("note", form_field=forms.CharField(required=False))]

    def handle(self, obj, request, data):
        if data["note"] == "refuse":
            from django.core.exceptions import ValidationError

            raise ValidationError("Refused.")

        obj.status = data["status"]
        obj.save(update_fields=["status"])
        return ButtonResult(message=f"Set to {data['status']}.")


class ButtonTests(AuthenticatedTestCase):
    def setUp(self):
        self.superuser = self.create_user(superuser=True)
        self.article = Article.objects.create(title="one")
        self.button = ScheduleButton()

    def run_button(self, data):
        client = self.client_for(self.superuser)

        with mock.patch.object(
            ArticleAdmin, "edit_sidebar", ArticleAdmin.edit_sidebar + [self.button]
        ):
            return client.post(
                f"/api/content/testapp.article/{self.article.pk}/components/"
                f"{self.button.component_id}/run",
                {"data": data},
                format="json",
            )

    def test_handle_gets_the_values(self):
        response = self.run_button({"status": "published", "note": ""})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["message"], "Set to published.")
        self.article.refresh_from_db()
        self.assertEqual(self.article.status, "published")

    def test_invalid_values_are_refused(self):
        response = self.run_button({"status": "nope"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("status", response.json())

    def test_a_validation_error_from_handle_is_a_400(self):
        response = self.run_button({"status": "published", "note": "refuse"})

        self.assertEqual(response.status_code, 400)
        self.article.refresh_from_db()
        self.assertEqual(self.article.status, "draft")


class CheckTests(TestCase):
    def errors_for(self, **attributes):
        studio_class = type("Checked", (ArticleAdmin,), attributes)

        return [
            message
            for check_id, message in action_form_errors(studio_class(Article, None))
            + bulk_action_errors(studio_class(Article, None))
        ]

    def test_a_valid_configuration_has_no_errors(self):
        self.assertEqual(
            self.errors_for(
                assign=assign,
                set_status=set_status,
                row_actions=["assign", "duplicate", "delete"],
                edit_actions=["set_status"],
            ),
            [],
        )

    def test_unknown_fields_need_a_form_field(self):
        @bulk_action(fields=["nope"])
        def broken(self, request, queryset, data):
            pass

        [error] = self.errors_for(broken=broken)
        self.assertIn("'nope'", error)
        self.assertIn("form_field", error)

    def test_non_editable_fields_cannot_be_set(self):
        @bulk_action(fields=["id"])
        def broken(self, request, queryset, data):
            pass

        [error] = self.errors_for(broken=broken)
        self.assertIn("not editable", error)

    def test_handlers_need_a_data_argument(self):
        @bulk_action(fields=["status"])
        def broken(self, request, queryset):
            pass

        [error] = self.errors_for(broken=broken)
        self.assertIn("data", error)

    def test_conditions_read_the_action_fields(self):
        @bulk_action(fields=[Field("status", when=Q(title="x"))])
        def broken(self, request, queryset, data):
            pass

        [error] = self.errors_for(broken=broken)
        self.assertIn("'title'", error)

    def test_unknown_row_and_edit_action_names(self):
        errors = self.errors_for(
            row_actions=["nope", "delete", "delete"], edit_actions=["delete"]
        )

        self.assertEqual(len(errors), 3)
        self.assertTrue(any("row_actions contains 'nope'" in e for e in errors))
        self.assertTrue(any("more than once" in e for e in errors))
        self.assertTrue(any("edit_actions contains 'delete'" in e for e in errors))

    def test_buttons_are_checked_too(self):
        class Broken(Button):
            label = "Broken"
            fields = ["status"]

            def handle(self, obj, request):
                pass

        errors = self.errors_for(edit_sidebar=[Broken()])
        self.assertEqual(len(errors), 1)
        self.assertIn("Button 'Broken'", errors[0])


class ActionFormTests(TestCase):
    def test_strings_become_fields(self):
        form = ActionForm(Article, ["status", Field("note", form_field=forms.CharField())])

        self.assertEqual([field.name for field in form.fields], ["status", "note"])
