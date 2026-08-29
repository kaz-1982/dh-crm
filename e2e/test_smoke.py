"""E2E の土台が動くかの最小確認。"""

from decimal import Decimal

from django.contrib.auth import get_user_model

from crm.models import Company, Contact, Deal
from e2e.base import PlaywrightTestCase, expect

User = get_user_model()


class SmokeTests(PlaywrightTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            "tester", password="pw12345678", display_name="テスト太郎"
        )
        self.company = Company.objects.create(
            name="テスト商事", name_kana="テストショウジ", industry="it", owner=self.user
        )
        Contact.objects.create(company=self.company, last_name="山田", first_name="太郎")
        Deal.objects.create(
            title="テスト案件", company=self.company, amount=Decimal("500000"), stage="proposal"
        )

    def test_未ログインならログイン画面が出る(self):
        self.page.goto(f"{self.live_server_url}/")
        expect(self.page).to_have_url(f"{self.live_server_url}/accounts/login/?next=/")
        expect(self.page.get_by_role("button", name="ログイン")).to_be_visible()

    def test_ログインしてダッシュボードに入れる(self):
        self.page.goto(f"{self.live_server_url}/accounts/login/")
        self.page.get_by_label("ユーザー名").fill("tester")
        self.page.get_by_label("パスワード").fill("pw12345678")
        self.page.get_by_role("button", name="ログイン").click()

        expect(self.page.get_by_role("heading", name="ダッシュボード")).to_be_visible()
        self.assert_no_console_errors()

    def test_htmxが読み込まれている(self):
        self.login(self.user)
        self.goto("/")
        self.assertEqual(self.page.evaluate("htmx.version"), "2.0.10")

    def test_主要画面をひと通り開ける(self):
        self.login(self.user)
        for path, heading in [
            ("/", "ダッシュボード"),
            ("/companies/", "取引先"),
            ("/contacts/", "担当者"),
            ("/deals/", "商談ボード"),
            ("/activities/", "活動履歴"),
            ("/tasks/", "タスク"),
            ("/guide/", "htmx 学習ガイド"),
        ]:
            with self.subTest(path=path):
                self.goto(path)
                expect(self.page.get_by_role("heading", name=heading).first).to_be_visible()
        self.assert_no_console_errors()
