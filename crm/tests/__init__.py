"""CRM のテスト。

    crm/tests/
      base.py             共通のテストデータ
      test_models.py      【単体】モデル・QuerySet・プロパティ
      test_forms.py       【単体】フォームのバリデーション
      test_templatetags.py【単体】テンプレートタグ
      test_views.py       【結合】ビューを HTTP レベルで
      test_htmx.py        【結合】htmx 固有の振る舞い

    e2e/                  【E2E】実ブラウザ（Playwright）

詳しくは docs/07-testing.md を参照。
"""
