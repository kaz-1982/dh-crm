"""【E2E テスト】実ブラウザ（Playwright）で操作する層。

ここでしか検証できないのは「JavaScript が絡む部分」だけ:

  - htmx が本当に差し替えているか（ヘッダを返しただけでは分からない）
  - モーダルの開閉、トーストの表示
  - ドラッグ&ドロップ
  - スクロールによる追加読み込み
  - Out of Band Swap が離れた場所に届いているか

サーバが正しい HTML とヘッダを返すかは crm/tests/ の結合テストで済ませ、
この層は薄く保つ。遅いので、増やしすぎるとテストが回らなくなる。

    uv run playwright install chromium   # 初回だけ
    uv run python manage.py test e2e     # E2E だけ
    uv run python manage.py test --exclude-tag=e2e   # E2E を除く
"""
