"""テンプレートから使う小さなヘルパー群。

インライン編集（click-to-edit）では「フィールド名を変数で受け取って
その値やラベルを出す」必要があるが、Django テンプレートは
``{{ obj.field_name }}`` のような動的アクセスができない。そこを埋める。
"""

from django import template
from django.utils.formats import date_format, number_format
from django.utils.html import format_html

register = template.Library()


@register.simple_tag
def model_value(obj, field_name):
    """`obj` の `field_name` を人間向けの文字列にして返す。"""
    field = obj._meta.get_field(field_name)
    if field.choices:
        return getattr(obj, f"get_{field_name}_display")()
    value = getattr(obj, field_name)
    if value in (None, ""):
        return ""
    if field.get_internal_type() in {"DecimalField", "IntegerField", "PositiveIntegerField"}:
        return number_format(value, force_grouping=True)
    if field.get_internal_type() == "DateField":
        return date_format(value, "Y年n月j日")
    return value


@register.simple_tag
def model_label(obj, field_name):
    return obj._meta.get_field(field_name).verbose_name


@register.simple_tag(takes_context=True)
def sort_indicator(context, key):
    """並び替え中の列に ▲▼ を出す。"""
    if context.get("sort_key") != key:
        return ""
    return format_html('<span class="sort-mark">{}</span>', "▼" if context.get("sort_desc") else "▲")


@register.simple_tag(takes_context=True)
def next_dir(context, key):
    """同じ列をもう一度クリックしたときの並び順を返す。"""
    if context.get("sort_key") == key and not context.get("sort_desc"):
        return "desc"
    return "asc"


@register.filter
def yen(value):
    """1234567 -> ¥1,234,567"""
    if value in (None, ""):
        return "—"
    return f"¥{number_format(int(value), force_grouping=True)}"


@register.filter
def initials(user):
    return getattr(user, "initials", str(user)[:2] if user else "?")
