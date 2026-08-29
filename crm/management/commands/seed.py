"""デモ用の初期データを投入する。

    uv run python manage.py seed --reset
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from crm.models import Activity, Company, Contact, Deal, Tag, Task

User = get_user_model()

USERS = [
    ("tanaka", "田中 一郎", "sales", "#6366f1"),
    ("suzuki", "鈴木 美咲", "sales", "#ec4899"),
    ("sato", "佐藤 健太", "marketing", "#14b8a6"),
    ("yamada", "山田 由紀", "support", "#f59e0b"),
]

COMPANIES = [
    ("株式会社アルファテック", "アルファテック", "it", "a", 480, "東京都港区芝浦3-1-1"),
    ("ベータ工業株式会社", "ベータコウギョウ", "manufacturing", "b", 1250, "愛知県名古屋市中村区名駅4-2-2"),
    ("ガンマ商事株式会社", "ガンマショウジ", "retail", "b", 320, "大阪府大阪市北区梅田1-3-3"),
    ("デルタ銀行", "デルタギンコウ", "finance", "a", 8600, "東京都千代田区大手町1-1-1"),
    ("イプシロン医療センター", "イプシロンイリョウ", "medical", "b", 740, "神奈川県横浜市西区北幸2-4-4"),
    ("ゼータ建設株式会社", "ゼータケンセツ", "construction", "c", 210, "福岡県福岡市博多区博多駅前3-5-5"),
    ("イータソフトウェア株式会社", "イータソフトウェア", "it", "a", 95, "東京都渋谷区道玄坂1-6-6"),
    ("シータ物流株式会社", "シータブツリュウ", "retail", "b", 1580, "千葉県千葉市美浜区中瀬1-7-7"),
    ("イオタ精密工業", "イオタセイミツ", "manufacturing", "b", 430, "長野県諏訪市大和1-8-8"),
    ("カッパ製薬株式会社", "カッパセイヤク", "medical", "a", 2200, "大阪府吹田市江坂町1-9-9"),
    ("ラムダ不動産", "ラムダフドウサン", "construction", "c", 60, "北海道札幌市中央区大通西5-10"),
    ("ミューリテール株式会社", "ミューリテール", "retail", "c", 890, "宮城県仙台市青葉区一番町2-11-11"),
    ("ニューエナジー株式会社", "ニューエナジー", "other", "b", 340, "静岡県静岡市葵区呉服町1-12-12"),
    ("クサイ食品工業", "クサイショクヒン", "manufacturing", "b", 760, "兵庫県神戸市中央区磯上通4-13-13"),
    ("オミクロン保険", "オミクロンホケン", "finance", "a", 4100, "東京都新宿区西新宿2-14-14"),
    ("パイ電子工業株式会社", "パイデンシ", "manufacturing", "b", 1120, "京都府京都市下京区烏丸通1-15-15"),
    ("ロー・コンサルティング", "ローコンサルティング", "other", "c", 45, "東京都中央区銀座5-16-16"),
    ("シグマ通信株式会社", "シグマツウシン", "it", "a", 3300, "東京都品川区大崎2-17-17"),
]

LAST_NAMES = ["高橋", "伊藤", "渡辺", "中村", "小林", "加藤", "吉田", "山本", "松本", "井上", "木村", "林"]
FIRST_NAMES = ["翔太", "彩", "大輔", "遥", "健一", "美穂", "拓也", "麻衣", "隆", "さやか"]
TITLES = ["代表取締役", "営業部長", "情報システム部 課長", "購買部 主任", "経営企画室", "総務部長", "開発部 リーダー"]

DEAL_TITLES = [
    "基幹システム刷新", "営業支援ツール導入", "セキュリティ監査サービス",
    "クラウド移行支援", "在庫管理システム構築", "モバイルアプリ開発",
    "データ分析基盤構築", "ネットワーク更改", "BPO サービス導入", "年次保守契約更新",
]

ACTIVITY_TEMPLATES = [
    ("call", "電話でヒアリング", "現行システムの課題感を確認。予算期は下期とのこと。"),
    ("email", "提案書を送付", "見積書とあわせてPDFで送付済み。来週フォロー予定。"),
    ("meeting", "定例ミーティング", "先方の情シス部長と要件をすり合わせ。導入時期は次年度4月希望。"),
    ("note", "社内メモ", "競合が価格で攻めている。保守の手厚さで差別化する方針。"),
    ("meeting", "デモ実施", "実機デモを実施。UIの分かりやすさに好感触。"),
    ("call", "フォローコール", "稟議の進捗を確認。役員会は月末。"),
]

TAGS = [
    ("決裁者", "#dc2626"), ("キーマン", "#7c3aed"), ("技術担当", "#0284c7"),
    ("紹介経由", "#059669"), ("展示会", "#d97706"),
]


class Command(BaseCommand):
    help = "デモ用の CRM データを投入します"

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="既存の CRM データを削除してから投入する")

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(20250829)

        if options["reset"]:
            Activity.objects.all().delete()
            Task.objects.all().delete()
            Deal.objects.all().delete()
            Contact.objects.all().delete()
            Company.objects.all().delete()
            Tag.objects.all().delete()
            self.stdout.write(self.style.WARNING("既存データを削除しました"))

        # --- ユーザー -------------------------------------------------------
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser(
                "admin", "admin@example.com", "admin1234",
                display_name="管理者", department="admin",
            )
            self.stdout.write("スーパーユーザー admin / admin1234 を作成しました")

        users = []
        for username, display, department, color in USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "display_name": display,
                    "department": department,
                    "avatar_color": color,
                    "email": f"{username}@example.com",
                    "is_staff": True,
                },
            )
            if created:
                user.set_password("demo1234")
                user.save()
            users.append(user)

        # --- タグ -----------------------------------------------------------
        tags = [Tag.objects.get_or_create(name=name, defaults={"color": color})[0] for name, color in TAGS]

        # --- 取引先・担当者・商談 --------------------------------------------
        today = timezone.localdate()
        now = timezone.localtime()
        companies = []
        for name, kana, industry, rank, employees, address in COMPANIES:
            company, _ = Company.objects.get_or_create(
                name=name,
                defaults={
                    "name_kana": kana,
                    "industry": industry,
                    "rank": rank,
                    "employee_count": employees,
                    "address": address,
                    "phone": f"0{random.randint(3, 9)}-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}",
                    "website": f"https://www.{kana[:6].lower()}.example.co.jp",
                    "owner": random.choice(users),
                    "note": "初回接触は展示会。導入検討中。" if rank == "a" else "",
                },
            )
            companies.append(company)

            for index in range(random.randint(1, 4)):
                contact, created = Contact.objects.get_or_create(
                    company=company,
                    last_name=random.choice(LAST_NAMES),
                    first_name=random.choice(FIRST_NAMES),
                    defaults={
                        "title": random.choice(TITLES),
                        "phone": f"090-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}",
                        "is_primary": index == 0,
                    },
                )
                if created:
                    contact.email = f"{contact.last_name.lower()}{contact.pk}@{kana[:6].lower()}.example.co.jp"
                    contact.save(update_fields=["email"])
                    contact.tags.set(random.sample(tags, random.randint(0, 2)))

        position = 0
        for company in companies:
            for _ in range(random.randint(0, 3)):
                stage = random.choice(
                    ["lead", "qualified", "proposal", "proposal", "negotiation", "won", "lost"]
                )
                deal = Deal.objects.create(
                    title=f"{company.name[:6]} {random.choice(DEAL_TITLES)}",
                    company=company,
                    contact=company.contacts.order_by("?").first(),
                    amount=Decimal(random.randint(3, 120) * 100000),
                    stage=stage,
                    probability=Deal.DEFAULT_PROBABILITY[stage],
                    expected_close_date=today + timedelta(days=random.randint(-25, 120)),
                    owner=company.owner or random.choice(users),
                    position=position,
                    description="既存システムの老朽化に伴うリプレース案件。",
                )
                position += 1

                for _ in range(random.randint(1, 4)):
                    kind, subject, body = random.choice(ACTIVITY_TEMPLATES)
                    Activity.objects.create(
                        kind=kind,
                        subject=f"{subject}（{deal.title[:14]}）",
                        body=body,
                        occurred_at=now - timedelta(days=random.randint(0, 60), hours=random.randint(0, 20)),
                        company=company,
                        contact=deal.contact,
                        deal=deal,
                        created_by=deal.owner,
                    )

        # --- タスク ---------------------------------------------------------
        deals = list(Deal.objects.open())
        task_titles = [
            "見積書を作成する", "提案書をレビューに回す", "先方に電話でフォロー",
            "デモ環境を用意する", "契約書のドラフトを法務へ", "議事録を共有する",
        ]
        for user in users:
            for _ in range(random.randint(3, 6)):
                Task.objects.create(
                    title=random.choice(task_titles),
                    due_date=today + timedelta(days=random.randint(-6, 20)),
                    priority=random.choice([1, 2, 2, 3]),
                    assignee=user,
                    deal=random.choice(deals) if deals else None,
                    is_done=random.random() < 0.25,
                )

        self.stdout.write(self.style.SUCCESS(
            f"投入完了: 取引先 {Company.objects.count()} / 担当者 {Contact.objects.count()} / "
            f"商談 {Deal.objects.count()} / 活動 {Activity.objects.count()} / タスク {Task.objects.count()}"
        ))
        self.stdout.write("ログイン: tanaka / demo1234  （管理者: admin / admin1234）")
