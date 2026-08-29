"""【結合テスト】htmx 固有の振る舞い

htmx を使うと、テストで見るべきものが2つ増える。

  1. 同じ URL が「フルページ」と「断片」の2つの顔を持つ
     → うっかりフルページを返すと、レイアウトが入れ子になって画面が壊れる
  2. 返す HTML ではなく、レスポンス「ヘッダ」に指示が乗る
     → 本文が空(204)でも、画面は正しく動かなければならない

どちらもブラウザ無しで検証できる。E2E に持ち込む必要はない。
"""

import json

from django.urls import reverse

from crm.models import Activity, Company, Contact, Deal, Task
from crm.tests.base import HTMX, CRMTestCase


def triggers(response) -> dict:
    """HX-Trigger ヘッダを辞書にして返す。

    日本語は JSON で \\uXXXX にエスケープされるため、
    文字列の in で比較すると必ず失敗する。必ずパースすること。
    """
    return json.loads(response["HX-Trigger"])


class FragmentTests(CRMTestCase):
    """htmx のときだけ断片を返すこと。htmx 対応で最も壊れやすい部分。"""

    def test_一覧はhtmxだとレイアウトを含まない(self):
        full = self.client.get(reverse("crm:company_list"))
        self.assertContains(full, "<!doctype html>")

        fragment = self.client.get(reverse("crm:company_list"), **HTMX)
        self.assertNotContains(fragment, "<!doctype html>")
        self.assertNotContains(fragment, "<body")
        self.assertContains(fragment, 'id="results"')
        self.assertContains(fragment, "テスト商事")

    def test_断片にも更新用の属性が残っている(self):
        """outerHTML で差し替えるので、断片自身が hx-* を持っていないと
        2回目以降の更新ができなくなる。"""
        fragment = self.client.get(reverse("crm:company_list"), **HTMX)
        self.assertContains(fragment, 'hx-get=')
        self.assertContains(fragment, "companyListChanged from:body")

    def test_断片を返す一覧を洗い出す(self):
        for name, marker in [
            ("crm:company_list", 'id="results"'),
            ("crm:contact_list", 'id="results"'),
            ("crm:deal_table", 'id="results"'),
            ("crm:deal_board", 'id="board"'),
            ("crm:task_list", 'id="results"'),
            ("crm:activity_list", 'id="feed"'),
        ]:
            with self.subTest(name=name):
                response = self.client.get(reverse(name), **HTMX)
                self.assertNotContains(response, "<!doctype html>")
                self.assertContains(response, marker)

    def test_KPIパーシャルが単体で描画できる(self):
        response = self.client.get(reverse("crm:dashboard_kpi"), **HTMX)
        self.assertContains(response, 'id="kpi"')
        self.assertContains(response, "every 30s")      # ポーリングが継続する
        self.assertNotContains(response, "<body")

    def test_パイプラインの遅延ロード(self):
        response = self.client.get(reverse("crm:dashboard_pipeline"), **HTMX)
        self.assertContains(response, "提案中")
        self.assertNotContains(response, "<body")

    def test_無限スクロールの2ページ目は項目だけ(self):
        """コンテナを含めて返すと、追加のたびに入れ子になっていく。"""
        for i in range(20):
            Activity.objects.create(subject=f"活動{i}", company=self.company)
        response = self.client.get(reverse("crm:activity_list"), {"page": 2}, **HTMX)
        self.assertNotContains(response, 'id="feed"')
        self.assertNotContains(response, 'id="activity-items"')
        self.assertContains(response, "<li")

    def test_最後の項目に次ページのトリガーが乗る(self):
        for i in range(20):
            Activity.objects.create(subject=f"活動{i}", company=self.company)
        response = self.client.get(reverse("crm:activity_list"), **HTMX)
        self.assertContains(response, 'hx-trigger="revealed"')
        self.assertContains(response, "page=2")

    def test_最終ページには次ページのトリガーが無い(self):
        response = self.client.get(reverse("crm:activity_list"), **HTMX)
        self.assertNotContains(response, 'hx-trigger="revealed"')


class BoostedRequestTests(CRMTestCase):
    """hx-boost はページ遷移。断片を返してはいけない。

    hx-boost 経由のリクエストも HX-Request: true を送ってくるので、
    request.htmx だけで分岐すると「サイドバーのリンクを押した瞬間に
    レイアウトが消える」という壊れ方をする（E2E で発見）。
    """

    BOOSTED = {"HTTP_HX_REQUEST": "true", "HTTP_HX_BOOSTED": "true"}

    def test_boost経由ならフルページを返す(self):
        for name in [
            "crm:company_list", "crm:contact_list", "crm:deal_table",
            "crm:deal_board", "crm:task_list", "crm:activity_list",
        ]:
            with self.subTest(name=name):
                response = self.client.get(reverse(name), **self.BOOSTED)
                self.assertContains(response, "<!doctype html>")
                self.assertContains(response, 'class="sidebar"')

    def test_boostでない普通のhtmxなら断片を返す(self):
        response = self.client.get(reverse("crm:company_list"), **HTMX)
        self.assertNotContains(response, "<!doctype html>")

    def test_boost経由のページ指定でもフルページ(self):
        for i in range(20):
            Activity.objects.create(subject=f"活動{i}", company=self.company)
        response = self.client.get(
            reverse("crm:activity_list"), {"page": 2}, **self.BOOSTED
        )
        self.assertContains(response, "<!doctype html>")


class ModalTests(CRMTestCase):
    def test_フォームを取得できる(self):
        response = self.client.get(reverse("crm:company_create"), **HTMX)
        self.assertContains(response, "取引先の新規登録")
        self.assertContains(response, "<form")
        self.assertNotContains(response, "<!doctype html>")

    def test_保存成功は204とヘッダで指示する(self):
        response = self.client.post(
            reverse("crm:company_create"),
            {"name": "新規会社", "industry": "it", "rank": "b"}, **HTMX,
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")

        payload = triggers(response)
        self.assertIn("closeModal", payload)          # モーダルを閉じろ
        self.assertIn("companyListChanged", payload)  # 一覧を更新しろ
        self.assertIn("新規会社", payload["toast"]["message"])
        self.assertTrue(Company.objects.filter(name="新規会社").exists())

    def test_イベントの順序が意図どおり(self):
        """closeModal が先に来ると、モーダル内のフォームが DOM から外れ、
        後続イベントが body までバブリングしなくなる（実際に踏んだバグ）。
        JS 側で片付けを遅延させて対処しているが、順序自体も固定しておく。"""
        response = self.client.post(
            reverse("crm:company_create"),
            {"name": "順序確認", "industry": "it", "rank": "b"}, **HTMX,
        )
        self.assertEqual(
            list(triggers(response)), ["closeModal", "companyListChanged", "toast"]
        )

    def test_方式A_バリデーションエラーは422(self):
        response = self.client.post(
            reverse("crm:company_create"),
            {"name": "テスト商事", "industry": "it", "rank": "b"}, **HTMX,   # 重複
        )
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "すでに登録されています", status_code=422)
        self.assertContains(response, 'hx-target-422', status_code=422)

    def test_方式A_入力値が保持される(self):
        response = self.client.post(
            reverse("crm:company_create"),
            {"name": "テスト商事", "industry": "manufacturing", "rank": "a"}, **HTMX,
        )
        self.assertContains(response, 'value="テスト商事"', status_code=422)

    def test_方式B_担当者フォームは200でエラーを返す(self):
        response = self.client.post(reverse("crm:contact_create"), {"last_name": ""}, **HTMX)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "このフィールドは必須です")

    def test_編集フォームには既存値が入る(self):
        response = self.client.get(
            reverse("crm:company_update", args=[self.company.pk]), **HTMX
        )
        self.assertContains(response, 'value="テスト商事"')
        self.assertContains(response, f"/companies/{self.company.pk}/edit/")


class LiveValidationTests(CRMTestCase):
    def test_使用済みのメールを知らせる(self):
        response = self.client.get(
            reverse("crm:contact_check_email"), {"email": "yamada@example.com"}
        )
        self.assertContains(response, "使用中です")
        self.assertContains(response, "テスト商事")     # 誰が使っているか分かる
        self.assertContains(response, 'id="email-feedback"')

    def test_使えるメールを知らせる(self):
        response = self.client.get(reverse("crm:contact_check_email"), {"email": "free@example.com"})
        self.assertContains(response, "使えます")

    def test_形式が不正なら教える(self):
        response = self.client.get(reverse("crm:contact_check_email"), {"email": "notanemail"})
        self.assertContains(response, "形式が正しくありません")

    def test_編集中は自分自身を重複扱いしない(self):
        response = self.client.get(
            reverse("crm:contact_check_email"),
            {"email": "yamada@example.com", "pk": self.contact.pk},
        )
        self.assertContains(response, "使えます")

    def test_大文字小文字を区別しない(self):
        response = self.client.get(
            reverse("crm:contact_check_email"), {"email": "YAMADA@EXAMPLE.COM"}
        )
        self.assertContains(response, "使用中です")


class CascadingSelectTests(CRMTestCase):
    def test_選んだ取引先の担当者だけ返る(self):
        other = Company.objects.create(name="別会社")
        Contact.objects.create(company=other, last_name="鈴木")
        response = self.client.get(reverse("crm:contact_options"), {"company": self.company.pk})
        self.assertContains(response, "山田")
        self.assertNotContains(response, "鈴木")

    def test_取引先未指定なら空選択肢だけ(self):
        response = self.client.get(reverse("crm:contact_options"))
        self.assertContains(response, "<option")
        self.assertNotContains(response, "山田")

    def test_optionタグだけを返す(self):
        """select の innerHTML に入れるので、余計なタグがあってはならない。"""
        response = self.client.get(reverse("crm:contact_options"), {"company": self.company.pk})
        body = response.content.decode().strip()
        self.assertTrue(body.startswith("<option"))
        self.assertNotIn("<select", body)


class InlineEditTests(CRMTestCase):
    def url(self, field="phone"):
        return reverse("crm:company_inline_field", args=[self.company.pk, field])

    def test_同じURLで表示と編集が切り替わる(self):
        display = self.client.get(self.url(), **HTMX)
        self.assertContains(display, "inline-edit")
        self.assertNotContains(display, "<form")

        edit = self.client.get(self.url(), {"edit": "1"}, **HTMX)
        self.assertContains(edit, "<form")
        self.assertContains(edit, 'name="phone"')

    def test_保存すると表示用HTMLが返る(self):
        response = self.client.post(self.url(), {"phone": "03-1234-5678"}, **HTMX)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "03-1234-5678")
        self.assertNotContains(response, "<form")
        self.assertIn("toast", triggers(response))
        self.company.refresh_from_db()
        self.assertEqual(self.company.phone, "03-1234-5678")

    def test_選択肢のある項目は表示ラベルが返る(self):
        response = self.client.post(self.url("rank"), {"rank": "a"}, **HTMX)
        self.assertContains(response, "A（重要顧客）")

    def test_エラーなら422でフォームに戻す(self):
        response = self.client.post(
            reverse("crm:deal_inline_field", args=[self.deal.pk, "probability"]),
            {"probability": "150"}, **HTMX,
        )
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "<form", status_code=422)

    def test_ホワイトリスト外の項目は400(self):
        """URL に項目名が入る設計なので、ここが最後の砦。"""
        for field in ["is_active", "owner", "created_at"]:
            with self.subTest(field=field):
                self.assertEqual(self.client.get(self.url(field), {"edit": "1"}).status_code, 400)
                self.assertEqual(self.client.post(self.url(field), {field: "x"}).status_code, 400)

    def test_表示と編集の両方が同じ要素を差し替える(self):
        """どちらも closest .inline-edit を outerHTML で置き換えるので、
        往復しても DOM が入れ子にならない。"""
        for response in [
            self.client.get(self.url(), **HTMX),
            self.client.get(self.url(), {"edit": "1"}, **HTMX),
        ]:
            body = response.content.decode()
            # class="inline-edit" を持つ要素はどちらも1つだけ
            # （hx-target="closest .inline-edit" の出現は数えない）
            self.assertEqual(body.count('class="inline-edit"'), 1)


class OutOfBandTests(CRMTestCase):
    def test_行とバッジをまとめて返す(self):
        response = self.client.post(reverse("crm:task_toggle", args=[self.task.pk]), **HTMX)
        self.assertContains(response, f'id="task-row-{self.task.pk}"')
        self.assertContains(response, 'id="task-badge"')
        self.assertContains(response, 'hx-swap-oob="true"')

    def test_トグルで完了状態が変わる(self):
        self.client.post(reverse("crm:task_toggle", args=[self.task.pk]), **HTMX)
        self.task.refresh_from_db()
        self.assertTrue(self.task.is_done)

        self.client.post(reverse("crm:task_toggle", args=[self.task.pk]), **HTMX)
        self.task.refresh_from_db()
        self.assertFalse(self.task.is_done)

    def test_バッジの数はコンテキストプロセッサと一致する(self):
        """2箇所で別々に数えると、リロードした瞬間に数字が変わる。"""
        from django.utils import timezone
        today = timezone.localdate()
        Task.objects.create(title="期限切れ", assignee=self.user, due_date=today)
        Task.objects.create(title="来月", assignee=self.user, due_date=today.replace(day=28))

        page = self.client.get(reverse("crm:task_list"))
        expected = page.context["badge_my_tasks"]

        toggle = self.client.post(reverse("crm:task_toggle", args=[self.task.pk]), **HTMX)
        self.assertContains(toggle, f'id="task-badge" class="count" hx-swap-oob="true">{expected}<')


class BoardTests(CRMTestCase):
    def test_移動後はボード全体が返る(self):
        response = self.client.post(
            reverse("crm:deal_move", args=[self.deal.pk]), {"stage": "won"}, **HTMX
        )
        self.assertContains(response, 'id="board"')
        self.assertContains(response, "リード")    # 全列が含まれる
        self.assertContains(response, "失注")
        self.assertNotContains(response, "<!doctype html>")

    def test_移動でトーストが返る(self):
        response = self.client.post(
            reverse("crm:deal_move", args=[self.deal.pk]), {"stage": "won"}, **HTMX
        )
        self.assertIn("受注", triggers(response)["toast"]["message"])


class EventContractTests(CRMTestCase):
    """サーバが投げるイベント名は、一覧側の hx-trigger との「契約」。
    どちらか片方だけ変えると、静かに更新されなくなる。"""

    CONTRACTS = [
        ("companyListChanged", "crm:company_list", "crm:company_create",
         {"name": "契約確認社", "industry": "it", "rank": "b"}),
        ("contactListChanged", "crm:contact_list", "crm:contact_create",
         {"company": None, "last_name": "契約"}),
    ]

    def test_サーバが投げるイベントを一覧が待ち受けている(self):
        for event, list_name, create_name, data in self.CONTRACTS:
            with self.subTest(event=event):
                if "company" in data and data["company"] is None:
                    data = data | {"company": self.company.pk}

                created = self.client.post(reverse(create_name), data, **HTMX)
                self.assertIn(event, triggers(created), f"{create_name} が {event} を投げていない")

                listing = self.client.get(reverse(list_name), **HTMX)
                self.assertContains(
                    listing, f"{event} from:body",
                    msg_prefix=f"{list_name} が {event} を待ち受けていない",
                )
