from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("content_studio_comments", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="comment",
            name="kind",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
    ]
