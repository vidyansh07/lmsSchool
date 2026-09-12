from django.contrib import admin

from .models import FeePayment, FeePlan


class FeePaymentInline(admin.TabularInline):
    model = FeePayment
    extra = 0
    can_delete = False
    readonly_fields = (
        "receipt_number",
        "amount",
        "paid_on",
        "method",
        "reference",
        "recorded_by",
        "voided_at",
        "voided_by",
        "void_reason",
    )


@admin.register(FeePlan)
class FeePlanAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "agreed_amount", "discount_amount", "next_due_on", "updated_at")
    search_fields = (
        "enrollment__code",
        "enrollment__student__student_id",
        "enrollment__student__user__email",
    )
    readonly_fields = ("created_by", "updated_by", "created_at", "updated_at")
    inlines = (FeePaymentInline,)


@admin.register(FeePayment)
class FeePaymentAdmin(admin.ModelAdmin):
    list_display = ("receipt_number", "plan", "amount", "paid_on", "method", "voided_at")
    search_fields = ("receipt_number", "reference", "plan__enrollment__code")
    readonly_fields = tuple(field.name for field in FeePayment._meta.fields)
