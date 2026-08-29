from django.urls import path

from . import views

app_name = "crm"

urlpatterns = [
    # ダッシュボード -------------------------------------------------------
    path("", views.dashboard, name="dashboard"),
    path("dashboard/kpi/", views.dashboard_kpi, name="dashboard_kpi"),
    path("dashboard/pipeline/", views.dashboard_pipeline, name="dashboard_pipeline"),

    # 取引先 ---------------------------------------------------------------
    path("companies/", views.company_list, name="company_list"),
    path("companies/new/", views.company_create, name="company_create"),
    path("companies/export/", views.company_export_csv, name="company_export"),
    path("companies/bulk/", views.company_bulk_action, name="company_bulk"),
    path("companies/<int:pk>/", views.company_detail, name="company_detail"),
    path("companies/<int:pk>/edit/", views.company_update, name="company_update"),
    path("companies/<int:pk>/delete/", views.company_delete, name="company_delete"),
    path(
        "companies/<int:pk>/field/<str:field>/",
        views.company_inline_field,
        name="company_inline_field",
    ),

    # 担当者 ---------------------------------------------------------------
    path("contacts/", views.contact_list, name="contact_list"),
    path("contacts/new/", views.contact_create, name="contact_create"),
    path("contacts/check-email/", views.contact_check_email, name="contact_check_email"),
    path("contacts/options/", views.contact_options, name="contact_options"),
    path("contacts/<int:pk>/", views.contact_detail, name="contact_detail"),
    path("contacts/<int:pk>/edit/", views.contact_update, name="contact_update"),
    path("contacts/<int:pk>/delete/", views.contact_delete, name="contact_delete"),

    # 商談 -----------------------------------------------------------------
    path("deals/", views.deal_board, name="deal_board"),
    path("deals/table/", views.deal_table, name="deal_table"),
    path("deals/new/", views.deal_create, name="deal_create"),
    path("deals/<int:pk>/", views.deal_detail, name="deal_detail"),
    path("deals/<int:pk>/edit/", views.deal_update, name="deal_update"),
    path("deals/<int:pk>/delete/", views.deal_delete, name="deal_delete"),
    path("deals/<int:pk>/move/", views.deal_move, name="deal_move"),
    path("deals/<int:pk>/field/<str:field>/", views.deal_inline_field, name="deal_inline_field"),

    # 活動履歴 -------------------------------------------------------------
    path("activities/", views.activity_list, name="activity_list"),
    path("activities/new/", views.activity_create, name="activity_create"),

    # タスク ---------------------------------------------------------------
    path("tasks/", views.task_list, name="task_list"),
    path("tasks/new/", views.task_create, name="task_create"),
    path("tasks/<int:pk>/toggle/", views.task_toggle, name="task_toggle"),
    path("tasks/<int:pk>/delete/", views.task_delete, name="task_delete"),

    # 学習ガイド -----------------------------------------------------------
    path("guide/", views.guide, name="guide"),
    path("guide/slow/", views.guide_slow, name="guide_slow"),
]
