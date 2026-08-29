"""CRM のビュー群。

htmx との組み合わせ方の「型」を一通り詰め込んである。ポイントは3つ:

1. ``request.htmx`` (django-htmx) で「部分リクエストかどうか」を判定する
2. 返すのは HTML の断片。Django 6.0 で入った **テンプレートパーシャル** を使い、
   ``"crm/foo.html#rows"`` のように 1 ファイルの中の一部だけをレンダリングする
3. 画面更新の指示はレスポンスヘッダ (``HX-Trigger`` / ``HX-Redirect`` など) で送る
"""

import csv
import time
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST
from django_htmx.http import HttpResponseClientRedirect, trigger_client_event

from .forms import (
    INLINE_EDITABLE_FIELDS,
    ActivityForm,
    CompanyForm,
    ContactForm,
    DealForm,
    TaskForm,
    build_inline_form,
)
from .models import Activity, Company, Contact, Deal, Task

# ---------------------------------------------------------------------------
# 共通ヘルパー
# ---------------------------------------------------------------------------

PAGE_SIZE = 15


def toast(response, message: str, level: str = "success"):
    """レスポンスに `HX-Trigger` を積んで、クライアント側でトーストを出させる。

    base.html の JS が `toast` イベントを拾って画面右下に表示する。
    """
    return trigger_client_event(response, "toast", {"message": message, "level": level})


def paginate(request, queryset, per_page: int = PAGE_SIZE):
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(request.GET.get("page"))


def sorted_queryset(request, queryset, allowed: dict[str, str], default: str):
    """`?sort=name&dir=desc` を安全に order_by に変換する。

    ユーザー入力をそのまま order_by に渡すと任意のカラムを覗けてしまうため、
    ホワイトリスト方式にするのが定石。
    """
    key = request.GET.get("sort", default)
    if key not in allowed:
        key = default
    field = allowed[key]
    descending = request.GET.get("dir") == "desc"
    return queryset.order_by(f"-{field}" if descending else field), key, descending


def partial(request, template: str, name: str) -> str:
    """htmx リクエストならパーシャル名付きのテンプレート名を返す。

    ⚠️ `request.htmx` だけで判定してはいけない。
    hx-boost によるページ遷移も HX-Request: true を送ってくるが、
    あれは「ページ遷移」であって部分更新ではない。
    htmx は返ってきた HTML で <body> の中身を丸ごと置き換えるため、
    断片を返すとレイアウトごと消えてしまう。

    HX-Boosted ヘッダ（django-htmx では request.htmx.boosted）で見分ける。
    """
    if request.htmx and not request.htmx.boosted:
        return f"{template}#{name}"
    return template


# ---------------------------------------------------------------------------
# ダッシュボード
# ---------------------------------------------------------------------------


def kpi_context():
    today = timezone.localdate()
    month_start = today.replace(day=1)
    open_deals = Deal.objects.open()
    won_this_month = Deal.objects.filter(stage=Deal.Stage.WON, updated_at__date__gte=month_start)
    return {
        "kpi_open_count": open_deals.count(),
        "kpi_open_amount": open_deals.total_amount(),
        "kpi_weighted": sum((d.weighted_amount for d in open_deals), Decimal("0")),
        "kpi_won_amount": won_this_month.total_amount(),
        "kpi_company_count": Company.objects.filter(is_active=True).count(),
        "kpi_overdue": sum(1 for d in open_deals if d.is_overdue),
        "kpi_updated_at": timezone.localtime(),
    }


@login_required
def dashboard(request):
    context = kpi_context()
    context |= {
        "my_tasks": Task.objects.filter(assignee=request.user, is_done=False).select_related("deal")[:8],
        "recent_activities": Activity.objects.select_related("company", "created_by")[:6],
    }
    return render(request, "crm/dashboard.html", context)


@login_required
def dashboard_kpi(request):
    """`hx-trigger="every 30s"` でポーリングされる KPI カード群。"""
    return render(request, "crm/dashboard.html#kpi", kpi_context())


@login_required
def dashboard_pipeline(request):
    """`hx-trigger="load"` の遅延ロード（lazy loading）デモ。

    重い集計を初期表示のブロッキング要因にしない、というパターン。
    """
    rows = (
        Deal.objects.filter(stage__in=Deal.OPEN_STAGES)
        .values("stage")
        .annotate(count=Count("id"), amount=Sum("amount"))
    )
    by_stage = {row["stage"]: row for row in rows}
    max_amount = max((r["amount"] or 0 for r in rows), default=0) or 1
    pipeline = []
    for value, label in Deal.Stage.choices:
        if value not in Deal.OPEN_STAGES:
            continue
        row = by_stage.get(value, {"count": 0, "amount": 0})
        amount = row["amount"] or 0
        pipeline.append(
            {
                "label": label,
                "stage": value,
                "count": row["count"],
                "amount": amount,
                "percent": int(amount / max_amount * 100),
            }
        )
    return render(request, "crm/dashboard.html#pipeline", {"pipeline": pipeline})


# ---------------------------------------------------------------------------
# 取引先
# ---------------------------------------------------------------------------

COMPANY_SORTS = {
    "name": "name_kana",
    "industry": "industry",
    "rank": "rank",
    "employees": "employee_count",
    "updated": "updated_at",
}


@login_required
def company_list(request):
    """一覧 + ライブ検索 + 絞り込み + ソート + ページング。

    htmx からは同じ URL を叩き、テーブル部分だけ差し替える。
    """
    queryset = Company.objects.with_stats().select_related("owner")
    keyword = request.GET.get("q", "").strip()
    queryset = queryset.search(keyword)
    if industry := request.GET.get("industry"):
        queryset = queryset.filter(industry=industry)
    if rank := request.GET.get("rank"):
        queryset = queryset.filter(rank=rank)
    if request.GET.get("active_only"):
        queryset = queryset.filter(is_active=True)

    queryset, sort_key, descending = sorted_queryset(request, queryset, COMPANY_SORTS, "name")
    page = paginate(request, queryset)

    context = {
        "page_obj": page,
        "q": keyword,
        "sort_key": sort_key,
        "sort_desc": descending,
        "industries": Company.Industry.choices,
        "ranks": Company.Rank.choices,
        "total_count": page.paginator.count,
    }
    return render(request, partial(request, "crm/company_list.html", "results"), context)


@login_required
def company_detail(request, pk):
    company = get_object_or_404(
        Company.objects.select_related("owner").prefetch_related("contacts", "deals"), pk=pk
    )
    context = {
        "company": company,
        "deals": company.deals.select_related("owner").order_by("-created_at"),
        "activities": company.activities.select_related("created_by")[:10],
    }
    return render(request, "crm/company_detail.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def company_create(request):
    """モーダルでの新規登録。

    - GET : モーダルの中身（フォーム）を返す
    - POST 成功 : 204 No Content + `HX-Trigger` で「閉じろ」「一覧を更新しろ」と伝える
    - POST 失敗 : 422 でフォームを返し、response-targets 拡張でモーダル内に差し戻す
    """
    form = CompanyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        company = form.save()
        response = HttpResponse(status=204)
        trigger_client_event(response, "closeModal", {})
        trigger_client_event(response, "companyListChanged", {})
        return toast(response, f"取引先「{company.name}」を登録しました")

    status = 422 if request.method == "POST" else 200
    return render(
        request,
        "crm/company_form.html",
        {"form": form, "title": "取引先の新規登録", "action": "/companies/new/"},
        status=status,
    )


@login_required
@require_http_methods(["GET", "POST"])
def company_update(request, pk):
    company = get_object_or_404(Company, pk=pk)
    form = CompanyForm(request.POST or None, instance=company)
    if request.method == "POST" and form.is_valid():
        form.save()
        response = HttpResponse(status=204)
        trigger_client_event(response, "closeModal", {})
        trigger_client_event(response, "companyListChanged", {})
        return toast(response, "取引先を更新しました")

    status = 422 if request.method == "POST" else 200
    return render(
        request,
        "crm/company_form.html",
        {
            "form": form,
            "title": f"{company.name} を編集",
            "action": f"/companies/{company.pk}/edit/",
        },
        status=status,
    )


@login_required
@require_http_methods(["DELETE", "POST"])
def company_delete(request, pk):
    company = get_object_or_404(Company, pk=pk)
    name = company.name
    company.delete()

    if request.htmx and request.headers.get("HX-Target", "").startswith("company-row-"):
        # 一覧の行から消された場合: 空文字を返して行ごと消す
        response = HttpResponse("")
        trigger_client_event(response, "companyCountChanged", {})
        return toast(response, f"「{name}」を削除しました", "warning")

    # 詳細画面から消された場合: クライアント側でページ遷移させる
    messages.warning(request, f"「{name}」を削除しました")
    return HttpResponseClientRedirect("/companies/")


@login_required
@require_http_methods(["GET", "POST"])
def company_inline_field(request, pk, field):
    """クリックしてその場で編集（click-to-edit）。

    同じ URL で「表示用 HTML」と「編集フォーム」を出し分けるのがコツ。
    """
    company = get_object_or_404(Company, pk=pk)
    if field not in INLINE_EDITABLE_FIELDS["Company"]:
        return HttpResponseBadRequest("この項目はインライン編集できません")

    if request.method == "POST":
        form = build_inline_form(company, field, data=request.POST)
        if form.is_valid():
            form.save()
            response = render(
                request,
                "crm/company_detail.html#inline-display",
                {"company": company, "field": field},
            )
            return toast(response, "保存しました")
        return render(
            request,
            "crm/company_detail.html#inline-form",
            {"company": company, "field": field, "form": form},
            status=422,
        )

    if request.GET.get("edit"):
        form = build_inline_form(company, field)
        return render(
            request,
            "crm/company_detail.html#inline-form",
            {"company": company, "field": field, "form": form},
        )
    return render(
        request, "crm/company_detail.html#inline-display", {"company": company, "field": field}
    )


@login_required
@require_POST
def company_bulk_action(request):
    """チェックボックスで選択した複数行への一括操作。"""
    ids = request.POST.getlist("selected")
    action = request.POST.get("action")
    queryset = Company.objects.filter(pk__in=ids)
    count = queryset.count()

    if not count:
        response = HttpResponse(status=204)
        return toast(response, "行が選択されていません", "warning")

    match action:
        case "rank_a":
            queryset.update(rank=Company.Rank.A)
            label = f"{count} 件をランク A にしました"
        case "deactivate":
            queryset.update(is_active=False)
            label = f"{count} 件を無効化しました"
        case "activate":
            queryset.update(is_active=True)
            label = f"{count} 件を有効化しました"
        case "delete":
            queryset.delete()
            label = f"{count} 件を削除しました"
        case _:
            response = HttpResponse(status=204)
            return toast(response, "不明な操作です", "error")

    response = HttpResponse(status=204)
    trigger_client_event(response, "companyListChanged", {})
    return toast(response, label)


@login_required
def company_export_csv(request):
    """CSV ダウンロード。htmx を経由させず、素のリンクで落とすのがコツ。"""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="companies.csv"'

    # Excel に UTF-8 だと認識させるための BOM。先頭に1回だけ書く。
    # ⚠️ content_type に charset=utf-8-sig を指定してはいけない。
    #    HttpResponse.write() は呼ばれるたびに charset でエンコードするため、
    #    utf-8-sig だと「1行ごとに BOM が付く」CSV ができてしまう。
    response.write("\ufeff")

    writer = csv.writer(response)
    writer.writerow(["会社名", "カナ", "業種", "ランク", "従業員数", "電話", "住所", "担当者"])
    for company in Company.objects.select_related("owner").search(request.GET.get("q", "")):
        writer.writerow([
            company.name,
            company.name_kana,
            company.get_industry_display(),
            company.get_rank_display(),
            company.employee_count or "",
            company.phone,
            company.address,
            company.owner or "",
        ])
    return response


# ---------------------------------------------------------------------------
# 担当者
# ---------------------------------------------------------------------------

CONTACT_SORTS = {
    "name": "last_name",
    "company": "company__name",
    "title": "title",
    "updated": "updated_at",
}


@login_required
def contact_list(request):
    queryset = (
        Contact.objects.select_related("company")
        .prefetch_related("tags")
        .search(request.GET.get("q", "").strip())
    )
    if company_id := request.GET.get("company"):
        queryset = queryset.filter(company_id=company_id)
    if request.GET.get("primary_only"):
        queryset = queryset.filter(is_primary=True)

    queryset, sort_key, descending = sorted_queryset(request, queryset, CONTACT_SORTS, "name")
    page = paginate(request, queryset)
    context = {
        "page_obj": page,
        "q": request.GET.get("q", ""),
        "sort_key": sort_key,
        "sort_desc": descending,
        "companies": Company.objects.filter(is_active=True).only("id", "name"),
        "total_count": page.paginator.count,
    }
    return render(request, partial(request, "crm/contact_list.html", "results"), context)


@login_required
def contact_detail(request, pk):
    contact = get_object_or_404(
        Contact.objects.select_related("company").prefetch_related("tags"), pk=pk
    )
    return render(
        request,
        "crm/contact_detail.html",
        {
            "contact": contact,
            "activities": contact.activities.select_related("created_by")[:10],
            "deals": contact.deals.select_related("company"),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def contact_create(request):
    """こちらは 422 を使わず、常に 200 でフォームを返し直すパターン。

    company_create（422 + response-targets）と読み比べてみてほしい。
    """
    form = ContactForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        contact = form.save()
        response = HttpResponse(status=204)
        trigger_client_event(response, "closeModal", {})
        trigger_client_event(response, "contactListChanged", {})
        return toast(response, f"{contact.full_name} さんを登録しました")

    return render(
        request,
        "crm/contact_form.html",
        {"form": form, "title": "担当者の新規登録", "action": "/contacts/new/"},
    )


@login_required
@require_http_methods(["GET", "POST"])
def contact_update(request, pk):
    contact = get_object_or_404(Contact, pk=pk)
    form = ContactForm(request.POST or None, instance=contact)
    if request.method == "POST" and form.is_valid():
        form.save()
        response = HttpResponse(status=204)
        trigger_client_event(response, "closeModal", {})
        trigger_client_event(response, "contactListChanged", {})
        return toast(response, "担当者を更新しました")
    return render(
        request,
        "crm/contact_form.html",
        {
            "form": form,
            "title": f"{contact.full_name} を編集",
            "action": f"/contacts/{contact.pk}/edit/",
        },
    )


@login_required
@require_http_methods(["DELETE", "POST"])
def contact_delete(request, pk):
    contact = get_object_or_404(Contact, pk=pk)
    name = contact.full_name
    contact.delete()
    if request.htmx and request.headers.get("HX-Target", "").startswith("contact-row-"):
        return toast(HttpResponse(""), f"{name} さんを削除しました", "warning")
    messages.warning(request, f"{name} さんを削除しました")
    return HttpResponseClientRedirect("/contacts/")


@login_required
def contact_check_email(request):
    """入力途中のリアルタイムバリデーション。

    `hx-trigger="blur, keyup changed delay:500ms"` から呼ばれ、
    「そのメールアドレスは使えるか」だけを判定した小さな HTML を返す。
    """
    email = (request.GET.get("email") or "").strip().lower()
    exclude_pk = request.GET.get("pk")
    state, message = "", ""
    if email:
        queryset = Contact.objects.filter(email__iexact=email)
        if exclude_pk:
            queryset = queryset.exclude(pk=exclude_pk)
        if "@" not in email:
            state, message = "error", "メールアドレスの形式が正しくありません"
        elif owner := queryset.select_related("company").first():
            state = "error"
            message = f"{owner.company.name} の {owner.full_name} さんが使用中です"
        else:
            state, message = "ok", "このアドレスは使えます"
    return render(
        request, "crm/contact_form.html#email-feedback", {"state": state, "message": message}
    )


@login_required
def contact_options(request):
    """連動プルダウン: 取引先を選ぶと担当者の <option> を差し替える。"""
    company_id = request.GET.get("company")
    contacts = Contact.objects.filter(company_id=company_id) if company_id else Contact.objects.none()
    return render(request, "crm/deal_form.html#contact-options", {"contacts": contacts})


# ---------------------------------------------------------------------------
# 商談（カンバンボード）
# ---------------------------------------------------------------------------


def board_context():
    deals = Deal.objects.select_related("company", "owner").order_by("position", "-created_at")
    columns = []
    for value, label in Deal.Stage.choices:
        stage_deals = [d for d in deals if d.stage == value]
        columns.append(
            {
                "stage": value,
                "label": label,
                "deals": stage_deals,
                "count": len(stage_deals),
                "amount": sum((d.amount for d in stage_deals), Decimal("0")),
            }
        )
    return {"columns": columns}


@login_required
def deal_board(request):
    return render(request, partial(request, "crm/deal_board.html", "board"), board_context())


@login_required
@require_POST
def deal_move(request, pk):
    """ドラッグ&ドロップで商談カードを別ステージに移す。

    SortableJS の onEnd から htmx.ajax() を呼び、ここに POST する。
    """
    deal = get_object_or_404(Deal, pk=pk)
    stage = request.POST.get("stage")
    if stage not in dict(Deal.Stage.choices):
        return HttpResponse("不正なステージです", status=400)

    previous = deal.get_stage_display()
    deal.stage = stage
    deal.probability = Deal.DEFAULT_PROBABILITY[stage]
    deal.save(update_fields=["stage", "probability", "updated_at"])

    # 同じ列に入ったカードの並び順を、送られてきた ID 順に振り直す。
    # クライアントから届く値は信用せず、数値以外はこの時点で落としておく
    # （空の列のプレースホルダが混ざって "undefined" が飛んでくることがある）。
    ordered_ids = [i for i in request.POST.getlist("order") if i.isdigit()]
    if ordered_ids:
        by_id = Deal.objects.in_bulk([int(i) for i in ordered_ids])
        to_update = []
        for index, raw_id in enumerate(ordered_ids):
            if (obj := by_id.get(int(raw_id))) is not None:
                obj.position = index
                to_update.append(obj)
        Deal.objects.bulk_update(to_update, ["position"])

    Activity.objects.create(
        kind=Activity.Kind.NOTE,
        subject=f"ステージ変更: {previous} → {deal.get_stage_display()}",
        company=deal.company,
        deal=deal,
        created_by=request.user,
    )

    response = render(request, "crm/deal_board.html#board", board_context())
    return toast(response, f"「{deal.title}」を{deal.get_stage_display()}に移動しました")


@login_required
def deal_table(request):
    queryset = Deal.objects.select_related("company", "owner").search(request.GET.get("q", "").strip())
    if stage := request.GET.get("stage"):
        queryset = queryset.filter(stage=stage)
    if request.GET.get("open_only"):
        queryset = queryset.open()
    queryset = queryset.order_by("-updated_at")
    page = paginate(request, queryset)
    context = {
        "page_obj": page,
        "q": request.GET.get("q", ""),
        "stages": Deal.Stage.choices,
        "total_amount": queryset.total_amount(),
        "total_count": page.paginator.count,
    }
    return render(request, partial(request, "crm/deal_table.html", "results"), context)


@login_required
def deal_detail(request, pk):
    deal = get_object_or_404(Deal.objects.select_related("company", "contact", "owner"), pk=pk)
    return render(
        request,
        "crm/deal_detail.html",
        {
            "deal": deal,
            "activities": deal.activities.select_related("created_by"),
            "tasks": deal.tasks.select_related("assignee"),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def deal_create(request):
    initial = {}
    if company_id := request.GET.get("company"):
        initial["company"] = company_id
    form = DealForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        deal = form.save()
        response = HttpResponse(status=204)
        trigger_client_event(response, "closeModal", {})
        trigger_client_event(response, "dealListChanged", {})
        return toast(response, f"商談「{deal.title}」を作成しました")
    status = 422 if request.method == "POST" else 200
    return render(
        request,
        "crm/deal_form.html",
        {"form": form, "title": "商談の新規作成", "action": "/deals/new/"},
        status=status,
    )


@login_required
@require_http_methods(["GET", "POST"])
def deal_update(request, pk):
    deal = get_object_or_404(Deal, pk=pk)
    form = DealForm(request.POST or None, instance=deal)
    if request.method == "POST" and form.is_valid():
        form.save()
        response = HttpResponse(status=204)
        trigger_client_event(response, "closeModal", {})
        trigger_client_event(response, "dealListChanged", {})
        return toast(response, "商談を更新しました")
    status = 422 if request.method == "POST" else 200
    return render(
        request,
        "crm/deal_form.html",
        {"form": form, "title": f"{deal.title} を編集", "action": f"/deals/{deal.pk}/edit/"},
        status=status,
    )


@login_required
@require_http_methods(["DELETE", "POST"])
def deal_delete(request, pk):
    deal = get_object_or_404(Deal, pk=pk)
    title = deal.title
    deal.delete()
    if request.htmx and request.headers.get("HX-Target", "").startswith("deal-"):
        response = HttpResponse("")
        trigger_client_event(response, "dealListChanged", {})
        return toast(response, f"商談「{title}」を削除しました", "warning")
    messages.warning(request, f"商談「{title}」を削除しました")
    return HttpResponseClientRedirect("/deals/")


@login_required
@require_http_methods(["GET", "POST"])
def deal_inline_field(request, pk, field):
    deal = get_object_or_404(Deal, pk=pk)
    if field not in INLINE_EDITABLE_FIELDS["Deal"]:
        return HttpResponseBadRequest("この項目はインライン編集できません")

    if request.method == "POST":
        form = build_inline_form(deal, field, data=request.POST)
        if form.is_valid():
            form.save()
            response = render(
                request, "crm/deal_detail.html#inline-display", {"deal": deal, "field": field}
            )
            return toast(response, "保存しました")
        return render(
            request,
            "crm/deal_detail.html#inline-form",
            {"deal": deal, "field": field, "form": form},
            status=422,
        )
    if request.GET.get("edit"):
        return render(
            request,
            "crm/deal_detail.html#inline-form",
            {"deal": deal, "field": field, "form": build_inline_form(deal, field)},
        )
    return render(request, "crm/deal_detail.html#inline-display", {"deal": deal, "field": field})


# ---------------------------------------------------------------------------
# 活動履歴（無限スクロール）
# ---------------------------------------------------------------------------


@login_required
def activity_list(request):
    """`hx-trigger="revealed"` による無限スクロール。

    最後の要素が画面に入った瞬間に次ページを取りに行き、`beforeend` で継ぎ足す。
    """
    queryset = Activity.objects.select_related("company", "contact", "deal", "created_by")
    if kind := request.GET.get("kind"):
        queryset = queryset.filter(kind=kind)
    if keyword := request.GET.get("q", "").strip():
        queryset = queryset.filter(Q(subject__icontains=keyword) | Q(body__icontains=keyword))

    page = paginate(request, queryset, per_page=12)
    context = {
        "page_obj": page,
        "q": keyword,
        "kind": kind,
        "kinds": Activity.Kind.choices,
        "total_count": page.paginator.count,
    }
    if request.htmx and not request.htmx.boosted and request.GET.get("page"):
        # 2 ページ目以降は「行だけ」を返して継ぎ足す
        # （boost 経由＝ページ遷移のときは除く。フルページを返す必要がある）
        return render(request, "crm/activity_list.html#items", context)
    return render(request, partial(request, "crm/activity_list.html", "feed"), context)


@login_required
@require_http_methods(["GET", "POST"])
def activity_create(request):
    initial = {"occurred_at": timezone.localtime()}
    for key in ("company", "contact", "deal"):
        if value := request.GET.get(key):
            initial[key] = value
    form = ActivityForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        activity = form.save(commit=False)
        activity.created_by = request.user
        activity.save()
        response = HttpResponse(status=204)
        trigger_client_event(response, "closeModal", {})
        trigger_client_event(response, "activityListChanged", {})
        return toast(response, "活動履歴を登録しました")
    status = 422 if request.method == "POST" else 200
    return render(
        request,
        "crm/activity_form.html",
        {"form": form, "title": "活動履歴の登録", "action": "/activities/new/"},
        status=status,
    )


# ---------------------------------------------------------------------------
# タスク
# ---------------------------------------------------------------------------


@login_required
def task_list(request):
    queryset = Task.objects.select_related("assignee", "deal")
    scope = request.GET.get("scope", "mine")
    if scope == "mine":
        queryset = queryset.filter(assignee=request.user)
    if not request.GET.get("show_done"):
        queryset = queryset.filter(is_done=False)
    context = {
        "tasks": queryset,
        "scope": scope,
        "show_done": bool(request.GET.get("show_done")),
        "open_count": queryset.filter(is_done=False).count(),
    }
    return render(request, partial(request, "crm/task_list.html", "results"), context)


@login_required
@require_POST
def task_toggle(request, pk):
    """チェックボックスのトグル。

    行だけを差し替えつつ、`hx-swap-oob` でサイドバーのバッジも同時に更新する
    （= Out of Band Swap）。1 レスポンスで画面の複数箇所を書き換える技。
    """
    task = get_object_or_404(Task, pk=pk)
    task.is_done = not task.is_done
    task.save(update_fields=["is_done", "updated_at"])
    response = render(
        request,
        "crm/task_list.html#row-with-oob",
        {"task": task, "open_count": Task.objects.needs_attention(request.user).count()},
    )
    return toast(response, "完了にしました" if task.is_done else "未完了に戻しました", "info")


@login_required
@require_http_methods(["GET", "POST"])
def task_create(request):
    form = TaskForm(request.POST or None, initial={"assignee": request.user})
    if request.method == "POST" and form.is_valid():
        form.save()
        response = HttpResponse(status=204)
        trigger_client_event(response, "closeModal", {})
        trigger_client_event(response, "taskListChanged", {})
        return toast(response, "タスクを追加しました")
    status = 422 if request.method == "POST" else 200
    return render(
        request,
        "crm/task_form.html",
        {"form": form, "title": "タスクの追加", "action": "/tasks/new/"},
        status=status,
    )


@login_required
@require_http_methods(["DELETE", "POST"])
def task_delete(request, pk):
    task = get_object_or_404(Task, pk=pk)
    task.delete()
    return toast(HttpResponse(""), "タスクを削除しました", "warning")


# ---------------------------------------------------------------------------
# 学習ガイド
# ---------------------------------------------------------------------------


@login_required
def guide(request):
    return render(request, "crm/guide.html", {"now": timezone.localtime()})


@login_required
def guide_slow(request):
    """わざと 1.5 秒待つエンドポイント。`hx-indicator` の動作確認用。"""
    time.sleep(1.5)
    return render(request, "crm/guide.html#slow-result", {"now": timezone.localtime()})
