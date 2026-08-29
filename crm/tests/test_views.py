"""【結合テスト】ビューを HTTP レベルで

Django のテストクライアントは、URL 解決 → ミドルウェア → ビュー →
テンプレート描画までを通す。ブラウザは使わないので JavaScript は動かない。

「サーバが正しい HTML と正しいステータスを返すか」はここで担保し、
「ブラウザがそれをどう扱うか」だけを E2E に任せる、と切り分ける。
"""

import csv
import io

from django.urls import reverse

from crm.models import Activity, Company, Contact, Deal, Task
from crm.tests.base import HTMX, CRMTestCase


class AuthTests(CRMTestCase):
    def setUp(self):
        pass  # あえてログインしない

    def test_未ログインならログイン画面へ飛ばされる(self):
        response = self.client.get(reverse("crm:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_保護されている画面を洗い出す(self):
        """login_required の付け忘れを機械的に検出する。"""
        urls = [
            reverse("crm:dashboard"),
            reverse("crm:company_list"),
            reverse("crm:company_detail", args=[self.company.pk]),
            reverse("crm:contact_list"),
            reverse("crm:deal_board"),
            reverse("crm:activity_list"),
            reverse("crm:task_list"),
            reverse("crm:company_export"),
            reverse("crm:company_inline_field", args=[self.company.pk, "phone"]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 302)

    def test_ログインすれば入れる(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("crm:dashboard")).status_code, 200)


class PageTests(CRMTestCase):
    def test_一覧系がすべて200を返す(self):
        names = [
            "crm:dashboard", "crm:company_list", "crm:contact_list",
            "crm:deal_board", "crm:deal_table", "crm:activity_list",
            "crm:task_list", "crm:guide",
        ]
        for name in names:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_詳細系がすべて200を返す(self):
        for url in [
            self.company.get_absolute_url(),
            self.contact.get_absolute_url(),
            self.deal.get_absolute_url(),
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_存在しないIDは404(self):
        self.assertEqual(self.client.get("/companies/999999/").status_code, 404)

    def test_一覧に必要な情報が出ている(self):
        response = self.client.get(reverse("crm:company_list"))
        self.assertContains(response, "テスト商事")
        self.assertContains(response, "¥500,000")   # 進行中金額の集計
        self.assertContains(response, "テスト太郎") # 営業担当

    def test_詳細ページの表示(self):
        response = self.client.get(self.company.get_absolute_url())
        self.assertContains(response, "テスト商事")
        self.assertContains(response, "山田 太郎")
        self.assertContains(response, "テスト案件")

    def test_一覧の発行クエリ数を抑える(self):
        """機能追加で N+1 が混入したら気づけるようにしておく。"""
        with self.assertNumQueries(6):
            self.client.get(reverse("crm:company_list"))


class SearchAndSortTests(CRMTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        Company.objects.create(name="アイウエオ社", name_kana="アイウエオ", industry="finance", rank="a")

    def test_キーワードで絞り込める(self):
        response = self.client.get(reverse("crm:company_list"), {"q": "テスト"})
        self.assertContains(response, "テスト商事")
        self.assertNotContains(response, "アイウエオ社")

    def test_業種で絞り込める(self):
        response = self.client.get(reverse("crm:company_list"), {"industry": "finance"})
        self.assertContains(response, "アイウエオ社")
        self.assertNotContains(response, "テスト商事")

    def test_昇順(self):
        body = self.client.get(
            reverse("crm:company_list"), {"sort": "name", "dir": "asc"}
        ).content.decode()
        self.assertLess(body.index("アイウエオ社"), body.index("テスト商事"))

    def test_降順(self):
        body = self.client.get(
            reverse("crm:company_list"), {"sort": "name", "dir": "desc"}
        ).content.decode()
        self.assertLess(body.index("テスト商事"), body.index("アイウエオ社"))

    def test_知らない並び順キーは既定値に落ちる(self):
        """order_by にユーザー入力をそのまま渡さないための防御。"""
        response = self.client.get(
            reverse("crm:company_list"), {"sort": "owner__password", "dir": "asc"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["sort_key"], "name")

    def test_ページングが効く(self):
        for i in range(20):
            Company.objects.create(name=f"会社{i:02d}")
        page1 = self.client.get(reverse("crm:company_list"))
        self.assertEqual(len(page1.context["page_obj"].object_list), 15)
        page2 = self.client.get(reverse("crm:company_list"), {"page": 2})
        self.assertEqual(page2.context["page_obj"].number, 2)


class DeleteTests(CRMTestCase):
    def test_一覧の行から消すと空レスポンスが返る(self):
        response = self.client.delete(
            reverse("crm:company_delete", args=[self.company.pk]),
            HTTP_HX_TARGET=f"company-row-{self.company.pk}",
            **HTMX,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")
        self.assertFalse(Company.objects.filter(pk=self.company.pk).exists())

    def test_詳細から消すとクライアントリダイレクト(self):
        response = self.client.delete(
            reverse("crm:company_delete", args=[self.company.pk]), HTTP_HX_TARGET="body", **HTMX
        )
        self.assertEqual(response["HX-Redirect"], "/companies/")

    def test_GETでは削除できない(self):
        """require_http_methods が効いていること。"""
        response = self.client.get(reverse("crm:company_delete", args=[self.company.pk]))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(Company.objects.filter(pk=self.company.pk).exists())


class BulkActionTests(CRMTestCase):
    def test_ランクを一括変更できる(self):
        other = Company.objects.create(name="対象会社")
        response = self.client.post(
            reverse("crm:company_bulk"),
            {"selected": [self.company.pk, other.pk], "action": "rank_a"},
            **HTMX,
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(Company.objects.filter(rank="a").count(), 2)

    def test_一括削除(self):
        self.client.post(
            reverse("crm:company_bulk"), {"selected": [self.company.pk], "action": "delete"}, **HTMX
        )
        self.assertFalse(Company.objects.exists())

    def test_知らない操作は何もしない(self):
        self.client.post(
            reverse("crm:company_bulk"), {"selected": [self.company.pk], "action": "drop_table"},
            **HTMX,
        )
        self.assertTrue(Company.objects.filter(pk=self.company.pk).exists())

    def test_GETでは実行できない(self):
        self.assertEqual(self.client.get(reverse("crm:company_bulk")).status_code, 405)


class DealMoveTests(CRMTestCase):
    def test_ステージ移動で確度も自動更新される(self):
        self.client.post(
            reverse("crm:deal_move", args=[self.deal.pk]),
            {"stage": "won", "order": [self.deal.pk]},
            **HTMX,
        )
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.stage, "won")
        self.assertEqual(self.deal.probability, 100)

    def test_移動が活動履歴に残る(self):
        self.client.post(
            reverse("crm:deal_move", args=[self.deal.pk]), {"stage": "negotiation"}, **HTMX
        )
        activity = Activity.objects.get(deal=self.deal)
        self.assertIn("ステージ変更", activity.subject)
        self.assertIn("提案中", activity.subject)
        self.assertIn("交渉中", activity.subject)
        self.assertEqual(activity.created_by, self.user)

    def test_並び順が送られた順に振り直される(self):
        second = Deal.objects.create(title="2件目", company=self.company, stage="proposal")
        self.client.post(
            reverse("crm:deal_move", args=[self.deal.pk]),
            {"stage": "proposal", "order": [second.pk, self.deal.pk]},
            **HTMX,
        )
        second.refresh_from_db()
        self.deal.refresh_from_db()
        self.assertEqual(second.position, 0)
        self.assertEqual(self.deal.position, 1)

    def test_数値でないIDが混ざっても落ちない(self):
        """空の列に落とすと、プレースホルダ由来の "undefined" が
        order に混ざって飛んでくる（E2E で発見）。"""
        response = self.client.post(
            reverse("crm:deal_move", args=[self.deal.pk]),
            {"stage": "won", "order": ["undefined", str(self.deal.pk), ""]},
            **HTMX,
        )
        self.assertEqual(response.status_code, 200)
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.stage, "won")
        self.assertEqual(self.deal.position, 0)   # 有効な ID だけで採番される

    def test_存在しないIDが混ざっても落ちない(self):
        response = self.client.post(
            reverse("crm:deal_move", args=[self.deal.pk]),
            {"stage": "won", "order": ["999999", str(self.deal.pk)]},
            **HTMX,
        )
        self.assertEqual(response.status_code, 200)

    def test_不正なステージは400(self):
        response = self.client.post(
            reverse("crm:deal_move", args=[self.deal.pk]), {"stage": "unknown"}, **HTMX
        )
        self.assertEqual(response.status_code, 400)
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.stage, "proposal")


class TaskViewTests(CRMTestCase):
    def test_既定では自分の未完了タスクだけ出る(self):
        Task.objects.create(title="他人のタスク", assignee=self.other_user)
        Task.objects.create(title="完了済み", assignee=self.user, is_done=True)
        response = self.client.get(reverse("crm:task_list"))
        self.assertContains(response, "やること")
        self.assertNotContains(response, "他人のタスク")
        self.assertNotContains(response, "完了済み")

    def test_全員分も見られる(self):
        Task.objects.create(title="他人のタスク", assignee=self.other_user)
        response = self.client.get(reverse("crm:task_list"), {"scope": "all"})
        self.assertContains(response, "他人のタスク")

    def test_完了も表示できる(self):
        Task.objects.create(title="完了済み", assignee=self.user, is_done=True)
        response = self.client.get(reverse("crm:task_list"), {"show_done": "1"})
        self.assertContains(response, "完了済み")


class ExportTests(CRMTestCase):
    def export(self, **params):
        return self.client.get(reverse("crm:company_export"), params)

    def test_CSVがダウンロードできる(self):
        response = self.export()
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("companies.csv", response["Content-Disposition"])

    def test_BOMは先頭に1回だけ(self):
        """content_type に charset=utf-8-sig を指定すると、
        HttpResponse.write() のたびに BOM が付き「行ごとに BOM」になる。
        Excel で開くと壊れて見えるので、ここで固定する。"""
        body = self.export().content
        self.assertTrue(body.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(body.count(b"\xef\xbb\xbf"), 1)

    def test_CSVの中身が正しい(self):
        text = self.export().content.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text)))
        self.assertEqual(rows[0][0], "会社名")
        self.assertEqual(rows[1][0], "テスト商事")
        self.assertEqual(rows[1][2], "IT・ソフトウェア")   # コード値ではなく表示ラベル

    def test_検索条件が引き継がれる(self):
        Company.objects.create(name="出力されない会社")
        text = self.export(q="テスト").content.decode("utf-8-sig")
        self.assertIn("テスト商事", text)
        self.assertNotIn("出力されない会社", text)
