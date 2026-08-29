from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q, Sum
from django.urls import reverse
from django.utils import timezone


class TimeStampedModel(models.Model):
    """作成/更新日時を持つ抽象基底クラス。全モデルで使い回す。"""

    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        abstract = True


class Tag(models.Model):
    name = models.CharField("タグ名", max_length=30, unique=True)
    color = models.CharField("色", max_length=7, default="#64748b")

    class Meta:
        verbose_name = "タグ"
        verbose_name_plural = "タグ"
        ordering = ["name"]

    def __str__(self):
        return self.name


class CompanyQuerySet(models.QuerySet):
    def search(self, keyword: str):
        """一覧のライブ検索用。空文字なら素通し。"""
        if not keyword:
            return self
        return self.filter(
            Q(name__icontains=keyword)
            | Q(name_kana__icontains=keyword)
            | Q(address__icontains=keyword)
        )

    def with_stats(self):
        """N+1 を避けるため、一覧で使う集計をまとめて取る。"""
        return self.annotate(
            contact_count=models.Count("contacts", distinct=True),
            open_deal_amount=Sum(
                "deals__amount",
                filter=Q(deals__stage__in=Deal.OPEN_STAGES),
                default=Decimal("0"),
            ),
        )


class Company(TimeStampedModel):
    """取引先企業。"""

    class Industry(models.TextChoices):
        IT = "it", "IT・ソフトウェア"
        MANUFACTURING = "manufacturing", "製造"
        RETAIL = "retail", "小売・流通"
        FINANCE = "finance", "金融"
        MEDICAL = "medical", "医療・ヘルスケア"
        CONSTRUCTION = "construction", "建設・不動産"
        OTHER = "other", "その他"

    class Rank(models.TextChoices):
        A = "a", "A（重要顧客）"
        B = "b", "B（通常）"
        C = "c", "C（見込み薄）"

    name = models.CharField("会社名", max_length=120, db_index=True)
    name_kana = models.CharField("会社名カナ", max_length=120, blank=True)
    industry = models.CharField("業種", max_length=20, choices=Industry, default=Industry.OTHER)
    rank = models.CharField("ランク", max_length=1, choices=Rank, default=Rank.B)
    employee_count = models.PositiveIntegerField("従業員数", null=True, blank=True)
    website = models.URLField("Web サイト", blank=True)
    phone = models.CharField("代表電話", max_length=20, blank=True)
    address = models.CharField("住所", max_length=200, blank=True)
    note = models.TextField("メモ", blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="担当者",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="companies",
    )
    is_active = models.BooleanField("有効", default=True)

    objects = CompanyQuerySet.as_manager()

    class Meta:
        verbose_name = "取引先"
        verbose_name_plural = "取引先"
        ordering = ["name_kana", "name"]
        constraints = [
            models.UniqueConstraint(
                models.functions.Lower("name"), name="company_name_unique_ci"
            )
        ]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("crm:company_detail", args=[self.pk])


class ContactQuerySet(models.QuerySet):
    def search(self, keyword: str):
        if not keyword:
            return self
        return self.filter(
            Q(last_name__icontains=keyword)
            | Q(first_name__icontains=keyword)
            | Q(kana__icontains=keyword)
            | Q(email__icontains=keyword)
            | Q(company__name__icontains=keyword)
        )


class Contact(TimeStampedModel):
    """取引先の担当者（人）。"""

    company = models.ForeignKey(
        Company, verbose_name="取引先", on_delete=models.CASCADE, related_name="contacts"
    )
    last_name = models.CharField("姓", max_length=40)
    first_name = models.CharField("名", max_length=40, blank=True)
    kana = models.CharField("フリガナ", max_length=80, blank=True)
    title = models.CharField("役職", max_length=60, blank=True)
    email = models.EmailField("メール", blank=True)
    phone = models.CharField("電話", max_length=20, blank=True)
    is_primary = models.BooleanField("主担当", default=False)
    tags = models.ManyToManyField(Tag, verbose_name="タグ", blank=True, related_name="contacts")

    objects = ContactQuerySet.as_manager()

    class Meta:
        verbose_name = "担当者"
        verbose_name_plural = "担当者"
        ordering = ["company__name", "-is_primary", "last_name"]
        indexes = [models.Index(fields=["email"])]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self) -> str:
        return f"{self.last_name} {self.first_name}".strip()

    def get_absolute_url(self):
        return reverse("crm:contact_detail", args=[self.pk])


class DealQuerySet(models.QuerySet):
    def open(self):
        return self.filter(stage__in=Deal.OPEN_STAGES)

    def search(self, keyword: str):
        if not keyword:
            return self
        return self.filter(Q(title__icontains=keyword) | Q(company__name__icontains=keyword))

    def total_amount(self) -> Decimal:
        return self.aggregate(total=Sum("amount", default=Decimal("0")))["total"]


class Deal(TimeStampedModel):
    """商談（案件）。カンバンボードの1枚のカードにあたる。"""

    class Stage(models.TextChoices):
        LEAD = "lead", "リード"
        QUALIFIED = "qualified", "案件化"
        PROPOSAL = "proposal", "提案中"
        NEGOTIATION = "negotiation", "交渉中"
        WON = "won", "受注"
        LOST = "lost", "失注"

    OPEN_STAGES = ["lead", "qualified", "proposal", "negotiation"]
    #: 各ステージのデフォルト確度（%）。ステージ変更時に自動で入る。
    DEFAULT_PROBABILITY = {
        "lead": 10,
        "qualified": 30,
        "proposal": 50,
        "negotiation": 75,
        "won": 100,
        "lost": 0,
    }

    title = models.CharField("案件名", max_length=120)
    company = models.ForeignKey(
        Company, verbose_name="取引先", on_delete=models.CASCADE, related_name="deals"
    )
    contact = models.ForeignKey(
        Contact,
        verbose_name="担当者",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deals",
    )
    amount = models.DecimalField("金額", max_digits=12, decimal_places=0, default=0)
    stage = models.CharField("ステージ", max_length=20, choices=Stage, default=Stage.LEAD, db_index=True)
    probability = models.PositiveSmallIntegerField("確度(%)", default=10)
    expected_close_date = models.DateField("受注予定日", null=True, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="営業担当",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deals",
    )
    #: カンバン内での並び順。ドラッグ&ドロップで更新する。
    position = models.PositiveIntegerField("表示順", default=0)
    description = models.TextField("概要", blank=True)

    objects = DealQuerySet.as_manager()

    class Meta:
        verbose_name = "商談"
        verbose_name_plural = "商談"
        ordering = ["position", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(probability__lte=100), name="deal_probability_lte_100"
            ),
            models.CheckConstraint(condition=Q(amount__gte=0), name="deal_amount_gte_0"),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("crm:deal_detail", args=[self.pk])

    @property
    def is_open(self) -> bool:
        return self.stage in self.OPEN_STAGES

    @property
    def is_overdue(self) -> bool:
        return bool(
            self.is_open
            and self.expected_close_date
            and self.expected_close_date < timezone.localdate()
        )

    @property
    def weighted_amount(self) -> Decimal:
        return self.amount * Decimal(self.probability) / Decimal(100)


class Activity(TimeStampedModel):
    """活動履歴。タイムラインに流れる1件。"""

    class Kind(models.TextChoices):
        CALL = "call", "電話"
        EMAIL = "email", "メール"
        MEETING = "meeting", "打合せ"
        NOTE = "note", "メモ"

    ICONS = {"call": "☎", "email": "✉", "meeting": "🤝", "note": "📝"}

    kind = models.CharField("種別", max_length=20, choices=Kind, default=Kind.NOTE)
    subject = models.CharField("件名", max_length=150)
    body = models.TextField("内容", blank=True)
    occurred_at = models.DateTimeField("実施日時", default=timezone.now)
    company = models.ForeignKey(
        Company,
        verbose_name="取引先",
        on_delete=models.CASCADE,
        related_name="activities",
        null=True,
        blank=True,
    )
    contact = models.ForeignKey(
        Contact,
        verbose_name="担当者",
        on_delete=models.SET_NULL,
        related_name="activities",
        null=True,
        blank=True,
    )
    deal = models.ForeignKey(
        Deal,
        verbose_name="商談",
        on_delete=models.CASCADE,
        related_name="activities",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="登録者",
        on_delete=models.SET_NULL,
        null=True,
        related_name="activities",
    )

    class Meta:
        verbose_name = "活動履歴"
        verbose_name_plural = "活動履歴"
        ordering = ["-occurred_at", "-id"]
        indexes = [models.Index(fields=["-occurred_at"])]

    def __str__(self):
        return self.subject

    @property
    def icon(self) -> str:
        return self.ICONS.get(self.kind, "•")


class TaskQuerySet(models.QuerySet):
    def needs_attention(self, user):
        """サイドバーのバッジに出す「今日までに片付けるべき自分のタスク」。

        バッジの定義を1か所にまとめておかないと、
        コンテキストプロセッサとトグル用ビューで数字がずれる。
        """
        return self.filter(
            assignee=user, is_done=False, due_date__lte=timezone.localdate()
        )


class Task(TimeStampedModel):
    """ToDo。チェックボックスの htmx トグルのお題に使う。"""

    class Priority(models.IntegerChoices):
        LOW = 1, "低"
        NORMAL = 2, "中"
        HIGH = 3, "高"

    title = models.CharField("タイトル", max_length=150)
    due_date = models.DateField("期限", null=True, blank=True)
    is_done = models.BooleanField("完了", default=False)
    priority = models.IntegerField("優先度", choices=Priority, default=Priority.NORMAL)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="担当",
        on_delete=models.CASCADE,
        related_name="tasks",
    )
    deal = models.ForeignKey(
        Deal,
        verbose_name="関連商談",
        on_delete=models.CASCADE,
        related_name="tasks",
        null=True,
        blank=True,
    )

    objects = TaskQuerySet.as_manager()

    class Meta:
        verbose_name = "タスク"
        verbose_name_plural = "タスク"
        ordering = ["is_done", "due_date", "-priority"]

    def __str__(self):
        return self.title

    @property
    def is_overdue(self) -> bool:
        return bool(not self.is_done and self.due_date and self.due_date < timezone.localdate())
