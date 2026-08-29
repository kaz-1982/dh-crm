from django import forms
from django.utils import timezone

from .models import Activity, Company, Contact, Deal, Tag, Task

TEXT = {"class": "input"}
AREA = {"class": "input", "rows": 3}
SELECT = {"class": "input"}


class BootstrapishMixin:
    """全フォーム共通で widget に CSS クラスを当てるだけの薄いミックスイン。

    django-crispy-forms などを使わずに素で書くとこうなる、という例。
    """

    error_css_class = "has-error"
    required_css_class = "is-required"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "checkbox")
            else:
                widget.attrs.setdefault("class", "input")
            if field.required:
                widget.attrs.setdefault("required", "required")
            # 外部キーの空選択肢が英語のままなので日本語にしておく
            if isinstance(field, forms.ModelChoiceField) and field.empty_label is not None:
                field.empty_label = "選択してください"


class CompanyForm(BootstrapishMixin, forms.ModelForm):
    class Meta:
        model = Company
        fields = [
            "name", "name_kana", "industry", "rank", "employee_count",
            "website", "phone", "address", "owner", "note",
        ]
        widgets = {"note": forms.Textarea(attrs=AREA)}

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        qs = Company.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("同じ会社名がすでに登録されています。")
        return name


class ContactForm(BootstrapishMixin, forms.ModelForm):
    class Meta:
        model = Contact
        fields = [
            "company", "last_name", "first_name", "kana",
            "title", "email", "phone", "is_primary", "tags",
        ]
        widgets = {"tags": forms.CheckboxSelectMultiple()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["company"].queryset = Company.objects.filter(is_active=True)
        self.fields["tags"].queryset = Tag.objects.all()
        # CheckboxSelectMultiple には input クラスを当てたくないので上書き
        self.fields["tags"].widget.attrs.pop("class", None)
        self.fields["tags"].widget.attrs.pop("required", None)

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            return email
        qs = Contact.objects.filter(email__iexact=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("このメールアドレスは別の担当者に登録済みです。")
        return email


class DealForm(BootstrapishMixin, forms.ModelForm):
    class Meta:
        model = Deal
        fields = [
            "title", "company", "contact", "amount", "stage",
            "probability", "expected_close_date", "owner", "description",
        ]
        widgets = {
            "expected_close_date": forms.DateInput(attrs={"type": "date", "class": "input"}),
            "description": forms.Textarea(attrs=AREA),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["company"].queryset = Company.objects.filter(is_active=True)
        self.fields["contact"].required = False
        # 取引先が決まっている場合だけ、その会社の担当者に絞る（連動プルダウン）。
        company_id = self.data.get("company") or self.initial.get("company")
        if company_id:
            self.fields["contact"].queryset = Contact.objects.filter(company_id=company_id)
        elif self.instance.pk:
            self.fields["contact"].queryset = self.instance.company.contacts.all()
        else:
            self.fields["contact"].queryset = Contact.objects.none()

    def clean(self):
        cleaned = super().clean()
        company = cleaned.get("company")
        contact = cleaned.get("contact")
        if company and contact and contact.company_id != company.pk:
            self.add_error("contact", "担当者は選択した取引先に所属している必要があります。")
        date = cleaned.get("expected_close_date")
        stage = cleaned.get("stage")
        if date and stage in Deal.OPEN_STAGES and date < timezone.localdate():
            self.add_error("expected_close_date", "進行中の商談に過去日は設定できません。")
        return cleaned


class ActivityForm(BootstrapishMixin, forms.ModelForm):
    class Meta:
        model = Activity
        fields = ["kind", "subject", "body", "occurred_at", "company", "contact", "deal"]
        widgets = {
            "body": forms.Textarea(attrs=AREA),
            "occurred_at": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "input"}, format="%Y-%m-%dT%H:%M"
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["occurred_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"]
        for name in ("company", "contact", "deal"):
            self.fields[name].required = False


class TaskForm(BootstrapishMixin, forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title", "due_date", "priority", "assignee", "deal"]
        widgets = {"due_date": forms.DateInput(attrs={"type": "date", "class": "input"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["deal"].required = False


#: 「その場で編集（click to edit）」で使える項目の定義。
#: フィールド単体のミニフォームを動的に作ることで、URL 1 本で全項目に対応できる。
INLINE_EDITABLE_FIELDS = {
    "Company": ["name", "phone", "website", "address", "employee_count", "rank", "note"],
    "Deal": ["title", "amount", "probability", "expected_close_date"],
}


def build_inline_form(instance, field_name: str, data=None):
    """指定 1 フィールドだけを持つ ModelForm を動的生成する。"""
    model_name = instance.__class__.__name__
    allowed = INLINE_EDITABLE_FIELDS.get(model_name, [])
    if field_name not in allowed:
        raise ValueError(f"{model_name}.{field_name} はインライン編集できません")

    form_class = forms.modelform_factory(
        instance.__class__,
        form=_InlineBase,
        fields=[field_name],
    )
    return form_class(data=data, instance=instance)


class _InlineBase(BootstrapishMixin, forms.ModelForm):
    """modelform_factory に渡すためのベース。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["autofocus"] = "autofocus"
