"""Playwright を Django のテストに載せるための土台。"""

import os

from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.contrib.sessions.backends.db import SessionStore
from django.test import tag

try:
    from playwright.sync_api import expect, sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:  # pragma: no cover
    PLAYWRIGHT_AVAILABLE = False
    expect = None


@tag("e2e")
class PlaywrightTestCase(StaticLiveServerTestCase):
    """ブラウザを1つ立ち上げ、クラス内のテストで使い回す。

    StaticLiveServerTestCase は実際に HTTP サーバを別スレッドで起動し、
    静的ファイル（htmx 本体を含む）も配信してくれる。
    """

    #: 各操作の待ち時間の上限（ミリ秒）。CI が遅いときはここを伸ばす。
    TIMEOUT = 5_000

    @classmethod
    def setUpClass(cls):
        # Playwright の同期 API は、Django が張るイベントループの中では動かない。
        # このフラグで「非同期文脈での同期呼び出し」を許可する。
        os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")
        super().setUpClass()
        cls._pw = sync_playwright().start()
        cls.browser = cls._pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._pw.stop()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 900})
        self.context.set_default_timeout(self.TIMEOUT)
        self.page = self.context.new_page()

        # コンソールエラーを集めておく。htmx は失敗を黙って握りつぶしがちなので、
        # 「エラーが出ていないこと」自体をテストの一部にする。
        self.console_errors = []
        self.page.on(
            "console",
            lambda msg: self.console_errors.append(msg.text) if msg.type == "error" else None,
        )
        self.page.on("pageerror", lambda err: self.console_errors.append(str(err)))

    def tearDown(self):
        self.context.close()
        super().tearDown()

    # --- ヘルパー ---------------------------------------------------------

    def login(self, user):
        """画面を経由せずにセッションを作る。

        ログイン画面の操作は1回テストすれば十分で、
        毎回フォームを埋めるのは無駄に遅い。
        """
        session = SessionStore()
        session[SESSION_KEY] = str(user.pk)
        session[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
        session[HASH_SESSION_KEY] = user.get_session_auth_hash()
        session.create()
        self.context.add_cookies([{
            "name": settings.SESSION_COOKIE_NAME,
            "value": session.session_key,
            "url": self.live_server_url,
        }])

    def goto(self, path="/"):
        self.page.goto(f"{self.live_server_url}{path}")
        # htmx が読み込まれ、DOM の処理が終わるまで待つ
        self.page.wait_for_function("() => window.htmx !== undefined")

    def assert_no_console_errors(self):
        """htmx のセレクタ間違いなどはコンソールにしか出ない。"""
        self.assertEqual(self.console_errors, [], "コンソールにエラーが出ています")

    def toast(self):
        """最新のトーストのロケータ。"""
        return self.page.locator("#toasts .toast").last

    def open_modal(self, button_name):
        """モーダルを開き、htmx が中身を処理し終えるまで待つ。

        ⚠️ ここが E2E のハマりどころ。
        「要素が DOM に現れた」と「htmx がその要素を処理し終えた」は別物で、
        htmx は innerHTML を差し替えてから中の要素に属性を紐づける。
        中の <select> の存在だけを待って操作すると、change イベントが
        まだリスナーの無い要素に飛び、静かに失われる。

        dialog が visible になるのは app.js の htmx:afterSwap ハンドラなので、
        これを待てば「htmx の処理が済んでいる」ことまで保証できる。
        """
        self.page.get_by_role("button", name=button_name).click()
        modal = self.page.locator("dialog#modal")
        expect(modal).to_be_visible()
        return modal

    def type_into(self, locator, text):
        """1文字ずつ打ち込む。

        Playwright の fill() は input イベントしか出さないため、
        `keyup changed delay:...` で待ち受けている htmx は反応しない。
        ライブ検索や入力中バリデーションのテストでは必ずこちらを使う。
        """
        locator.click()
        locator.fill("")
        locator.press_sequentially(text, delay=30)
