"""【単体テスト】テンプレートタグ

テンプレートタグは「ただの関数」なので、直接呼べばテストできる。
render_to_string を通す必要があるのは、タグの登録まで含めて確かめたいときだけ。
"""

from datetime import date
from decimal import Decimal

from django.template import Context, Template
from django.test import TestCase

from crm.models import Company, Deal
from crm.templatetags.crm_extras import model_label, model_value, next_dir, yen
from crm.tests.base import CRMTestCase


class ModelValueTests(TestCase):
    """インライン編集で「フィールド名を変数で受け取って値を出す」ための関数。"""

    def test_選択肢のあるフィールドは表示ラベルを返す(self):
        company = Company(rank="a")
        self.assertEqual(model_value(company, "rank"), "A（重要顧客）")

    def test_数値は3桁区切りになる(self):
        self.assertEqual(model_value(Company(employee_count=1234567), "employee_count"), "1,234,567")
        self.assertEqual(model_value(Deal(amount=Decimal("500000")), "amount"), "500,000")

    def test_日付は日本語の書式になる(self):
        deal = Deal(expected_close_date=date(2026, 3, 9))
        self.assertEqual(model_value(deal, "expected_close_date"), "2026年3月9日")

    def test_空の値は空文字を返す(self):
        """テンプレート側で default:"—" を効かせるため、None ではなく空文字。"""
        self.assertEqual(model_value(Company(phone=""), "phone"), "")
        self.assertEqual(model_value(Company(employee_count=None), "employee_count"), "")

    def test_通常の文字列はそのまま(self):
        self.assertEqual(model_value(Company(phone="03-1234-5678"), "phone"), "03-1234-5678")

    def test_ラベルを取れる(self):
        self.assertEqual(model_label(Company(), "employee_count"), "従業員数")


class YenFilterTests(TestCase):
    def test_金額に記号と区切りを付ける(self):
        self.assertEqual(yen(1234567), "¥1,234,567")
        self.assertEqual(yen(Decimal("500000")), "¥500,000")

    def test_ゼロも表示する(self):
        self.assertEqual(yen(0), "¥0")

    def test_値が無ければダッシュ(self):
        self.assertEqual(yen(None), "—")
        self.assertEqual(yen(""), "—")


class SortTagTests(TestCase):
    """並べ替えリンクの向きを決めるタグ。"""

    def test_別の列なら昇順から始まる(self):
        context = {"sort_key": "name", "sort_desc": False}
        self.assertEqual(next_dir(context, "industry"), "asc")

    def test_同じ列を昇順で見ているなら次は降順(self):
        context = {"sort_key": "name", "sort_desc": False}
        self.assertEqual(next_dir(context, "name"), "desc")

    def test_同じ列を降順で見ているなら次は昇順に戻る(self):
        context = {"sort_key": "name", "sort_desc": True}
        self.assertEqual(next_dir(context, "name"), "asc")


class RenderedTagTests(CRMTestCase):
    """タグの登録とテンプレートからの呼び出しまで含めた確認。"""

    def render(self, template_string, **context):
        return Template("{% load crm_extras %}" + template_string).render(Context(context))

    def test_asで変数に受けられる(self):
        html = self.render(
            '{% model_value company "rank" as v %}[{{ v }}]', company=self.company
        )
        self.assertEqual(html, "[B（通常）]")

    def test_空のときdefaultフィルタが効く(self):
        """simple_tag の戻り値に直接フィルタは掛けられないので as で受ける。"""
        html = self.render(
            '{% model_value company "phone" as v %}{{ v|default:"—" }}', company=self.company
        )
        self.assertEqual(html, "—")

    def test_並べ替え中の列に矢印が出る(self):
        html = self.render(
            "{% sort_indicator 'name' %}", sort_key="name", sort_desc=True
        )
        self.assertIn("▼", html)

    def test_並べ替えていない列には何も出ない(self):
        html = self.render("{% sort_indicator 'industry' %}", sort_key="name", sort_desc=False)
        self.assertEqual(html.strip(), "")
