from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "display_name", "department", "email", "is_staff")
    list_filter = ("department", "is_staff", "is_active")
    fieldsets = UserAdmin.fieldsets + (
        ("社内情報", {"fields": ("display_name", "department", "phone", "avatar_color")}),
    )
