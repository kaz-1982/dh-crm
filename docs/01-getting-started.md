# 01. はじめかた

## 必要なもの

- [uv](https://docs.astral.sh/uv/)（Python のバージョン管理と依存解決を両方やってくれる）

Python 自体を先に入れる必要はありません。`uv sync` が `.python-version` を見て
CPython 3.13 を自動でダウンロードします。

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## セットアップ

```bash
uv sync
```

```bash
uv run python manage.py migrate
```

```bash
uv run python manage.py seed --reset
```

```bash
uv run python manage.py runserver
```

http://127.0.0.1:8000/ を開きます。

### ログイン情報

| 用途 | ユーザー名 | パスワード | 備考 |
|---|---|---|---|
| 営業担当 | `tanaka` | `demo1234` | 通常の利用者。まずはこれで |
| 〃 | `suzuki` / `sato` / `yamada` | `demo1234` | 担当者を切り替えて見え方を比べる用 |
| 管理者 | `admin` | `admin1234` | `/admin/` にも入れる |

---

## よく使うコマンド

```bash
uv run python manage.py test
```

```bash
uv run python manage.py test crm.tests.PartialTests -v 2
```

```bash
uv run python manage.py seed --reset
```

```bash
uv run python manage.py makemigrations && uv run python manage.py migrate
```

```bash
uv run python manage.py shell
```

```bash
uv run python manage.py check
```

依存を足すとき:

```bash
uv add パッケージ名
```

---

## 開発中に知っておくと楽なこと

### 静的ファイルがキャッシュされる問題は対策済み

CSS や JS を直しても反映されない、というのは開発中の定番ストレスです。
`crm/context_processors.py` の `asset_version` が `DEBUG=True` のとき
ファイルの更新時刻をクエリに付けるので、**リロードすれば必ず最新**になります。

```django
<link rel="stylesheet" href="{% static 'css/app.css' %}{{ asset_v }}">
```

本番では `ManifestStaticFilesStorage` がファイル名にハッシュを埋め込むので、
この仕組みは `DEBUG=False` では無効になります（`config/settings.py` の `STORAGES`）。

### htmx の通信を目で見る

ブラウザの DevTools を開いて Network タブを **Fetch/XHR** で絞ると、
htmx が投げているリクエストと、返ってきた HTML 断片がそのまま読めます。
JSON API と違って**レスポンスがそのまま画面の一部**なので、デバッグは驚くほど簡単です。

htmx のログを全部出したいときは、コンソールで:

```js
htmx.logAll()
```

### データを作り直したい

```bash
rm -f db.sqlite3 && uv run python manage.py migrate && uv run python manage.py seed
```

`seed` は `random.seed()` を固定してあるので、何度実行しても同じデータになります。

---

## つまずいたら

| 症状 | 原因と対処 |
|---|---|
| `no such table` | `migrate` を忘れている |
| ログインできない | `seed` を実行していない。`--reset` 付きで再実行 |
| CSS が変わらない | 上記の対策が入っているのでスーパーリロード（Cmd+Shift+R）で確実に直る |
| htmx が何も起きない | DevTools のコンソールを見る。`hx-target` のセレクタ間違いは黙って失敗せずエラーを出す |
| 403 Forbidden | CSRF トークン。`base.html` の `hx-headers` が効いているか確認 |

より詳しくは [06. ハマりどころ](06-pitfalls.md) を参照。
