from django.conf import settings

from .models import Deal, Task


def asset_version(request):
    """開発中に CSS/JS がブラウザにキャッシュされ続けるのを防ぐ。

    DEBUG のときだけファイルの更新時刻をクエリに付ける。
    本番では ManifestStaticFilesStorage がハッシュを付けるので不要。
    """
    if not settings.DEBUG:
        return {"asset_v": ""}
    newest = 0.0
    for directory in settings.STATICFILES_DIRS:
        for path in directory.rglob("*"):
            if path.suffix in {".css", ".js"} and path.is_file():
                newest = max(newest, path.stat().st_mtime)
    return {"asset_v": f"?v={int(newest)}"}


def sidebar_badges(request):
    """サイドバーのバッジ用。未ログイン時は問い合わせないこと。"""
    if not request.user.is_authenticated:
        return {}
    return {
        "badge_open_deals": Deal.objects.open().count(),
        "badge_my_tasks": Task.objects.needs_attention(request.user).count(),
    }
