"""【単体テスト】フォームのバリデーション

フォームは「HTTP を介さずに直接インスタンス化してテストできる」ことを
忘れられがちだが、ビュー経由より速く、失敗時の原因も分かりやすい。
"""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from crm.forms import CompanyForm, ContactForm, DealForm, build_inline_form
from crm.models import Company, Contact
from crm.tests.base import CRMTestCase


class CompanyFormTests(CRMTestCase):
    def test_最低限の入力で通る(self):
        form = CompanyForm(data={"name": "新規会社", "industry": "it", "rank": "b"})
        self.assertTrue(form.is_valid(), form.errors)

    def test_会社名は必須(self):
        form = CompanyForm(data={"industry": "it", "rank": "b"})
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_会社名の重複を弾く(self):
        form = CompanyForm(data={"name": "テスト商事", "industry": "it", "rank": "b"})
        self.assertFalse(form.is_valid())
        self.assertIn("すでに登録されています", form.errors["name"][0])

    def test_重複判定は大文字小文字を区別しない(self):
        Company.objects.create(name="Acme Inc")
        form = CompanyForm(data={"name": "ACME INC", "industry": "it", "rank": "b"})
        self.assertFalse(form.is_valid())

    def test_自分自身は重複判定から除外する(self):
        """編集時に名前を変えずに保存できないと困る。"""
        form = CompanyForm(
            data={"name": "テスト商事", "industry": "it", "rank": "b"}, instance=self.company
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_前後の空白は落とす(self):
        form = CompanyForm(data={"name": "  空白会社  ", "industry": "it", "rank": "b"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["name"], "空白会社")

    def test_必須項目にはCSSクラスと属性が付く(self):
        """BootstrapishMixin が widget に手を入れていることの確認。"""
        form = CompanyForm()
        self.assertEqual(form.fields["name"].widget.attrs["class"], "input")
        self.assertEqual(form.fields["name"].widget.attrs["required"], "required")

    def test_外部キーの空選択肢が日本語になっている(self):
        form = CompanyForm()
        self.assertEqual(form.fields["owner"].empty_label, "選択してください")


class ContactFormTests(CRMTestCase):
    def base_data(self, **overrides):
        data = {"company": self.company.pk, "last_name": "鈴木", "first_name": "花子"}
        return data | overrides

    def test_通常の入力で通る(self):
        self.assertTrue(ContactForm(data=self.base_data()).is_valid())

    def test_メールは省略できる(self):
        form = ContactForm(data=self.base_data(email=""))
        self.assertTrue(form.is_valid(), form.errors)

    def test_メールの重複を弾く(self):
        form = ContactForm(data=self.base_data(email="yamada@example.com"))
        self.assertFalse(form.is_valid())
        self.assertIn("登録済み", form.errors["email"][0])

    def test_メールは小文字に正規化される(self):
        form = ContactForm(data=self.base_data(email="Suzuki@EXAMPLE.com"))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["email"], "suzuki@example.com")

    def test_タグのウィジェットにはinputクラスを当てない(self):
        """CheckboxSelectMultiple に input クラスが付くとレイアウトが崩れる。"""
        form = ContactForm()
        self.assertNotIn("class", form.fields["tags"].widget.attrs)

    def test_無効な取引先は選べない(self):
        inactive = Company.objects.create(name="休止中", is_active=False)
        form = ContactForm(data=self.base_data(company=inactive.pk))
        self.assertFalse(form.is_valid())


class DealFormTests(CRMTestCase):
    def base_data(self, **overrides):
        data = {
            "title": "新案件",
            "company": self.company.pk,
            "amount": "1000000",
            "stage": "proposal",
            "probability": "50",
        }
        return data | overrides

    def test_通常の入力で通る(self):
        self.assertTrue(DealForm(data=self.base_data()).is_valid())

    def test_取引先に所属しない担当者は弾く(self):
        """連動プルダウンを画面で細工されても、サーバ側で止まること。

        止めているのは2層ある。
          1層目: ModelChoiceField の queryset（取引先で絞ってある）
          2層目: clean() の突き合わせ
        実際に効くのは1層目で、エラーメッセージも Django 標準のものになる。
        """
        other_company = Company.objects.create(name="よその会社")
        other_contact = Contact.objects.create(company=other_company, last_name="他人")
        form = DealForm(data=self.base_data(contact=other_contact.pk))
        self.assertFalse(form.is_valid())
        self.assertIn("contact", form.errors)

    def test_querysetを広げてもcleanが取引先違いを弾く(self):
        """2層目が実際に機能することを、1層目を無効化して確かめる。

        「queryset での絞り込みを外す変更」を将来入れても、
        取引先違いが素通りしないことをこのテストが保証する。
        """
        other_company = Company.objects.create(name="よその会社")
        other_contact = Contact.objects.create(company=other_company, last_name="他人")

        form = DealForm(data=self.base_data(contact=other_contact.pk))
        form.fields["contact"].queryset = Contact.objects.all()   # 1層目を無効化
        self.assertFalse(form.is_valid())
        self.assertIn("所属している必要があります", form.errors["contact"][0])

    def test_進行中の商談に過去日は設定できない(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        form = DealForm(data=self.base_data(expected_close_date=yesterday.isoformat()))
        self.assertFalse(form.is_valid())
        self.assertIn("過去日", form.errors["expected_close_date"][0])

    def test_受注済みなら過去日でもよい(self):
        """実績として過去日を入れるのは正当。"""
        yesterday = timezone.localdate() - timedelta(days=1)
        form = DealForm(
            data=self.base_data(stage="won", probability="100",
                                expected_close_date=yesterday.isoformat())
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_取引先未選択なら担当者の選択肢は空(self):
        form = DealForm()
        self.assertEqual(form.fields["contact"].queryset.count(), 0)

    def test_取引先が決まると担当者が絞り込まれる(self):
        form = DealForm(initial={"company": self.company.pk})
        self.assertQuerySetEqual(
            form.fields["contact"].queryset, [self.contact], ordered=False
        )


class InlineFormFactoryTests(CRMTestCase):
    """インライン編集用に1フィールドだけのフォームを動的生成する仕組み。"""

    def test_指定した1項目だけのフォームができる(self):
        form = build_inline_form(self.company, "phone")
        self.assertEqual(list(form.fields), ["phone"])

    def test_保存できる(self):
        form = build_inline_form(self.company, "phone", data={"phone": "03-1111-2222"})
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.company.refresh_from_db()
        self.assertEqual(self.company.phone, "03-1111-2222")

    def test_ホワイトリスト外の項目は作れない(self):
        """URL に項目名が入る設計なので、ここが最後の砦になる。"""
        with self.assertRaises(ValueError):
            build_inline_form(self.company, "is_active")
        with self.assertRaises(ValueError):
            build_inline_form(self.company, "owner")

    def test_モデルごとに許可項目が分かれている(self):
        build_inline_form(self.deal, "amount")           # Deal では許可
        with self.assertRaises(ValueError):
            build_inline_form(self.deal, "phone")        # Deal には無い項目

    def test_オートフォーカスが付く(self):
        form = build_inline_form(self.company, "phone")
        self.assertEqual(form.fields["phone"].widget.attrs["autofocus"], "autofocus")

    def test_モデルのバリデーションも効く(self):
        form = build_inline_form(self.deal, "probability", data={"probability": "150"})
        self.assertFalse(form.is_valid())
