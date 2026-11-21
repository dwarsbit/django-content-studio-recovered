"""
Tests for the comments app (content_studio.comments): threads, replies,
editing, deleting, resolving, mentions, the notifications they send and
who may do what.
"""

from unittest import mock

from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory, TestCase
from rest_framework.test import APIClient

from content_studio.admin import AdminSerializer, admin_site
from content_studio.comments import add_comment, comment_added, get_comments
from content_studio.comments.models import Comment
from content_studio.notifications.models import (
    Follow,
    Notification,
    NotificationSubscription,
)
from content_studio.token_backends.jwt import create_access_token
from tests.testapp.models import Article, SiteSettings

URL = "/api/comments"


class CommentTestCase(TestCase):
    def setUp(self):
        self.anna = self.staff("anna", "view_article", "change_article")
        self.bob = self.staff("bob", "view_article")
        self.carol = self.staff("carol", "view_article")
        # Staff who may not view articles.
        self.dave = self.staff("dave", "view_page")
        self.article = Article.objects.create(title="Slow trains")

    def staff(self, username, *codenames, **fields):
        user = User.objects.create_user(
            username=username,
            password="x",
            is_staff=True,
            first_name=username.capitalize(),
            **fields,
        )
        user.user_permissions.set(Permission.objects.filter(codename__in=codenames))
        return user

    def client_for(self, user):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}")
        return client

    def target(self, obj=None):
        obj = obj or self.article
        return {"model": obj._meta.label_lower, "id": obj.pk}

    def threads(self, user, obj=None):
        response = self.client_for(user).get(URL, self.target(obj))
        assert response.status_code == 200, response.content
        return response.json()

    def comment(self, user, body="Looks good.", obj=None, **data):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client_for(user).post(
                URL, {**self.target(obj), "body": body, **data}, format="json"
            )

    def notified(self, user):
        return list(
            Notification.objects.filter(recipient=user).values_list("event", flat=True)
        )


class ThreadTests(CommentTestCase):
    def test_no_comments(self):
        assert self.threads(self.bob) == {"threads": [], "open": 0, "resolved": 0}

    def test_comment_and_reply(self):
        response = self.comment(self.bob, "The headline needs work.")

        assert response.status_code == 201, response.content
        thread = response.json()["threads"][0]
        assert thread["body"] == "The headline needs work."
        assert thread["author"]["name"] == "Bob"
        assert thread["can_edit"] is True
        assert thread["resolved_at"] is None

        response = self.comment(self.anna, "Fixed it.", parent=thread["id"])

        data = response.json()
        assert data["open"] == 1
        replies = data["threads"][0]["replies"]
        assert [reply["body"] for reply in replies] == ["Fixed it."]
        # Anna sees Bob's comment, but may not edit it.
        assert self.threads(self.anna)["threads"][0]["can_edit"] is False

    def test_a_reply_to_a_reply_joins_the_thread(self):
        thread = self.comment(self.bob).json()["threads"][0]
        reply = self.comment(self.anna, "Reply", parent=thread["id"]).json()
        reply_id = reply["threads"][0]["replies"][0]["id"]

        data = self.comment(self.carol, "Another", parent=reply_id).json()

        assert len(data["threads"]) == 1
        assert len(data["threads"][0]["replies"]) == 2

    def test_a_comment_needs_a_body(self):
        response = self.comment(self.bob, "   ")

        assert response.status_code == 400
        assert "body" in response.json()

    def test_a_reply_needs_a_comment_on_the_same_object(self):
        other = Article.objects.create(title="Other")
        thread = self.comment(self.bob, obj=other).json()["threads"][0]

        response = self.comment(self.bob, parent=thread["id"])

        assert response.status_code == 400

    def test_staff_who_may_not_view_the_object_see_nothing(self):
        self.comment(self.bob)

        client = self.client_for(self.dave)
        assert client.get(URL, self.target()).status_code == 404
        assert self.comment(self.dave).status_code == 404

    def test_studios_can_opt_out(self):
        studio = type(admin_site._registry[Article])

        with mock.patch.object(studio, "comments", False):
            assert self.client_for(self.bob).get(URL, self.target()).status_code == 404

    def test_singletons_have_no_comments(self):
        settings = SiteSettings.objects.create()
        superuser = User.objects.create_superuser("root", password="x")

        response = self.client_for(superuser).get(URL, self.target(settings))

        assert response.status_code == 404

    def test_the_admin_payload_says_which_studios_have_comments(self):
        request = RequestFactory().get("/")
        request.user = User.objects.create_superuser("root", password="x")

        def serialized(model):
            return AdminSerializer(admin_site._registry[model]).serialize(request)

        assert serialized(Article)["comments"] is True
        assert serialized(SiteSettings)["comments"] is False

    def test_deleting_the_object_deletes_its_comments(self):
        self.comment(self.bob)

        self.article.delete()

        assert not Comment.objects.exists()


class EditTests(CommentTestCase):
    def test_edit_your_own_comment(self):
        thread = self.comment(self.bob, "Typo").json()["threads"][0]

        response = self.client_for(self.bob).patch(
            f"{URL}/{thread['id']}", {"body": "No typo"}, format="json"
        )

        assert response.status_code == 200, response.content
        edited = response.json()["threads"][0]
        assert edited["body"] == "No typo"
        assert edited["edited_at"] is not None

    def test_others_may_not_edit(self):
        thread = self.comment(self.bob).json()["threads"][0]

        response = self.client_for(self.anna).patch(
            f"{URL}/{thread['id']}", {"body": "Mine now"}, format="json"
        )

        assert response.status_code == 403

    def test_delete_a_comment_without_replies(self):
        thread = self.comment(self.bob).json()["threads"][0]

        response = self.client_for(self.bob).delete(f"{URL}/{thread['id']}")

        assert response.status_code == 200
        assert response.json()["threads"] == []

    def test_a_deleted_comment_with_replies_stays_as_a_placeholder(self):
        thread = self.comment(self.bob, "Secret").json()["threads"][0]
        self.comment(self.anna, "Answer", parent=thread["id"])

        data = self.client_for(self.bob).delete(f"{URL}/{thread['id']}").json()

        deleted = data["threads"][0]
        assert deleted["deleted"] is True
        assert deleted["body"] == ""
        assert deleted["can_edit"] is False
        assert [reply["body"] for reply in deleted["replies"]] == ["Answer"]
        assert Comment.objects.get(pk=thread["id"]).body == ""

    def test_the_placeholder_goes_with_its_last_reply(self):
        thread = self.comment(self.bob).json()["threads"][0]
        reply = self.comment(self.anna, "Answer", parent=thread["id"]).json()
        reply_id = reply["threads"][0]["replies"][0]["id"]
        self.client_for(self.bob).delete(f"{URL}/{thread['id']}")

        data = self.client_for(self.anna).delete(f"{URL}/{reply_id}").json()

        assert data["threads"] == []
        assert not Comment.objects.exists()

    def test_others_may_not_delete_but_superusers_may(self):
        thread = self.comment(self.bob).json()["threads"][0]

        assert (
            self.client_for(self.anna).delete(f"{URL}/{thread['id']}").status_code
            == 403
        )

        superuser = User.objects.create_superuser("root", password="x")
        response = self.client_for(superuser).delete(f"{URL}/{thread['id']}")

        assert response.status_code == 200


class ResolveTests(CommentTestCase):
    def resolve(self, user, comment_id, resolved=True):
        return self.client_for(user).post(
            f"{URL}/{comment_id}/resolve", {"resolved": resolved}, format="json"
        )

    def test_people_who_may_change_the_object_resolve(self):
        thread = self.comment(self.bob).json()["threads"][0]

        response = self.resolve(self.anna, thread["id"])

        assert response.status_code == 200
        data = response.json()
        assert data["open"] == 0
        assert data["resolved"] == 1
        assert data["threads"][0]["resolved_by"]["name"] == "Anna"

        data = self.resolve(self.anna, thread["id"], resolved=False).json()
        assert data["open"] == 1

    def test_the_author_resolves_their_thread(self):
        thread = self.comment(self.bob).json()["threads"][0]

        assert self.resolve(self.bob, thread["id"]).status_code == 200

    def test_other_viewers_may_not_resolve(self):
        thread = self.comment(self.bob).json()["threads"][0]

        assert self.resolve(self.carol, thread["id"]).status_code == 403

    def test_resolving_a_reply_resolves_its_thread(self):
        thread = self.comment(self.bob).json()["threads"][0]
        reply = self.comment(self.anna, "Done", parent=thread["id"]).json()
        reply_id = reply["threads"][0]["replies"][0]["id"]

        data = self.resolve(self.anna, reply_id).json()

        assert data["threads"][0]["resolved_at"] is not None


class MentionTests(CommentTestCase):
    def test_people_lists_who_may_view_the_object(self):
        response = self.client_for(self.bob).get(f"{URL}/people", self.target())

        names = [person["name"] for person in response.json()["results"]]
        # Not Bob himself, not Dave (no view permission).
        assert names == ["Anna", "Carol"]

    def test_people_are_searched(self):
        response = self.client_for(self.bob).get(
            f"{URL}/people", {**self.target(), "q": "car"}
        )

        assert [p["name"] for p in response.json()["results"]] == ["Carol"]

    def test_a_mention_notifies(self):
        data = self.comment(
            self.bob, "@Carol can you check?", mentions=[self.carol.pk]
        ).json()

        assert [m["name"] for m in data["threads"][0]["mentions"]] == ["Carol"]
        notification = Notification.objects.get(recipient=self.carol)
        assert notification.event == "comments.mention"
        assert notification.get_title() == "Bob mentioned you on Slow trains"
        assert notification.get_body() == "@Carol can you check?"
        assert notification.object_id == str(self.article.pk)

    def test_mentions_of_people_who_may_not_view_are_dropped(self):
        data = self.comment(self.bob, "@Dave", mentions=[self.dave.pk]).json()

        assert data["threads"][0]["mentions"] == []
        assert not Notification.objects.filter(recipient=self.dave).exists()

    def test_a_reply_notifies_the_thread(self):
        thread = self.comment(self.bob).json()["threads"][0]
        self.comment(self.carol, "Me too", parent=thread["id"])

        self.comment(self.anna, "Thanks", parent=thread["id"])

        assert "comments.reply" in self.notified(self.bob)
        assert "comments.reply" in self.notified(self.carol)
        # Never about your own comment.
        assert self.notified(self.anna) == []

    def test_followers_hear_about_comments(self):
        Follow.objects.create(
            user=self.anna,
            content_type=ContentType.objects.get_for_model(Article),
            object_id=str(self.article.pk),
        )

        self.comment(self.bob)

        assert self.notified(self.anna) == ["comments.comment"]

    def test_one_notification_per_comment(self):
        Follow.objects.create(
            user=self.carol,
            content_type=ContentType.objects.get_for_model(Article),
            object_id=str(self.article.pk),
        )
        thread = self.comment(self.carol).json()["threads"][0]

        self.comment(self.bob, "@Carol", parent=thread["id"], mentions=[self.carol.pk])

        assert self.notified(self.carol) == ["comments.mention"]

    def test_turned_off_events_are_not_sent(self):
        NotificationSubscription.objects.create(
            user=self.carol, event="comments.mention", enabled=False
        )

        self.comment(self.bob, "@Carol", mentions=[self.carol.pk])

        assert self.notified(self.carol) == []

    def test_editing_notifies_only_new_mentions(self):
        thread = self.comment(self.bob, "@Carol", mentions=[self.carol.pk]).json()
        comment_id = thread["threads"][0]["id"]

        with self.captureOnCommitCallbacks(execute=True):
            self.client_for(self.bob).patch(
                f"{URL}/{comment_id}",
                {"body": "@Carol @Anna", "mentions": [self.carol.pk, self.anna.pk]},
                format="json",
            )

        assert self.notified(self.carol) == ["comments.mention"]
        assert self.notified(self.anna) == ["comments.mention"]


class ApiTests(CommentTestCase):
    def test_add_comment_from_code(self):
        received = []

        def receiver(sender, comment, target, author, **kwargs):
            received.append((comment.body, target, author))

        comment_added.connect(receiver)
        try:
            with self.captureOnCommitCallbacks(execute=True):
                comment = add_comment(
                    self.article,
                    None,
                    "Checked by the link checker.",
                    mentions=[self.bob],
                )
        finally:
            comment_added.disconnect(receiver)

        assert list(get_comments(self.article)) == [comment]
        assert comment.mentions == [self.bob.pk]
        assert received == [("Checked by the link checker.", self.article, None)]
        assert self.notified(self.bob) == ["comments.mention"]
        assert self.threads(self.bob)["threads"][0]["author"] is None
