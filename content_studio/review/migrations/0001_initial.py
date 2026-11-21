import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ReviewRequest",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("object_id", models.CharField(max_length=255)),
                (
                    "object_repr",
                    models.CharField(blank=True, default="", max_length=200),
                ),
                ("tenant", models.CharField(blank=True, default="", max_length=255)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("open", "In review"),
                            ("approved", "Approved"),
                            ("changes_requested", "Changes requested"),
                            ("withdrawn", "Withdrawn"),
                        ],
                        default="open",
                        max_length=20,
                        verbose_name="Status",
                    ),
                ),
                ("live", models.BooleanField(default=False)),
                ("submitted_at", models.DateTimeField(auto_now_add=True)),
                ("note", models.TextField(blank=True, default="")),
                ("snapshot", models.JSONField(blank=True, default=dict)),
                ("version", models.CharField(blank=True, default="", max_length=64)),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                ("decision_note", models.TextField(blank=True, default="")),
                ("approved_snapshot", models.JSONField(blank=True, null=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "content_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="contenttypes.contenttype",
                        verbose_name="Model",
                    ),
                ),
                (
                    "decided_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "reviewer",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Reviewer",
                    ),
                ),
                (
                    "submitted_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Submitted by",
                    ),
                ),
            ],
            options={
                "verbose_name": "review request",
                "verbose_name_plural": "review requests",
                "ordering": ["-submitted_at", "-pk"],
                "indexes": [
                    models.Index(
                        fields=["content_type", "object_id"], name="cs_review_target"
                    ),
                    models.Index(fields=["status"], name="cs_review_status"),
                ],
            },
        ),
    ]
