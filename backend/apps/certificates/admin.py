"""Django admin for certificates.

Templates are editable; certificates are not. Issue, reissue and revoke all
carry an audit entry and a snapshot, and an admin form that wrote the row
directly would produce a certificate nobody can explain.
"""

from django.contrib import admin

from .models import Certificate, CertificateTemplate


@admin.register(CertificateTemplate)
class CertificateTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "is_default", "institution_name", "updated_at")
    list_filter = ("is_default",)
    search_fields = ("name", "institution_name")
    readonly_fields = ("id", "created_by", "created_at", "updated_at")


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ("number", "student_name", "course_title", "status", "issued_at")
    list_filter = ("status",)
    search_fields = ("number", "student_name", "student_code", "course_title")
    readonly_fields = tuple(field.name for field in Certificate._meta.fields)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False
