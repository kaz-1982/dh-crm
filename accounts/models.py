from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """社内ユーザー。将来の拡張に備えて最初からカスタムユーザーにしておく。

    Django では後からユーザーモデルを差し替えるのが非常に大変なので、
    プロジェクト開始時にこれをやっておくのが定石。
    """

    class Department(models.TextChoices):
        SALES = "sales", "営業部"
        MARKETING = "marketing", "マーケティング部"
        SUPPORT = "support", "カスタマーサポート部"
        ADMIN = "admin", "管理部"

    display_name = models.CharField("表示名", max_length=50, blank=True)
    department = models.CharField(
        "部署", max_length=20, choices=Department, blank=True
    )
    phone = models.CharField("内線", max_length=20, blank=True)
    avatar_color = models.CharField("アバター色", max_length=7, default="#6366f1")

    class Meta:
        verbose_name = "ユーザー"
        verbose_name_plural = "ユーザー"

    def __str__(self):
        return self.display_name or self.get_full_name() or self.username

    @property
    def initials(self) -> str:
        source = self.display_name or self.get_full_name() or self.username
        return source[:2]
