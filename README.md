# 社内CRM — Django 6.1 + htmx 学習用サンプル

[![test](https://github.com/kaz-1982/dh-crm/actions/workflows/test.yml/badge.svg)](https://github.com/kaz-1982/dh-crm/actions/workflows/test.yml)

社内向けの顧客管理システム（CRM）を題材に、**Django 6.1 と htmx 2 の組み合わせ方**を
手を動かして学ぶためのサンプルアプリです。

React も Vue も npm も使わず、**サーバが HTML の断片を返すだけ**で、
モーダル・ライブ検索・ドラッグ&ドロップ・無限スクロール・トースト通知まで実装しています。
クライアント側の JavaScript は **約 170 行** です。

```
Python 3.13 / Django 6.1 / htmx 2.0.10 / django-htmx 1.29 / SQLite
ビルドツールなし・npm なし・CSS も素の1枚
```

---

## 動かす

```bash
uv sync && uv run python manage.py migrate && uv run python manage.py seed --reset
```

```bash
uv run python manage.py runserver
```

http://127.0.0.1:8000/ を開いて `tanaka` / `demo1234` でログイン。
（管理者は `admin` / `admin1234`）

テスト（**180 件**: 単体 70 / 結合 73 / E2E 37）:

```bash
uv run python manage.py test
```

E2E は実ブラウザ（Playwright）を使います。初回だけ:

```bash
uv run playwright install chromium
```

開発中は E2E を外すと 7 秒で回ります:

```bash
uv run python manage.py test --exclude-tag=e2e
```

CI は GitHub Actions で設定済みです（`.github/workflows/test.yml`）。
push と pull request のたびに、速い層と E2E を並列で回します。
E2E が落ちたときはスクリーンショットと Playwright トレースが成果物として残ります。

詳しくは **[docs/01-はじめかた](docs/01-getting-started.md)** と **[docs/07-テスト](docs/07-testing.md)**。

---

## 📚 ドキュメント

**[docs/](docs/README.md) に学習用の資料一式があります。**

| # | ドキュメント | 内容 |
|---|---|---|
| 01 | [はじめかた](docs/01-getting-started.md) | 環境構築、起動、よく使うコマンド |
| 02 | [アーキテクチャ](docs/02-architecture.md) | 全体像、データモデル、リクエストの流れ |
| 03 | [htmx 早見表](docs/03-htmx-reference.md) | 属性・swap・trigger・ヘッダ・イベントの一覧 |
| 04 | [実装パターン集](docs/04-patterns.md) | **20パターンをコード付きで解説（メイン）** |
| 05 | [Django 6.1 の新機能](docs/05-django-features.md) | テンプレートパーシャル、querystring、django-htmx |
| 06 | [ハマりどころ](docs/06-pitfalls.md) | 実際に踏んだバグ 15 件 |
| 07 | [テスト](docs/07-testing.md) | **単体・結合・E2E の3層。Playwright の実例つき** |
| 08 | [練習問題](docs/08-exercises.md) | 手を動かして覚える課題 12 問 |
| 09 | [本番化チェックリスト](docs/09-production.md) | 学習用のままだと困るところ |

アプリ内にも **「htmx ガイド」ページ**（`/guide/`）があり、その場で動作を試せます。

---

## 何が入っているか

| 画面 | 主な htmx の要素 |
|---|---|
| ダッシュボード | ポーリング (`every 30s`)、遅延ロード (`load`) |
| 取引先一覧 | ライブ検索、並べ替え、ページング、一括操作、CSV |
| 取引先詳細 | クリックしてその場で編集（1 URL で表示/編集を出し分け） |
| 担当者一覧 | ライブ検索、タグ表示 |
| 担当者フォーム | 入力中のメール重複チェック |
| 商談ボード | ドラッグ&ドロップ（SortableJS → `htmx.ajax()`） |
| 商談フォーム | 連動プルダウン（取引先 → 担当者） |
| 活動履歴 | 無限スクロール (`revealed`) |
| タスク | Out of Band Swap（行とサイドバーのバッジを同時更新） |
| 全画面 | `hx-boost`、トースト通知、モーダル CRUD、イベントによる疎結合 |

20パターンの詳細は [docs/04-実装パターン集](docs/04-patterns.md) にあります。

---

## 読む順番（おすすめ）

1. [docs/02-アーキテクチャ](docs/02-architecture.md) で全体像をつかむ
2. `templates/base.html` — `hx-boost` / `hx-headers` / モーダル / トースト
3. `crm/views.py` の `company_list` → `templates/crm/company_list.html`（一覧の基本形）
4. `company_create` → `company_form.html`（モーダルと `HX-Trigger`）
5. `company_inline_field` → `company_detail.html` の2つのパーシャル（インライン編集）
6. `deal_board` / `deal_move` → `static/js/app.js` の `initSortable()`
7. `task_toggle` → `task_list.html` の `row-with-oob`（OOB スワップ）
8. [docs/08-練習問題](docs/08-exercises.md) で自分で機能を足してみる

---

## ディレクトリ

```
.github/         CI（GitHub Actions）
config/          プロジェクト設定
accounts/        カスタムユーザー
crm/             ★ ドメインと htmx の実装
templates/       ★ {% partialdef %} でフルページと断片が同居
static/          CSS 1枚 + JS 約170行 + vendor（htmx / SortableJS）
e2e/             Playwright による E2E テスト
docs/            📚 学習用ドキュメント
```

各ディレクトリの詳細は [docs/02-アーキテクチャ](docs/02-architecture.md#ディレクトリ構成)。

---

## この題材の要点

**1. Django 6.0 のテンプレートパーシャルが効く**

htmx では「フルページ用」と「断片用」でテンプレートが2倍に増えがちでしたが、
1ファイルに同居させられるようになりました。

```django
{% partialdef results inline %}<div id="results">…</div>{% endpartialdef %}
```
```python
render(request, "crm/company_list.html#results", ctx)   # 断片だけ返る
```

**2. 状態はサーバにしか置かない**

「編集中かどうか」をクライアントに持たせません。
1つの URL が「表示用 HTML」と「編集フォーム」を出し分けます。

**3. 画面更新の指示はレスポンスヘッダで**

```python
trigger_client_event(response, "companyListChanged", {})
```
```django
<div id="results" hx-trigger="companyListChanged from:body" …>
```

一覧は「誰が更新したか」を知りません。イベント名だけが契約になります。
