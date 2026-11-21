"""
Tests for review and approval (content_studio.review): editors submit
objects of a studio with review for review, and someone who may publish
approves (publishing or scheduling them) or requests changes.

FeatureAdmin gets review for these tests; it also keeps edits to live
features unpublished (pending_changes).
"""

import datetime
from unittest import mock

from django.contrib.admin.models import LogEntry
from django.contrib.auth import models as auth_models
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from content_studio.admin import admin_site
from content_studio.checks import review_errors
from content_studio.comments.models import Comment
from content_studio.notifications.models import Notification
from content_studio.publishing import Publishing
from content_studio.review import Review
from content_studio.review.models import ReviewRequest
from content_studio.token_backends.jwt import create_access_token
from tests.testapp.models import Feature

NOW = timezone.now()
HOUR = datetime.timedelta(hours=1)
URL = "/api/content/testapp.feature"
FeatureAdmin = type(admin_site._registry[Feature])


class ReviewTestCase(TestCase):
    review = True

    def setUp(self):
        patcher = mock.patch.object(FeatureAdmin, "review", self.review)
        patcher.start()
        self.addCleanup(patcher.stop)
        FeatureAdmin.saves = []
        # Sam writes; Priya and Alex may publish.
        self.sam = self.staff("sam", "view_feature", "change_feature")
        self.priya = self.staff(
            "priya", "view_feature", "change_feature", "publish_feature"
        )
        self.alex = self.staff(
            "alex", "view_feature", "change_feature", "publish_feature"
        )
        self.draft = Feature.objects.create(title="Northern lights")
        self.live = Feature.objects.create(
            title="Slow trains", summary="Fast trains.", published_at=NOW - HOUR
        )

    def staff(self, username, *codenames):
        user = auth_models.User.objects.create_user(
            username=username,
            password="x",
            is_staff=True,
            first_name=username.capitalize(),
        )
        user.user_permissions.set(
            auth_models.Permission.objects.filter(codename__in=codenames)
        )
        return user

    def client_for(self, user):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}")
        return client

    def review_post(self, user, action, feature=None, **data):
        feature = feature or self.draft

        with self.captureOnCommitCallbacks(execute=True):
            return self.client_for(user).post(
                f"{URL}/{feature.pk}/review", {"action": action, **data}, format="json"
            )

    def review_get(self, user, feature=None, **params):
        feature = feature or self.draft
        response = self.client_for(user).get(f"{URL}/{feature.pk}/review", params)
        assert response.status_code == 200, response.content
        return response.json()

    def approve(self, user, feature=None, **data):
        version = self.review_get(user, feature)["version"]
        return self.review_post(user, "approve", feature, version=version, **data)

    def detail(self, user, feature=None):
        feature = feature or self.draft
        response = self.client_for(user).get(f"{URL}/{feature.pk}")
        assert response.status_code == 200, response.content
        return response.json()

    def save(self, user, feature, **changes):
        data = {
            key: value
            for key, value in self.detail(user, feature).items()
            if not key.startswith("__")
        }
        data.update(changes)
        response = self.client_for(user).put(f"{URL}/{feature.pk}", data, format="json")
        assert response.status_code == 200, response.content
        return response.json()

    def notified(self, user):
        return list(
            Notification.objects.filter(recipient=user).values_list("event", flat=True)
        )


class SubmitTests(ReviewTestCase):
    def test_submit_puts_the_draft_in_review(self):
        response = self.review_post(self.sam, "submit", note="Ready for a look.")

        assert response.status_code == 200, response.content
        review = response.json()["review"]
        assert review["status"] == "open"
        assert review["note"] == "Ready for a look."
        assert review["submitted_by"]["name"] == "Sam"
        assert review["mine"] is True
        assert review["can_approve"] is False
        assert review["can_withdraw"] is True
        # The object stays a draft.
        self.draft.refresh_from_db()
        assert self.draft.published_at is None
        assert LogEntry.objects.filter(
            object_id=str(self.draft.pk), change_message="Submitted for review."
        ).exists()

    def test_the_edit_page_shows_the_request(self):
        self.review_post(self.sam, "submit", note="Ready.")

        publishing = self.detail(self.priya)["__publishing__"]

        assert publishing["state"] == "draft"
        assert publishing["review"]["status"] == "open"
        assert publishing["review"]["can_approve"] is True
        assert publishing["review"]["mine"] is False

    def test_everyone_who_may_publish_is_notified(self):
        self.review_post(self.sam, "submit")

        assert self.notified(self.priya) == ["review.requested"]
        assert self.notified(self.alex) == ["review.requested"]
        assert self.notified(self.sam) == []

    def test_a_picked_reviewer_is_the_only_one_notified(self):
        response = self.review_post(self.sam, "submit", reviewer=self.priya.pk)

        assert response.json()["review"]["reviewer"]["name"] == "Priya"
        assert self.notified(self.priya) == ["review.requested"]
        assert self.notified(self.alex) == []

    def test_the_reviewer_must_be_able_to_publish(self):
        other = self.staff("other", "view_feature", "change_feature")

        response = self.review_post(self.sam, "submit", reviewer=other.pk)

        assert response.status_code == 400
        assert "reviewer" in response.json()

    def test_reviewers_to_pick(self):
        data = self.review_get(self.sam, include="reviewers")

        names = [person["name"] for person in data["reviewers"]]
        assert names == ["Alex", "Priya"]

    def test_submitting_twice_is_refused(self):
        self.review_post(self.sam, "submit")

        response = self.review_post(self.sam, "submit")

        assert response.status_code == 400

    def test_a_viewer_cannot_submit(self):
        viewer = self.staff("viewer", "view_feature")

        response = self.review_post(viewer, "submit")

        assert response.status_code == 403

    def test_live_content_needs_unpublished_changes(self):
        response = self.review_post(self.sam, "submit", feature=self.live)

        assert response.status_code == 400

    def test_without_review_the_endpoint_is_missing(self):
        with mock.patch.object(FeatureAdmin, "review", None):
            response = self.client_for(self.sam).get(f"{URL}/{self.draft.pk}/review")

        assert response.status_code == 404


class DecisionTests(ReviewTestCase):
    def setUp(self):
        super().setUp()
        self.review_post(self.sam, "submit", note="Ready for a look.")

    def test_approve_publishes_now(self):
        response = self.approve(self.priya, note="Lovely.")

        assert response.status_code == 200, response.content
        assert response.json()["publishing"]["state"] == "published"
        assert response.json()["review"] is None
        self.draft.refresh_from_db()
        assert self.draft.published_at is not None
        request = ReviewRequest.objects.get()
        assert request.status == "approved"
        assert request.decided_by == self.priya
        assert request.decision_note == "Lovely."
        assert request.approved_snapshot["title"] == "Northern lights"
        assert request.closed_at is not None
        assert self.notified(self.sam) == ["review.approved"]

    def test_approve_and_schedule(self):
        at = (NOW + 24 * HOUR).isoformat()

        response = self.approve(self.priya, at=at)

        assert response.status_code == 200, response.content
        assert response.json()["publishing"]["state"] == "scheduled"

    def test_approval_is_pinned_to_the_version_seen(self):
        version = self.review_get(self.priya)["version"]
        self.save(self.sam, self.draft, title="Northern lights, tonight")

        response = self.review_post(self.priya, "approve", version=version)

        assert response.status_code == 400
        assert "version" in response.json()
        self.draft.refresh_from_db()
        assert self.draft.published_at is None
        data = self.review_get(self.priya)
        assert data["changed_since_submitted"] == ["title"]

    def test_the_submitter_cannot_approve_their_own(self):
        submitter = self.staff(
            "lead", "view_feature", "change_feature", "publish_feature"
        )
        draft = Feature.objects.create(title="Own work")
        self.review_post(submitter, "submit", feature=draft)

        response = self.approve(submitter, feature=draft)

        assert response.status_code == 403

    def test_an_editor_cannot_approve(self):
        response = self.approve(self.sam)

        assert response.status_code == 403

    def test_request_changes_needs_a_note(self):
        response = self.review_post(self.priya, "request_changes")

        assert response.status_code == 400
        assert "note" in response.json()

    def test_request_changes(self):
        response = self.review_post(
            self.priya, "request_changes", note="Add the forecast link."
        )

        assert response.status_code == 200, response.content
        review = response.json()["review"]
        assert review["status"] == "changes_requested"
        assert review["decision_note"] == "Add the forecast link."
        assert review["decided_by"]["name"] == "Priya"
        assert self.notified(self.sam) == ["review.changes_requested"]
        # Submitting again starts a new request.
        again = self.review_post(self.sam, "submit", note="Added it.")
        assert again.json()["review"]["status"] == "open"
        assert ReviewRequest.objects.filter(closed_at__isnull=True).count() == 1
        assert ReviewRequest.objects.count() == 2

    def test_withdraw(self):
        response = self.review_post(self.sam, "withdraw")

        assert response.status_code == 200, response.content
        assert response.json()["review"] is None
        assert ReviewRequest.objects.get().status == "withdrawn"

    def test_someone_else_cannot_withdraw(self):
        other = self.staff("other", "view_feature", "change_feature")

        response = self.review_post(other, "withdraw")

        assert response.status_code == 403

    def test_publishing_directly_counts_as_approval(self):
        response = self.client_for(self.alex).post(
            f"{URL}/{self.draft.pk}/publishing", {"action": "publish"}, format="json"
        )

        assert response.status_code == 200, response.content
        request = ReviewRequest.objects.get()
        assert request.status == "approved"
        assert request.decided_by == self.alex

    def test_bulk_publish_counts_as_approval(self):
        response = self.client_for(self.alex).post(
            f"{URL}/bulk",
            {"action": "publishing:publish", "ids": [self.draft.pk]},
            format="json",
        )

        assert response.status_code == 200, response.content
        assert ReviewRequest.objects.get().status == "approved"

    def test_deleting_the_object_removes_its_requests(self):
        self.draft.delete()

        assert not ReviewRequest.objects.exists()


class LiveContentTests(ReviewTestCase):
    def test_review_of_unpublished_changes(self):
        self.save(self.sam, self.live, title="Slow journeys")
        submitted = self.review_post(self.sam, "submit", feature=self.live)
        assert submitted.status_code == 200, submitted.content
        assert submitted.json()["review"]["live"] is True

        data = self.review_get(self.priya, self.live)

        assert data["changes"]["base"] == "live"
        assert data["changes"]["fields"] == ["title"]
        assert data["changes"]["before"] == {"title": "Slow trains"}
        assert data["changes"]["after"] == {"title": "Slow journeys"}

        response = self.approve(self.priya, self.live)

        assert response.status_code == 200, response.content
        self.live.refresh_from_db()
        assert self.live.title == "Slow journeys"
        assert ReviewRequest.objects.get().status == "approved"

    def test_live_content_is_not_scheduled(self):
        self.save(self.sam, self.live, title="Slow journeys")
        self.review_post(self.sam, "submit", feature=self.live)

        response = self.approve(self.priya, self.live, at=(NOW + HOUR).isoformat())

        assert response.status_code == 400
        assert "at" in response.json()

    def test_discarding_the_changes_withdraws_their_review(self):
        self.save(self.sam, self.live, title="Slow journeys")
        self.review_post(self.sam, "submit", feature=self.live)

        response = self.client_for(self.priya).post(
            f"{URL}/{self.live.pk}/publishing",
            {"action": "discard_changes"},
            format="json",
        )

        assert response.status_code == 200, response.content
        assert ReviewRequest.objects.get().status == "withdrawn"

    def test_a_draft_is_compared_with_its_last_approved_values(self):
        self.review_post(self.sam, "submit")
        self.approve(self.priya)
        self.client_for(self.priya).post(
            f"{URL}/{self.draft.pk}/publishing",
            {"action": "unpublish"},
            format="json",
        )
        self.save(self.sam, self.draft, title="Northern lights in March")

        data = self.review_get(self.priya)

        assert data["changes"]["base"] == "approved"
        assert data["changes"]["fields"] == ["title"]


class RequiredReviewTests(ReviewTestCase):
    review = Review(required=True)

    def test_publishers_cannot_skip_review(self):
        response = self.client_for(self.priya).post(
            f"{URL}/{self.draft.pk}/publishing", {"action": "publish"}, format="json"
        )

        assert response.status_code == 400

    def test_the_list_has_no_bulk_publish(self):
        from content_studio.actions import get_bulk_actions

        ids = [action.id for action in get_bulk_actions(admin_site._registry[Feature])]
        assert "publishing:publish" not in ids
        assert "publishing:schedule" not in ids
        assert "publishing:unpublish" in ids

    def test_approval_still_publishes(self):
        self.review_post(self.sam, "submit")

        response = self.approve(self.priya)

        assert response.status_code == 200, response.content
        assert response.json()["publishing"]["state"] == "published"


class SelfApprovalTests(ReviewTestCase):
    review = Review(self_approval=True)

    def test_a_publisher_may_approve_their_own(self):
        self.review_post(self.priya, "submit")

        response = self.approve(self.priya)

        assert response.status_code == 200, response.content


class ListTests(ReviewTestCase):
    def setUp(self):
        super().setUp()
        self.review_post(self.sam, "submit")
        self.other = Feature.objects.create(title="Fog")
        self.review_post(self.sam, "submit", feature=self.other, reviewer=self.alex.pk)

    def ids(self, user, status):
        response = self.client_for(user).get(f"{URL}?publishing_status={status}")
        assert response.status_code == 200, response.content
        return sorted(row["id"] for row in response.json()["results"])

    def test_rows_carry_the_review_status(self):
        response = self.client_for(self.priya).get(URL)

        rows = {row["id"]: row for row in response.json()["results"]}
        assert rows[self.draft.pk]["__publishing__"]["review"] == {"status": "open"}
        assert rows[self.live.pk]["__publishing__"]["review"] is None

    def test_status_filter(self):
        assert self.ids(self.priya, "in_review") == sorted(
            [self.draft.pk, self.other.pk]
        )
        # Alex was picked for the other; anyone may take the first.
        assert self.ids(self.priya, "my_review") == [self.draft.pk]
        assert self.ids(self.alex, "my_review") == sorted(
            [self.draft.pk, self.other.pk]
        )
        assert self.ids(self.sam, "my_review") == []

        self.review_post(self.priya, "request_changes", note="Shorter.")

        assert self.ids(self.priya, "changes_requested") == [self.draft.pk]


class CommentTests(ReviewTestCase):
    def test_notes_are_posted_as_comments(self):
        self.review_post(self.sam, "submit", note="Ready for a look.")
        self.review_post(self.priya, "request_changes", note="Add the link.")

        comments = list(Comment.objects.values_list("kind", "body", "author"))

        assert comments == [
            ("review.submitted", "Ready for a look.", self.sam.pk),
            ("review.changes_requested", "Add the link.", self.priya.pk),
        ]
        # Review notified on its own events, not as comments.
        assert "comments.comment" not in self.notified(self.priya)

    def test_studios_without_comments_keep_notes_on_the_request(self):
        with mock.patch.object(FeatureAdmin, "comments", False):
            self.review_post(self.sam, "submit", note="Ready.")

        assert not Comment.objects.exists()
        assert ReviewRequest.objects.get().note == "Ready."


class CheckTests(TestCase):
    def test_review_needs_publishing(self):
        class Studio:
            model = Feature
            publishing = None
            review = True

        errors = review_errors(Studio())

        assert [check_id for check_id, _ in errors] == ["content_studio.E058"]

    def test_review_must_be_true_or_a_review(self):
        class Studio:
            model = Feature
            publishing = Publishing("published_at")
            review = "yes"

        assert review_errors(Studio())[0][0] == "content_studio.E058"

    def test_a_valid_review(self):
        class Studio:
            model = Feature
            publishing = Publishing("published_at")
            review = Review(required=True)

        assert review_errors(Studio()) == []


class ComparableTests(TestCase):
    def test_related_objects_compare_by_id(self):
        from content_studio.review.core import changed_fields, fingerprint

        before = {"tags": [{"id": 1, "__str__": "News", "description": "3 items"}]}
        after = {"tags": [{"id": 1, "__str__": "News", "description": "4 items"}]}

        self.assertEqual(changed_fields(before, after), [])
        self.assertEqual(fingerprint(before), fingerprint(after))
        self.assertEqual(
            changed_fields(before, {"tags": [{"id": 2, "__str__": "Other"}]}),
            ["tags"],
        )
