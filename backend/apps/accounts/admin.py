"""Admin registration for the custom user model."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Email-based admin.

    Passwords are never displayed: Django's admin form stores only the hash and
    exposes a change-password link.
    """

    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "role", "is_active", "is_staff")
    list_filter = ("role", "is_active", "is_email_verified", "is_staff", "is_superuser")
    search_fields = ("email", "first_name", "last_name")
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "last_login",
        "date_joined",
        "email_verified_at",
    )

    fieldsets = (
        (None, {"fields": ("id", "email", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "phone", "profile_image")}),
        (
            _("Email verification"),
            {"fields": ("is_email_verified", "email_verified_at")},
        ),
        (_("Role & access"), {"fields": ("role", "is_active", "is_staff", "is_superuser")}),
        (_("Permissions"), {"fields": ("groups", "user_permissions"), "classes": ("collapse",)}),
        (_("Timestamps"), {"fields": ("last_login", "date_joined", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "first_name", "last_name", "role", "password1", "password2"),
            },
        ),
    )
