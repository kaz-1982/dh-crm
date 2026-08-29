"""Playwright を Django のテストに載せるための土台。"""

import os
from pathlib import Path

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

    #: 各操作の待ち時間の上限（ミリ秒）。CI は遅いので環境変数で伸ばせるようにする。
    TIMEOUT = int(os.environ.get("E2E_TIMEOUT", 5_000))

    #: 失敗したテストのスクリーンショットとトレースの保存先。
    #: CI ではここを成果物としてアップロードする。
    ARTIFACT_DIR = Path(os.environ.get("E2E_ARTIFACTS", "test-results"))

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

        # 失敗したときだけ保存する。成功時は捨てるので、常時記録しても無駄にならない。
        self.context.tracing.start(screenshots=True, snapshots=True, sources=True)

        self.page = self.context.new_page()

        # このテストが失敗したかを後で判定するため、開始時点の件数を控えておく
        self._problems_before = self._problem_count()

        # コンソールエラーを集めておく。htmx は失敗を黙って握りつぶしがちなので、
        # 「エラーが出ていないこと」自体をテストの一部にする。
        self.console_errors = []
        self.page.on(
            "console",
            lambda msg: self.console_errors.append(msg.text) if msg.type == "error" else None,
        )
        self.page.on("pageerror", lambda err: self.console_errors.append(str(err)))

    def tearDown(self):
        if self._test_failed():
            self._save_artifacts()
        else:
            self.context.tracing.stop()
        self.context.close()
        super().tearDown()

    # --- 失敗時の証拠を残す ------------------------------------------------

    def _problem_count(self) -> int:
        result = self._outcome.result
        return len(result.failures) + len(result.errors)

    def _test_failed(self) -> bool:
        """このテストが失敗したか。

        `self._outcome.success` は使えない。unittest の testPartExecutor が
        tearDown の実行中だけ True に戻してしまうため、tearDown からは
        常に True に見える。一方 result への失敗の記録はテストメソッドが
        こけた時点で済んでいるので、件数の差分なら正しく判定できる。
        """
        return self._problem_count() > self._problems_before

    def _save_artifacts(self):
        """スクリーンショットと Playwright トレースを残す。

        トレースは `playwright show-trace <file>` で開くと、
        操作の各ステップの DOM とネットワークをそのまま辿れる。
        CI で落ちたときの原因究明はこれがあるかどうかで大きく変わる。
        """
        self.ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        name = f"{self.__class__.__name__}.{self._testMethodName}"
        try:
            self.page.screenshot(path=str(self.ARTIFACT_DIR / f"{name}.png"), full_page=True)
        except Exception:  # ページが閉じている等。証拠集めで落としたくない
            pass
        try:
            self.context.tracing.stop(path=str(self.ARTIFACT_DIR / f"{name}.zip"))
        except Exception:
            pass

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

    def wait_for_htmx_idle(self):
        """進行中の htmx リクエストが無くなるまで待つ。

        必要になる理由:
        SortableJS はドロップした瞬間に自分で DOM を動かす。つまり
        「カードが移動先の列にある」というアサーションは、サーバの応答を
        待たずに通ってしまう。その直後に次の操作を始めると、遅れて届いた
        レスポンスがボードを差し替えて操作対象が消え、たまに落ちる
        （＝ flaky なテストになる）。

        htmx はリクエスト中の要素に .htmx-request を付ける。
        htmx.ajax() の場合その要素は <body> なので、これで判定できる。
        """
        self.page.wait_for_function(
            "() => document.querySelectorAll('.htmx-request').length === 0"
        )

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
