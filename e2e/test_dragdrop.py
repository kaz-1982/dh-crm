"""【E2E】カンバンのドラッグ&ドロップ。

htmx の属性だけでは書けない、JS 起点の操作。
「SortableJS が動く → htmx.ajax でサーバへ → ボード全体が返る →
 Sortable が再初期化される」までを通しで確認する。
"""

from decimal import Decimal

from django.contrib.auth import get_user_model

from crm.models import Activity, Company, Deal
from e2e.base import PlaywrightTestCase, expect

User = get_user_model()


class KanbanDragTests(PlaywrightTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user("tester", password="pw12345678", display_name="担当")
        self.company = Company.objects.create(name="アルファ商事", name_kana="アルファ")
        self.deal = Deal.objects.create(
            title="基幹システム刷新", company=self.company,
            amount=Decimal("1000000"), stage="lead", probability=10, owner=self.user,
        )
        self.login(self.user)
        self.goto("/deals/")

    # --- ヘルパー --------------------------------------------------------

    def card(self, deal):
        return self.page.locator(f'.deal-card[data-deal-id="{deal.pk}"]')

    def column(self, stage):
        return self.page.locator(f'.board-list[data-stage="{stage}"]')

    def column_total(self, stage):
        """列ヘッダの合計金額。"""
        return self.page.locator(
            f'.board-col:has(.board-list[data-stage="{stage}"]) .sum'
        )

    def drag(self, source, target):
        """SortableJS を手で動かす。

        Playwright の drag_to は HTML5 の DragEvent を使うが、
        SortableJS は forceFallback 時にポインタイベントで動く。
        どちらでも確実に動かすため、マウスを段階的に動かす。
        中間点を挟まないと SortableJS が「移動」と認識しない。
        """
        # 差し替え直後は要素が入れ替わっている最中のことがあるので、
        # 座標を測る前に「見えている」ことを確かめる。
        expect(source).to_be_visible()
        expect(target).to_be_visible()
        src = source.bounding_box()
        dst = target.bounding_box()
        self.page.mouse.move(src["x"] + src["width"] / 2, src["y"] + src["height"] / 2)
        self.page.mouse.down()
        self.page.wait_for_timeout(50)
        # 数回に分けて動かす。1回で飛ばすと SortableJS が掴んだと認識しない
        for ratio in (0.2, 0.4, 0.6, 0.8, 1.0):
            self.page.mouse.move(
                src["x"] + (dst["x"] + dst["width"] / 2 - src["x"]) * ratio,
                src["y"] + (dst["y"] + 30 - src["y"]) * ratio,
                steps=6,
            )
            self.page.wait_for_timeout(30)
        self.page.mouse.up()
        # サーバがボードを返し終えるまで待つ。これを省くと、
        # 遅れて届いた差し替えが次の操作を壊して flaky になる。
        self.wait_for_htmx_idle()

    # --- テスト ----------------------------------------------------------

    def test_初期状態(self):
        expect(self.column("lead").locator(".deal-card")).to_have_count(1)
        expect(self.column("negotiation").locator(".deal-card")).to_have_count(0)

    def test_Sortableが全列に初期化されている(self):
        ready = self.page.evaluate(
            "() => [...document.querySelectorAll('.board-list')]"
            ".map(l => l.dataset.sortableReady)"
        )
        self.assertEqual(ready, ["1"] * 6)

    def test_カードを別の列に落とすとステージと確度が変わる(self):
        self.drag(self.card(self.deal), self.column("negotiation"))

        # ボード全体が差し替わり、カードが移動先の列にいる
        expect(self.column("negotiation").locator(".deal-card")).to_have_count(1)
        expect(self.column("lead").locator(".deal-card")).to_have_count(0)
        expect(self.toast()).to_contain_text("交渉中")

        self.deal.refresh_from_db()
        self.assertEqual(self.deal.stage, "negotiation")
        self.assertEqual(self.deal.probability, 75)   # ステージ既定の確度
        self.assert_no_console_errors()

    def test_列の集計が更新される(self):
        expect(self.column_total("lead")).to_have_text("¥1,000,000")
        expect(self.column_total("won")).to_have_text("¥0")

        self.drag(self.card(self.deal), self.column("won"))

        expect(self.column_total("won")).to_have_text("¥1,000,000")
        expect(self.column_total("lead")).to_have_text("¥0")

    def test_移動が活動履歴に記録される(self):
        self.drag(self.card(self.deal), self.column("proposal"))
        expect(self.column("proposal").locator(".deal-card")).to_have_count(1)

        activity = Activity.objects.get(deal=self.deal)
        self.assertIn("ステージ変更", activity.subject)
        self.assertEqual(activity.created_by, self.user)

    def test_差し替え後も続けてドラッグできる(self):
        """★ ここが本命。

        サーバはボード全体を返すので、SortableJS を紐づけていた DOM が
        丸ごと入れ替わる。htmx:afterSettle で初期化し直していないと、
        「1回目は動くが2回目から動かない」という壊れ方をする。
        """
        self.drag(self.card(self.deal), self.column("qualified"))
        expect(self.column("qualified").locator(".deal-card")).to_have_count(1)

        # 差し替え後の DOM でも Sortable が初期化し直されていること
        expect(self.column("qualified")).to_have_attribute("data-sortable-ready", "1")

        self.drag(self.card(self.deal), self.column("won"))
        expect(self.column("won").locator(".deal-card")).to_have_count(1)

        self.deal.refresh_from_db()
        self.assertEqual(self.deal.stage, "won")
        self.assertEqual(self.deal.probability, 100)
        self.assert_no_console_errors()

    def test_同じ列の中で並べ替えると表示順が保存される(self):
        second = Deal.objects.create(
            title="2件目の案件", company=self.company, stage="lead", position=1
        )
        self.page.reload()
        self.page.wait_for_function("() => window.htmx !== undefined")

        cards = self.column("lead").locator(".deal-card")
        expect(cards).to_have_count(2)
        self.drag(cards.nth(1), cards.nth(0))

        expect(self.toast()).to_be_visible()
        second.refresh_from_db()
        self.deal.refresh_from_db()
        self.assertLess(second.position, self.deal.position)
