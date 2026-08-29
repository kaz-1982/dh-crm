# 09. 本番化チェックリスト

このアプリは**学習用**です。社内で実際に運用するなら、以下を潰す必要があります。
「なぜ必要か」も書いたので、要否は自分の状況で判断してください。

---

## 1. セキュリティ（必須）

### 設定

```python
# config/settings.py
import os

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]     # ハードコードを外す
DEBUG = False
ALLOWED_HOSTS = os.environ["DJANGO_ALLOWED_HOSTS"].split(",")

CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
X_FRAME_OPTIONS = "DENY"
```

チェックコマンドがあります。

```bash
uv run python manage.py check --deploy
```

> `DEBUG = True` のまま公開すると、例外画面に**設定値とソースコードが全部出ます**。
> 最優先で直してください。

### デモアカウントを消す

`crm/management/commands/seed.py` が作る `tanaka` / `admin` などは、
**パスワードがドキュメントに書いてあります**。本番投入前に必ず削除してください。

```python
# seed コマンド自体を本番で実行できないようにする例
if not settings.DEBUG:
    raise CommandError("seed は開発環境専用です")
```

### 権限管理（このアプリの最大の穴）

いまは **「ログインしていれば全社の全データが見える」** 状態です。
`login_required` しか掛かっていません。

最低限やること:

```python
# crm/models.py
class CompanyQuerySet(models.QuerySet):
    def visible_to(self, user):
        if user.is_superuser:
            return self
        return self.filter(Q(owner=user) | Q(owner__department=user.department))
```

```python
# crm/views.py — 全ての入口で使う
company = get_object_or_404(Company.objects.visible_to(request.user), pk=pk)
```

> **htmx を使うと入口が増えます**（インライン編集、一括操作、連動プルダウン…）。
> 一覧だけ絞っても、`/companies/999/field/name/` を直接叩かれたら終わりです。
> **すべてのビューで QuerySet を絞る**か、`django-guardian` のような
> オブジェクト権限ライブラリを検討してください。

### インライン編集のホワイトリスト

すでに実装済み（`INLINE_EDITABLE_FIELDS`）ですが、
モデルを増やしたら**必ず**追加してください。忘れると任意の項目が書き換えられます。

---

## 2. データベース

SQLite は開発には十分ですが、複数人で書き込む社内システムなら PostgreSQL へ。

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["DB_NAME"],
        "USER": os.environ["DB_USER"],
        "PASSWORD": os.environ["DB_PASSWORD"],
        "HOST": os.environ["DB_HOST"],
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
}
```

### 検索を作り直す

いまの検索は `icontains` です。件数が増えると遅くなり、日本語の精度も低いです。

| 件数の目安 | 対応 |
|---|---|
| 〜数千件 | `icontains` のままでよい。インデックスを張る |
| 〜数十万件 | PostgreSQL の全文検索（`SearchVector` + GIN インデックス）|
| それ以上 | Meilisearch / OpenSearch などの外部エンジン |

日本語は形態素解析が要るので、PostgreSQL なら `pg_bigm` や `pgroonga` を検討します。

### インデックス

一覧のソート対象と検索対象には索引が要ります。
現在は `Company.name`、`Contact.email`、`Deal.stage`、`Activity.occurred_at` に付いています。
絞り込み条件を足したら、`EXPLAIN` を見て判断してください。

---

## 3. 静的ファイル

設定は済んでいます（`DEBUG=False` で `ManifestStaticFilesStorage` に切り替わる）。

```bash
uv run python manage.py collectstatic --noinput
```

配信は WhiteNoise か、リバースプロキシ（nginx）に任せます。

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",   # ← ここ
    ...
]
```

### htmx を CDN にしない

このアプリは `static/vendor/` にファイルを置いています。これは意図的です。

- 社内システムは**インターネットに出られない環境**で動くことがある
- CDN が落ちるとアプリが壊れる
- バージョンが勝手に変わらない

CDN を使うなら、最低限 `integrity` 属性（SRI）を付けてください。

---

## 4. パフォーマンス

### N+1 を監視する

htmx で一覧を頻繁に叩くようになるので、N+1 の影響が大きくなります。

```bash
uv add --dev django-debug-toolbar nplusone
```

現状すでに `select_related` / `prefetch_related` / `annotate` は入れてありますが、
機能を足すたびに確認してください。

### CSV エクスポートの上限

```python
# crm/views.py: company_export_csv — 現在は全件をメモリに載せる
for company in Company.objects.select_related("owner").search(...):
```

数万件を超えると危険です。

- `StreamingHttpResponse` に変える
- あるいは件数上限を設けて「絞り込んでから出力してください」と促す
- 大量出力は非同期ジョブ（Celery / django-tasks）にしてメールで送る

### ポーリングの負荷

KPI カードは 30 秒ごとに全ユーザーぶん飛びます。
100 人が開いていれば **1 分あたり 200 リクエスト**です。

- 集計結果を数十秒キャッシュする（`cache.get_or_set`）
- 間隔を伸ばす
- 画面が非表示のときは止める（htmx は要素が消えれば止まりますが、
  タブが裏に回っただけでは止まりません）

---

## 5. 運用

### ログ

```python
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {"level": "ERROR", "propagate": True},
    },
}
```

エラー通知は Sentry などを検討してください。
**htmx はエラーを画面に出さない**ので、ユーザーからの報告が上がってきません。
サーバ側のログが唯一の手がかりになります。

### 監査ログ

「誰がいつ何を変えたか」は社内システムでは必須になりがちです。
このアプリは商談のステージ変更だけ `Activity` に記録していますが、
本格的にやるなら `django-simple-history` などを検討します。

とくに **`HttpResponse(status=204)` を返している箇所**（モーダルの保存、一括操作）は
画面に痕跡が残らないので、意識的にログを残してください。

### バックアップ

```bash
uv run python manage.py dumpdata --natural-foreign --natural-primary \
  -e contenttypes -e auth.Permission > backup.json
```

実運用では DB のダンプ（`pg_dump`）を定期取得します。

---

## 6. コード品質

```bash
uv add --dev ruff
```

```bash
uv run ruff check . && uv run ruff format .
```

`pyproject.toml` に設定を足す例:

```toml
[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "DJ"]   # DJ = flake8-django
```

CI（GitHub Actions など）で `ruff check` と `manage.py test` を回せば、
このドキュメントに書いたハマりどころの多くは自動で防げます。

---

## 7. 落とさなくていいもの

学習用だからといって、**これらは本番でもそのままで問題ありません**。

| 項目 | 理由 |
|---|---|
| ビルドツールなしの CSS 1枚 | 社内システムの規模なら十分。Tailwind を入れる必要はない |
| `static/js/app.js` が素の JS | 160行にビルド工程を用意する意味はない |
| htmx をローカルに置く | むしろ推奨（上記参照） |
| `<dialog>` を使ったモーダル | 標準要素。アクセシビリティも自前実装より確実 |
| テンプレートパーシャル | Django 標準機能。将来も維持される |

**htmx を選んだ最大の利点は、これらを「足さなくてよい」ことです。**
本番化のチェックリストが短いのは、htmx を使った設計のご褒美だと思ってください。
