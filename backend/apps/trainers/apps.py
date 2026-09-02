from django.apps import AppConfig


class TrainersConfig(AppConfig):
    """Trainer domain: the profile attached to a user with the trainer role."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.trainers"
    verbose_name = "Trainers"
