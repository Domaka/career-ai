from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="CvExtract",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("profile_id", models.PositiveIntegerField(db_index=True)),
                ("raw_text", models.TextField()),
                ("clean_text", models.TextField()),
                ("structured_json", models.JSONField(default=dict)),
                ("derived_metrics", models.JSONField(default=dict)),
                ("page_count", models.PositiveIntegerField(blank=True, null=True)),
                ("career_level_estimate", models.CharField(default="unknown", max_length=20)),
                ("confidence_score", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
