# 05. Django 6.1 の新機能とライブラリ

htmx と組み合わせるうえで効いてくる Django 側の機能をまとめます。

---

## 1. テンプレートパーシャル（Django 6.0 で標準搭載）★最重要

### 何が問題だったか

htmx を使うと、同じ画面に対して2つのテンプレートが必要になりがちでした。

```
company_list.html          ← フルページ
_company_list_rows.html    ← htmx 用の断片
```

断片を `{% include %}` する形にすればファイルは分けられますが、
画面が増えるほど「断片ファイル」が散らかっていきます。
これまでは `django-template-partials` というサードパーティ製ライブラリで
解決するのが定番でした。

### Django 6.0 からは標準機能

**1つのファイルの中に、名前を付けた断片を定義できます。**

```django
{% extends "base.html" %}
{% block content %}

  {% partialdef results inline %}
    <div id="results">
      …テーブル…
    </div>
  {% endpartialdef %}

{% endblock %}
```

ビューからは `#名前` を付けて呼びます。

```python
render(request, "crm/company_list.html", ctx)           # フルページ
render(request, "crm/company_list.html#results", ctx)   # 断片だけ
```

### `inline` の有無

| 書き方 | 挙動 |
|---|---|
| `{% partialdef results inline %}` | **その場にも描画される**。フルページでもそのまま使える |
| `{% partialdef results %}` | 定義だけ。使うときは `{% partial results %}` で呼び出す |

「一覧の中身」のように**その位置に出したいもの**は `inline`、
「インライン編集の表示用と編集用」のように**出し分けたいもの**は `inline` なし、
と使い分けます。

```django
{# 定義だけしておいて… #}
{% partialdef inline-display %}
<div class="inline-edit" …>{{ display_value }}</div>
{% endpartialdef %}

{# 好きな場所で、好きな変数を渡して呼ぶ #}
<dd>{% with field="phone" %}{% partial inline-display %}{% endwith %}</dd>
<dd>{% with field="address" %}{% partial inline-display %}{% endwith %}</dd>
```

### 知っておくと便利な性質

| 性質 | 内容 |
|---|---|
| `{% extends %}` の中でも使える | `{% block %}` の内側に書いてよい（このアプリはそうしている） |
| 前方参照できる | `{% partial items %}` を、定義より前に書いてもよい |
| 他のファイルからも読める | `{% include "crm/task_list.html#row-with-oob" %}` が通る |
| 同名は禁止 | 同じテンプレート内で名前が重複すると `TemplateSyntaxError` |
| 終了タグに名前を付けられる | `{% endpartialdef results %}`（長い断片で読みやすくなる） |

### このアプリでのパーシャル一覧

| テンプレート | パーシャル名 | 用途 |
|---|---|---|
| `dashboard.html` | `kpi` / `pipeline` | ポーリング / 遅延ロード |
| `company_list.html` | `results` | 検索・ソート・ページング |
| `company_detail.html` | `inline-display` / `inline-form` | クリックして編集 |
| `contact_list.html` | `results` | 一覧 |
| `contact_form.html` | `email-feedback` | 入力中の重複チェック |
| `deal_board.html` | `board` | カンバン全体 |
| `deal_form.html` | `contact-options` | 連動プルダウン |
| `deal_detail.html` | `inline-display` / `inline-form` | クリックして編集 |
| `activity_list.html` | `feed` / `items` | 一覧 / 無限スクロールの追加分 |
| `task_list.html` | `results` / `row-with-oob` | 一覧 / 行＋バッジ同時更新 |
| `guide.html` | `slow-result` | hx-indicator のデモ |

---

## 2. `{% querystring %}` タグ（Django 5.1）

「いまの GET パラメータを保ったまま、一部だけ差し替えた URL」を作ります。
ページングとソートには**ほぼ必須**です。

```django
{# 現在の条件 + page=2 #}
{% querystring page=page_obj.next_page_number %}

{# 現在の条件からキーを削除 #}
{% querystring industry=None %}

{# 変数に受けて使い回す #}
{% querystring sort='name' dir=d as qs %}
<a href="{% url 'crm:company_list' %}{{ qs }}" hx-get="{% url 'crm:company_list' %}{{ qs }}">
```

これが無かった頃は、テンプレートタグを自作するか、
ビューでクエリ文字列を組み立ててコンテキストに詰める必要がありました。

> **注意**: `{% querystring %}` は `context.request` を使うので、
> `django.template.context_processors.request` が有効である必要があります（既定で有効）。

---

## 3. カスタムユーザーモデル

```python
# accounts/models.py
class User(AbstractUser):
    display_name = models.CharField("表示名", max_length=50, blank=True)
    department = models.CharField("部署", max_length=20, choices=Department, blank=True)
    ...
```

```python
# config/settings.py
AUTH_USER_MODEL = "accounts.User"
```

**プロジェクトを始めた最初のマイグレーション前にやってください。**
あとから差し替えるのは非常に大変です（既存の FK をすべて張り替える必要がある）。
「今は要らない」と思っても、空の `AbstractUser` サブクラスを置いておくのが定石です。

---

## 4. django-htmx

### ミドルウェア

```python
MIDDLEWARE = [
    ...
    "django_htmx.middleware.HtmxMiddleware",   # 認証・メッセージの後ろに
]
```

これだけで `request.htmx` が使えます。

```python
if request.htmx:
    return render(request, "crm/company_list.html#results", ctx)
return render(request, "crm/company_list.html", ctx)
```

### レスポンスヘルパー

```python
from django_htmx.http import (
    HttpResponseClientRedirect,   # HX-Redirect（クライアント側でページ遷移）
    HttpResponseClientRefresh,    # HX-Refresh（丸ごとリロード）
    HttpResponseLocation,         # HX-Location（ajax で遷移）
    HttpResponseStopPolling,      # HTTP 286（ポーリング停止）
    push_url, replace_url,        # HX-Push-Url / HX-Replace-Url
    retarget, reswap, reselect,   # HX-Retarget / HX-Reswap / HX-Reselect
    trigger_client_event,         # HX-Trigger
)
```

`trigger_client_event` は同じレスポンスに何度でも積めます（JSON にマージされる）。

```python
response = HttpResponse(status=204)
trigger_client_event(response, "closeModal", {})
trigger_client_event(response, "companyListChanged", {})
trigger_client_event(response, "toast", {"message": "保存しました", "level": "success"})
```

生成されるヘッダ:

```
HX-Trigger: {"closeModal": {}, "companyListChanged": {}, "toast": {"message": "…", "level": "success"}}
```

> 日本語は `\uXXXX` にエスケープされます。テストで中身を確認するときは
> 文字列比較ではなく `json.loads()` してください（[07. テスト](07-testing.md) 参照）。

---

## 5. モデル層の書き方

### QuerySet メソッドで検索条件を持つ

```python
class CompanyQuerySet(models.QuerySet):
    def search(self, keyword: str):
        if not keyword:
            return self       # 空なら素通し。呼ぶ側に if を書かせない
        return self.filter(Q(name__icontains=keyword) | Q(name_kana__icontains=keyword))

class Company(TimeStampedModel):
    objects = CompanyQuerySet.as_manager()
```

チェーンできるので、ビューが読みやすくなります。

```python
Company.objects.with_stats().select_related("owner").search(q).filter(rank="a")
```

### `annotate` で N+1 を潰す

一覧に「担当者数」「進行中金額」を出すために、行ごとにクエリを投げてはいけません。

```python
def with_stats(self):
    return self.annotate(
        contact_count=models.Count("contacts", distinct=True),
        open_deal_amount=Sum("deals__amount",
                             filter=Q(deals__stage__in=Deal.OPEN_STAGES),
                             default=Decimal("0")),
    )
```

`Sum(..., filter=...)` は「条件付き集計」です。SQL の `SUM(CASE WHEN … END)` になります。

### DB レベルの制約

アプリのバリデーションだけでは、管理コマンドや直接 SQL をすり抜けます。

```python
class Meta:
    constraints = [
        # 会社名は大文字小文字を区別せず一意
        models.UniqueConstraint(models.functions.Lower("name"), name="company_name_unique_ci"),
    ]
```

```python
class Meta:
    constraints = [
        models.CheckConstraint(condition=Q(probability__lte=100), name="deal_probability_lte_100"),
        models.CheckConstraint(condition=Q(amount__gte=0), name="deal_amount_gte_0"),
    ]
```

> `CheckConstraint` の引数名は Django 5.1 で `check` から **`condition`** に変わりました。
> 古い記事のコードをコピーすると警告が出ます。

### TextChoices / IntegerChoices

```python
class Stage(models.TextChoices):
    LEAD = "lead", "リード"
    QUALIFIED = "qualified", "案件化"
    WON = "won", "受注"

stage = models.CharField("ステージ", max_length=20, choices=Stage, default=Stage.LEAD)
```

- テンプレートでは `{{ deal.get_stage_display }}` で日本語ラベルが出る
- `Deal.Stage.choices` でプルダウンの選択肢になる
- Django 5.0 から `choices=Stage`（`.choices` を付けなくてよい）

---

## 6. SQLite の設定（開発用として侮らない）

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
            "transaction_mode": "IMMEDIATE",
        },
    }
}
```

- **WAL モード**: 読み取りが書き込みをブロックしなくなる
- **`transaction_mode: IMMEDIATE`**（Django 5.1+）: 書き込みロックを最初に取り、
  `database is locked` エラーを大幅に減らす

htmx を使うと画面あたりのリクエスト数が増えるので、この2つは効きます。

---

## 7. Django 6.1 で変わったところ（このアプリで踏んだもの）

| 項目 | 変更 |
|---|---|
| メール設定 | `EMAIL_BACKEND` ではなく **`MAILERS`** 辞書形式 |
| `CheckConstraint` | `check=` → **`condition=`**（5.1 で変更） |
| `choices` | `choices=Stage.choices` → **`choices=Stage`** でよい（5.0 から） |
| テンプレートパーシャル | **標準搭載**（6.0 から） |
| `{% querystring %}` | **標準搭載**（5.1 から） |

```python
# config/settings.py
MAILERS = {
    "default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"},
}
```
