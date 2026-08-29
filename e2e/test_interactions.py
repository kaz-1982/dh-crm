"""【E2E】htmx の差し替えが実ブラウザで本当に起きているか。

ここに書くのは「サーバのレスポンスを見ただけでは分からないこと」だけ。
ステータスコードやヘッダの検証は crm/tests/test_htmx.py の担当。
"""

import re
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from crm.models import Activity, Company, Contact, Deal, Task
from e2e.base import PlaywrightTestCase, expect

User = get_user_model()


class BaseFlowTest(PlaywrightTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            "tester", password="pw12345678", display_name="テスト太郎"
        )
        self.company = Company.objects.create(
            name="アルファ商事", name_kana="アルファショウジ", industry="it",
            phone="03-1111-1111", owner=self.user,
        )
        self.other = Company.objects.create(
            name="ベータ工業", name_kana="ベータコウギョウ", industry="manufacturing"
        )
        self.contact = Contact.objects.create(
            company=self.company, last_name="山田", first_name="太郎", email="yamada@example.com"
        )
        self.deal = Deal.objects.create(
            title="基幹システム刷新", company=self.company,
            amount=Decimal("500000"), stage="proposal", probability=50,
        )
        self.login(self.user)


class LiveSearchTests(BaseFlowTest):
    def test_入力すると一覧が絞り込まれる(self):
        self.goto("/companies/")
        rows = self.page.locator("#results tbody tr")
        expect(rows).to_have_count(2)

        self.type_into(self.page.get_by_placeholder("会社名・カナ・住所で検索…"), "ベータ")

        # デバウンス(350ms)のあと差し替わる。明示的な待ちは書かない —
        # expect() が条件を満たすまでポーリングしてくれる。
        expect(rows).to_have_count(1)
        expect(rows.first).to_contain_text("ベータ工業")
        self.assert_no_console_errors()

    def test_検索するとURLも変わる(self):
        """hx-push-url。リロード・戻る・URL 共有が成立する条件。"""
        self.goto("/companies/")
        self.type_into(self.page.get_by_placeholder("会社名・カナ・住所で検索…"), "ベータ")
        expect(self.page.locator("#results tbody tr")).to_have_count(1)
        expect(self.page).to_have_url(re.compile(r"q=%E3%83%99"))   # 「ベ」で始まる

    def test_リロードしても絞り込みが残る(self):
        self.goto("/companies/")
        self.type_into(self.page.get_by_placeholder("会社名・カナ・住所で検索…"), "ベータ")
        expect(self.page.locator("#results tbody tr")).to_have_count(1)

        self.page.reload()
        expect(self.page.locator("#results tbody tr")).to_have_count(1)
        expect(self.page.get_by_placeholder("会社名・カナ・住所で検索…")).to_have_value("ベータ")

    def test_ブラウザの戻るで検索前に戻れる(self):
        self.goto("/companies/")
        self.type_into(self.page.get_by_placeholder("会社名・カナ・住所で検索…"), "ベータ")
        expect(self.page.locator("#results tbody tr")).to_have_count(1)

        self.page.go_back()
        expect(self.page.locator("#results tbody tr")).to_have_count(2)

    def test_絞り込みで0件になると空表示が出る(self):
        self.goto("/companies/")
        self.type_into(self.page.get_by_placeholder("会社名・カナ・住所で検索…"), "該当なし")
        expect(self.page.get_by_text("条件に一致する取引先がありません")).to_be_visible()

    def test_業種の絞り込みも同じフォームから効く(self):
        self.goto("/companies/")
        self.page.locator("#filters select[name=industry]").select_option("manufacturing")
        expect(self.page.locator("#results tbody tr")).to_have_count(1)
        expect(self.page.locator("#results tbody tr").first).to_contain_text("ベータ工業")


class ModalTests(BaseFlowTest):
    def open_new_company_modal(self):
        self.goto("/companies/")
        return self.open_modal("＋ 新規登録")

    def test_モーダルが開く(self):
        self.open_new_company_modal()
        expect(self.page.get_by_role("heading", name="取引先の新規登録")).to_be_visible()
        self.assert_no_console_errors()

    def test_保存するとモーダルが閉じトーストが出て一覧が増える(self):
        """★ 実際に踏んだバグの回帰テスト。

        サーバは HX-Trigger で closeModal / companyListChanged / toast を
        まとめて返す。htmx はこれを「リクエストを出した要素」の上で順に
        発火させるため、closeModal を受けて即 modal-body を空にすると
        フォームが DOM から外れ、後続イベントが body に届かなくなる。

        結果、モーダルは閉じるのに一覧が更新されない、という
        「片方だけ動く」壊れ方をする。ここを一気に通しで押さえる。
        """
        self.open_new_company_modal()
        self.page.locator("dialog#modal input[name=name]").fill("ガンマ流通")
        self.page.locator("dialog#modal button[type=submit]").click()

        # ① モーダルが閉じる
        expect(self.page.locator("dialog#modal")).to_be_hidden()
        # ② トーストが出る
        expect(self.toast()).to_contain_text("ガンマ流通")
        # ③ 一覧が更新される（← これが落ちるのが件のバグ）
        expect(self.page.locator("#results tbody tr")).to_have_count(3)
        expect(self.page.locator("#results")).to_contain_text("ガンマ流通")

        self.assert_no_console_errors()

    def test_バリデーションエラーはモーダル内に表示され入力値も残る(self):
        self.open_new_company_modal()
        self.page.locator("dialog#modal input[name=name]").fill("アルファ商事")  # 重複
        self.page.locator("dialog#modal button[type=submit]").click()

        expect(self.page.locator("dialog#modal")).to_be_visible()
        expect(self.page.get_by_text("同じ会社名がすでに登録されています")).to_be_visible()
        expect(self.page.locator("dialog#modal input[name=name]")).to_have_value("アルファ商事")
        self.assertEqual(Company.objects.count(), 2)

    def test_エラーを直せば保存できる(self):
        self.open_new_company_modal()
        self.page.locator("dialog#modal input[name=name]").fill("アルファ商事")
        self.page.locator("dialog#modal button[type=submit]").click()
        expect(self.page.get_by_text("同じ会社名がすでに登録されています")).to_be_visible()

        self.page.locator("dialog#modal input[name=name]").fill("デルタ建設")
        self.page.locator("dialog#modal button[type=submit]").click()

        expect(self.page.locator("dialog#modal")).to_be_hidden()
        self.assertTrue(Company.objects.filter(name="デルタ建設").exists())

    def test_キャンセルで閉じて何も起きない(self):
        self.open_new_company_modal()
        self.page.locator("dialog#modal input[name=name]").fill("保存しない会社")
        self.page.get_by_role("button", name="キャンセル").click()

        expect(self.page.locator("dialog#modal")).to_be_hidden()
        self.assertEqual(Company.objects.count(), 2)

    def test_閉じたあと開き直すとフォームは空(self):
        """モーダルの中身を片付けていないと前回の入力が残る。"""
        self.open_new_company_modal()
        self.page.locator("dialog#modal input[name=name]").fill("入力途中")
        self.page.get_by_role("button", name="キャンセル").click()
        expect(self.page.locator("dialog#modal")).to_be_hidden()

        self.open_modal("＋ 新規登録")
        expect(self.page.locator("dialog#modal input[name=name]")).to_have_value("")


class LiveValidationTests(BaseFlowTest):
    def test_入力中にメールの重複を知らせる(self):
        self.goto("/contacts/")
        modal = self.open_modal("＋ 新規登録")
        email = modal.locator("input[name=email]")

        self.type_into(email, "yamada@example.com")
        expect(self.page.locator("#email-feedback")).to_contain_text("使用中です")

        self.type_into(email, "free@example.com")
        expect(self.page.locator("#email-feedback")).to_contain_text("使えます")
        self.assert_no_console_errors()

    def test_取引先を選ぶと担当者の選択肢が入れ替わる(self):
        self.goto("/deals/")
        modal = self.open_modal("＋ 新規商談")

        options = self.page.locator("#id_contact option")
        expect(options).to_have_count(1)   # 最初は空選択肢だけ

        modal.locator("select[name=company]").select_option(label="アルファ商事")
        expect(options).to_have_count(2)
        expect(self.page.locator("#id_contact")).to_contain_text("山田 太郎")


class InlineEditTests(BaseFlowTest):
    def test_クリックして編集し保存すると表示に戻る(self):
        self.goto(f"/companies/{self.company.pk}/")
        field = self.page.locator("#field-phone")
        expect(field).to_contain_text("03-1111-1111")

        field.click()
        edit_input = field.locator("input[name=phone]")
        expect(edit_input).to_be_visible()
        expect(edit_input).to_be_focused()          # autofocus が効いている

        edit_input.fill("06-9999-8888")
        field.locator("button[type=submit]").click()

        expect(self.page.locator("#field-phone")).to_contain_text("06-9999-8888")
        expect(self.page.locator("#field-phone input")).to_have_count(0)
        expect(self.toast()).to_contain_text("保存しました")

        self.company.refresh_from_db()
        self.assertEqual(self.company.phone, "06-9999-8888")
        self.assert_no_console_errors()

    def test_取り消すと元に戻り保存されない(self):
        self.goto(f"/companies/{self.company.pk}/")
        field = self.page.locator("#field-phone")
        field.click()
        field.locator("input[name=phone]").fill("00-0000-0000")
        field.locator("button[data-cancel]").click()

        expect(self.page.locator("#field-phone")).to_contain_text("03-1111-1111")
        self.company.refresh_from_db()
        self.assertEqual(self.company.phone, "03-1111-1111")

    def test_Escキーでも取り消せる(self):
        self.goto(f"/companies/{self.company.pk}/")
        field = self.page.locator("#field-phone")
        field.click()
        expect(field.locator("input[name=phone]")).to_be_visible()

        self.page.keyboard.press("Escape")
        expect(self.page.locator("#field-phone input")).to_have_count(0)
        expect(self.page.locator("#field-phone")).to_contain_text("03-1111-1111")

    def test_何度でも往復できる(self):
        """差し替えた断片にも hx-* が残っていないと2回目が動かない。"""
        self.goto(f"/companies/{self.company.pk}/")
        for value in ["11-1111-1111", "22-2222-2222", "33-3333-3333"]:
            field = self.page.locator("#field-phone")
            field.click()
            field.locator("input[name=phone]").fill(value)
            field.locator("button[type=submit]").click()
            expect(self.page.locator("#field-phone")).to_contain_text(value)


class DeleteTests(BaseFlowTest):
    def test_確認して削除すると行が消える(self):
        self.page.on("dialog", lambda dialog: dialog.accept())
        self.goto("/companies/")
        rows = self.page.locator("#results tbody tr")
        expect(rows).to_have_count(2)

        row = self.page.locator(f"#company-row-{self.other.pk}")
        row.hover()
        row.get_by_title("削除").click()

        expect(rows).to_have_count(1)
        expect(self.toast()).to_contain_text("削除しました")
        self.assertFalse(Company.objects.filter(pk=self.other.pk).exists())

    def test_確認をキャンセルすると何も起きない(self):
        self.page.on("dialog", lambda dialog: dialog.dismiss())
        self.goto("/companies/")

        row = self.page.locator(f"#company-row-{self.other.pk}")
        row.hover()
        row.get_by_title("削除").click()

        expect(self.page.locator("#results tbody tr")).to_have_count(2)
        self.assertTrue(Company.objects.filter(pk=self.other.pk).exists())


class OutOfBandTests(BaseFlowTest):
    def test_チェックすると行とサイドバーのバッジが同時に変わる(self):
        today = timezone.localdate()
        task = Task.objects.create(
            title="見積書を作成する", assignee=self.user, due_date=today
        )
        Task.objects.create(title="もう1件", assignee=self.user, due_date=today)

        self.goto("/tasks/")
        badge = self.page.locator("#task-badge")
        expect(badge).to_have_text("2")

        self.page.locator(f"#task-row-{task.pk} input[type=checkbox]").check()

        # ① 行が差し替わる
        expect(self.page.locator(f"#task-row-{task.pk} input[type=checkbox]")).to_be_checked()
        # ② 離れた場所のバッジも同じレスポンスで更新される
        expect(badge).to_have_text("1")
        expect(self.toast()).to_contain_text("完了にしました")
        self.assert_no_console_errors()


class InfiniteScrollTests(BaseFlowTest):
    def test_下までスクロールすると追加で読み込まれる(self):
        for i in range(30):
            Activity.objects.create(
                subject=f"活動記録 {i:02d}", company=self.company,
                occurred_at=timezone.now() - timedelta(minutes=i),
            )
        self.goto("/activities/")
        items = self.page.locator("#activity-items > li")
        expect(items).to_have_count(12)          # 1ページ目

        self.page.mouse.wheel(0, 20_000)
        expect(items).to_have_count(24)          # 2ページ目が継ぎ足された

        self.page.mouse.wheel(0, 20_000)
        expect(items).to_have_count(30)          # 全部出たら止まる

        self.page.mouse.wheel(0, 20_000)
        expect(items).to_have_count(30)          # それ以上は増えない
        self.assert_no_console_errors()


class BoostTests(BaseFlowTest):
    def test_リンク遷移でページ全体をリロードしない(self):
        """hx-boost。<body> の中身だけ差し替わるので、
        ページ読み込み前に仕込んだ印が生き残る。"""
        self.goto("/companies/")
        self.page.evaluate("window.__survived = true")

        self.page.locator('.sidebar a[href="/contacts/"]').click()
        expect(self.page.get_by_role("heading", name="担当者")).to_be_visible()

        self.assertTrue(self.page.evaluate("window.__survived === true"))
        expect(self.page).to_have_url(f"{self.live_server_url}/contacts/")

    def test_CSVリンクはboostから除外されている(self):
        self.goto("/companies/")
        link = self.page.locator('a[href^="/companies/export/"]')
        self.assertEqual(link.get_attribute("hx-boost"), "false")


class DashboardTests(BaseFlowTest):
    def test_パイプラインが遅延ロードされる(self):
        self.goto("/")
        # hx-trigger="load" なので、少し遅れて中身が入る
        expect(self.page.get_by_text("提案中")).to_be_visible()
        self.assert_no_console_errors()

    def test_KPIカードにポーリングが設定されている(self):
        self.goto("/")
        kpi = self.page.locator("#kpi")
        self.assertIn("every 30s", kpi.get_attribute("hx-trigger"))
