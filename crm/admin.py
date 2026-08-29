from django.contrib import admin

from .models import Activity, Company, Contact, Deal, Tag, Task


class ContactInline(admin.TabularInline):
    model = Contact
    extra = 0
    fields = ("last_name", "first_name", "title", "email", "is_primary")


class DealInline(admin.TabularInline):
    model = Deal
    extra = 0
    fields = ("title", "stage", "amount", "expected_close_date", "owner")


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "industry", "rank", "employee_count", "owner", "is_active")
    list_filter = ("industry", "rank", "is_active")
    search_fields = ("name", "name_kana", "address")
    inlines = [ContactInline, DealInline]
    list_select_related = ("owner",)


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("full_name", "company", "title", "email", "is_primary")
    list_filter = ("is_primary", "tags")
    search_fields = ("last_name", "first_name", "kana", "email")
    autocomplete_fields = ("company",)
    filter_horizontal = ("tags",)


@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "stage", "amount", "probability", "expected_close_date", "owner")
    list_filter = ("stage", "owner")
    search_fields = ("title", "company__name")
    autocomplete_fields = ("company", "contact")
    date_hierarchy = "created_at"


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ("subject", "kind", "company", "occurred_at", "created_by")
    list_filter = ("kind",)
    search_fields = ("subject", "body")
    date_hierarchy = "occurred_at"


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "assignee", "due_date", "priority", "is_done")
    list_filter = ("is_done", "priority", "assignee")
    search_fields = ("title",)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "color")
