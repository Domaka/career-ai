from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CvAnalysis",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("profile_id", models.PositiveIntegerField(db_index=True)),
                ("summary", models.TextField(blank=True, default="")),
                ("strengths", models.JSONField(default=list)),
                ("weaknesses", models.JSONField(default=list)),
                ("talent_gaps", models.JSONField(default=list)),
                ("analysis_json", models.JSONField(default=dict)),
                ("source", models.CharField(choices=[("rules", "Rules"), ("gemini", "Gemini")], default="rules", max_length=20)),
                ("fallback_reason", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("cv_extract", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="analysis", to="api.cvextract")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
