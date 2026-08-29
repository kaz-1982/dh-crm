"""テスト共通のデータとヘルパー。"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from crm.models import Company, Contact, Deal, Tag, Task

User = get_user_model()

#: htmx からのリクエストを再現するヘッダ。
#: テストクライアントでは HTTP_ プレフィックスを付けて渡す。
HTMX = {"HTTP_HX_REQUEST": "true"}


class CRMTestCase(TestCase):
    """ログイン済みユーザーと最低限のデータを用意する基底クラス。

    setUpTestData はクラスごとに1回しか走らないので、
    テストメソッドごとに作り直す setUp より大幅に速い。
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            "tester", password="pw12345678", display_name="テスト太郎"
        )
        cls.other_user = User.objects.create_user("other", password="pw12345678")
        cls.tag = Tag.objects.create(name="決裁者", color="#dc2626")

        cls.company = Company.objects.create(
            name="テスト商事",
            name_kana="テストショウジ",
            industry="it",
            rank="b",
            employee_count=100,
            owner=cls.user,
        )
        cls.contact = Contact.objects.create(
            company=cls.company,
            last_name="山田",
            first_name="太郎",
            kana="ヤマダタロウ",
            email="yamada@example.com",
            is_primary=True,
        )
        cls.deal = Deal.objects.create(
            title="テスト案件",
            company=cls.company,
            contact=cls.contact,
            amount=Decimal("500000"),
            stage="proposal",
            probability=50,
            owner=cls.user,
        )
        cls.task = Task.objects.create(title="やること", assignee=cls.user)

    def setUp(self):
        # force_login はパスワード検証を飛ばすので、毎回のログインが速い
        self.client.force_login(self.user)
