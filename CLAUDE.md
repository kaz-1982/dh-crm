# CLAUDE.md

このリポジトリで作業するときの前提メモ。

## これは何か

Django 6.1 + htmx 2 の**学習用サンプル**（社内 CRM）。
実務投入するプロダクトではなく、**読んで学ぶこと**が第一目的。
そのため次の性質を持つ。

- コード中のコメントは「何をしているか」ではなく **「なぜそう書くのか」** を書く
- あえて2通りの実装を残している箇所がある
  （バリデーションエラーを 422 で返す `company_create` と 200 で返す `contact_create`）
- ハマりどころは削除せず、**コメントとして残す**（`docs/06-pitfalls.md` と対応）

## コマンド

```bash
uv run python manage.py runserver                 # 開発サーバ
uv run python manage.py test --exclude-tag=e2e    # 単体+結合 143件 / 約7秒（開発中はこれ）
uv run python manage.py test                      # 全180件（E2E 含む）/ 約35秒
uv run python manage.py seed --reset              # デモデータ再投入
uv run python manage.py check                     # 設定チェック
uv run playwright install chromium                # E2E の初回だけ
```

デモアカウント: `tanaka` / `demo1234`、管理者 `admin` / `admin1234`

## 変更するときの約束

### テンプレート

- **複数行コメントは必ず `{% comment %}`**。`{# … #}` は1行専用で、
  複数行に書くと画面にそのまま出る（何度も踏んでいる）
- htmx 用の断片は **`{% partialdef %}`** で同じファイルに置く。
  断片専用のファイルを新規に作らない
- ビューからは `partial(request, "crm/x.html", "results")` ヘルパーで返す

### htmx

- 属性は子に継承される。フォーム内に「自分でリクエストを出す要素」があるときは
  **`hx-disinherit`** を検討する
- `HX-Trigger` で複数イベントを返すときは**発火順**に注意
  （先のハンドラが DOM を壊すと後続がバブリングしない）
- 4xx/5xx は htmx が画面に出さない。**必ず `htmx:responseError` で拾う**
- インライン編集の項目は **`INLINE_EDITABLE_FIELDS` のホワイトリスト必須**

### モデル

- 検索条件は QuerySet メソッドに寄せる（`Company.objects.search(q)`）
- 一覧の集計は `annotate` でまとめて取る（N+1 を作らない）
- 同じ数字を2箇所で数えない（`Task.objects.needs_attention(user)` のように定義を1つに）

### テスト（3層。詳細は docs/07-testing.md）

| 層 | 場所 | 何を書くか |
|---|---|---|
| 単体 | `crm/tests/test_{models,forms,templatetags}.py` | ドメインのロジック。HTTP を介さない |
| 結合 | `crm/tests/test_{views,htmx}.py` | ビューを HTTP レベルで。ブラウザは使わない |
| E2E | `e2e/test_*.py` | Playwright。**JS が絡むものだけ** |

- **下の層で書けるものを E2E に置かない。** E2E は 1件 0.8 秒かかる
- htmx リクエストは `HTMX = {"HTTP_HX_REQUEST": "true"}` を渡す
- `hx-boost` の分岐を触ったら `HTTP_HX_BOOSTED` 付きのケースも足す
- **断片がフルページを含んでいないこと**を必ず確認する
  （`assertNotContains(response, "<!doctype html>")`）
- `HX-Trigger` の日本語は `\uXXXX` エスケープされるので `json.loads()` してから比較
- E2E では `fill()` ではなく `type_into()`（`press_sequentially`）を使う。
  `fill()` は `keyup` を発火しないのでライブ検索が動かない
- E2E でモーダルを開くときは `open_modal()` を使う。
  要素の存在だけを待つと htmx の処理完了前に操作してしまう
- E2E で新しいバグを見つけたら、**必ず結合テストに回帰ケースを書き直す**
- **flaky を放置しない。** 直し方は「待ち時間を伸ばす」ではなく
  「何を待つべきかを正確に書く」。`wait_for_htmx_idle()` と
  `expect(...).to_be_focused()` を使う。`wait_for_timeout` を撒かない
- E2E を触ったら `for i in 1 2 3; do ... done` で連続実行して安定を確認する

### CI

`.github/workflows/test.yml`。push と PR で `fast`（単体+結合）と
`e2e` を並列に回す。E2E 失敗時は `test-results/` の
スクリーンショットとトレースが成果物として残る。

CI で回すコマンドを変えたら、手元でも同じコマンドを流して確認すること:

```bash
uv sync --frozen
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py test --exclude-tag=e2e
E2E_TIMEOUT=15000 uv run python manage.py test e2e
```

### ドキュメント

`docs/` が学習資料の本体。コードを変えたら対応する箇所も更新する。

| 変更した場所 | 更新するドキュメント |
|---|---|
| htmx パターンを追加 | `docs/04-patterns.md` |
| バグを踏んで直した | `docs/06-pitfalls.md` |
| モデル / URL 構成 | `docs/02-architecture.md` |
| テストの書き方 | `docs/07-testing.md` |

## 依存を足すとき

`uv add パッケージ名`。ただし**慎重に**。
「ビルドツールなし・npm なし」がこのサンプルの主張なので、
crispy-forms や Tailwind を入れると題材の意味が薄れる。
JS ライブラリは `static/vendor/` に置く（CDN にしない）。
