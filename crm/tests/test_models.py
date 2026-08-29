"""【単体テスト】モデル・QuerySet・プロパティ

HTTP もテンプレートも介さず、ドメインのロジックだけを検証する。
一番速く、一番壊れにくい層。ここが厚いほど上の層を薄くできる。
"""

from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from crm.models import Activity, Company, Contact, Deal, Task
from crm.tests.base import CRMTestCase


class DealPropertyTests(TestCase):
    """DB を使わずに済むものは、インスタンスを組み立てるだけで試す。"""

    def test_加重金額は金額かける確度(self):
        deal = Deal(amount=Decimal("1000000"), probability=35)
        self.assertEqual(deal.weighted_amount, Decimal("350000"))

    def test_確度0なら加重金額も0(self):
        deal = Deal(amount=Decimal("1000000"), probability=0)
        self.assertEqual(deal.weighted_amount, Decimal("0"))

    def test_進行中の判定(self):
        for stage in Deal.OPEN_STAGES:
            with self.subTest(stage=stage):
                self.assertTrue(Deal(stage=stage).is_open)
        for stage in ("won", "lost"):
            with self.subTest(stage=stage):
                self.assertFalse(Deal(stage=stage).is_open)

    def test_期限超過は進行中の商談だけ(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        self.assertTrue(Deal(stage="proposal", expected_close_date=yesterday).is_overdue)
        # 受注済みなら過去日でも「超過」ではない
        self.assertFalse(Deal(stage="won", expected_close_date=yesterday).is_overdue)
        # 予定日が無ければ判定しようがない
        self.assertFalse(Deal(stage="proposal", expected_close_date=None).is_overdue)


class ContactPropertyTests(TestCase):
    def test_氏名は姓と名をつなぐ(self):
        self.assertEqual(Contact(last_name="山田", first_name="太郎").full_name, "山田 太郎")

    def test_名が空でも余分な空白が残らない(self):
        self.assertEqual(Contact(last_name="山田", first_name="").full_name, "山田")


class TaskPropertyTests(TestCase):
    def test_期限超過は未完了のときだけ(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        self.assertTrue(Task(is_done=False, due_date=yesterday).is_overdue)
        self.assertFalse(Task(is_done=True, due_date=yesterday).is_overdue)
        self.assertFalse(Task(is_done=False, due_date=None).is_overdue)


class CompanyQuerySetTests(CRMTestCase):
    """検索条件はモデル層に寄せてあるので、ここで直接テストできる。"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.other = Company.objects.create(
            name="別会社", name_kana="ベツガイシャ", address="東京都港区"
        )

    def test_会社名で検索できる(self):
        self.assertQuerySetEqual(
            Company.objects.search("テスト"), [self.company], ordered=False
        )

    def test_カナでも住所でも検索できる(self):
        self.assertIn(self.other, Company.objects.search("ベツ"))
        self.assertIn(self.other, Company.objects.search("港区"))

    def test_空文字なら素通しする(self):
        """呼び出し側に if を書かせないための仕様。"""
        self.assertEqual(Company.objects.search("").count(), Company.objects.count())

    def test_集計をまとめて取れる(self):
        company = Company.objects.with_stats().get(pk=self.company.pk)
        self.assertEqual(company.contact_count, 1)
        self.assertEqual(company.open_deal_amount, Decimal("500000"))

    def test_受注済みの商談は進行中金額に含めない(self):
        Deal.objects.create(title="受注済み", company=self.company, amount=Decimal("999"), stage="won")
        company = Company.objects.with_stats().get(pk=self.company.pk)
        self.assertEqual(company.open_deal_amount, Decimal("500000"))

    def test_商談が無ければ0になる(self):
        """default=Decimal(0) を入れておかないと None が返る。"""
        company = Company.objects.with_stats().get(pk=self.other.pk)
        self.assertEqual(company.open_deal_amount, Decimal("0"))

    def test_一覧の集計はクエリ1本で済む(self):
        """N+1 が入り込んでいないことを、発行クエリ数で守る。"""
        with self.assertNumQueries(1):
            for company in Company.objects.with_stats().select_related("owner"):
                _ = (company.contact_count, company.open_deal_amount, company.owner)


class DealQuerySetTests(CRMTestCase):
    def test_進行中だけを取れる(self):
        Deal.objects.create(title="受注", company=self.company, stage="won")
        Deal.objects.create(title="失注", company=self.company, stage="lost")
        self.assertQuerySetEqual(Deal.objects.open(), [self.deal], ordered=False)

    def test_合計金額(self):
        Deal.objects.create(title="2件目", company=self.company, amount=Decimal("250000"))
        self.assertEqual(Deal.objects.total_amount(), Decimal("750000"))

    def test_1件も無ければ合計は0(self):
        Deal.objects.all().delete()
        self.assertEqual(Deal.objects.total_amount(), Decimal("0"))


class TaskQuerySetTests(CRMTestCase):
    """サイドバーのバッジ定義。ここがブレると画面の数字がズレる。"""

    def test_期限が今日以前の未完了タスクだけ数える(self):
        today = timezone.localdate()
        Task.objects.create(title="今日まで", assignee=self.user, due_date=today)
        Task.objects.create(title="来週", assignee=self.user, due_date=today + timedelta(days=7))
        Task.objects.create(title="完了済み", assignee=self.user, due_date=today, is_done=True)
        Task.objects.create(title="他人の", assignee=self.other_user, due_date=today)

        self.assertEqual(Task.objects.needs_attention(self.user).count(), 1)

    def test_期限なしは数えない(self):
        # base.py の self.task は due_date が None
        self.assertEqual(Task.objects.needs_attention(self.user).count(), 0)


class ConstraintTests(CRMTestCase):
    """DB レベルの制約。アプリのバリデーションをすり抜けても守られること。"""

    def test_会社名は大文字小文字を区別せず一意(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Company.objects.create(name="テスト商事")

    def test_確度は100以下(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Deal.objects.create(title="不正", company=self.company, probability=101)

    def test_金額は0以上(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Deal.objects.create(title="不正", company=self.company, amount=Decimal("-1"))


class CascadeTests(CRMTestCase):
    """外部キーの削除挙動。意図せずデータが消える/残るのを防ぐ。"""

    def test_取引先を消すと担当者と商談も消える(self):
        self.company.delete()
        self.assertFalse(Contact.objects.exists())
        self.assertFalse(Deal.objects.exists())

    def test_担当者を消しても商談は残る(self):
        """SET_NULL にしてあるので、窓口が退職しても案件は消えない。"""
        self.contact.delete()
        self.deal.refresh_from_db()
        self.assertIsNone(self.deal.contact)

    def test_ユーザーを消しても取引先は残る(self):
        self.user.delete()
        self.company.refresh_from_db()
        self.assertIsNone(self.company.owner)


class ActivityTests(CRMTestCase):
    def test_種別からアイコンが決まる(self):
        self.assertEqual(Activity(kind="call").icon, "☎")
        self.assertEqual(Activity(kind="unknown").icon, "•")

    def test_新しい順に並ぶ(self):
        now = timezone.now()
        old = Activity.objects.create(subject="古い", occurred_at=now - timedelta(days=1))
        new = Activity.objects.create(subject="新しい", occurred_at=now)
        self.assertEqual(list(Activity.objects.all()), [new, old])
