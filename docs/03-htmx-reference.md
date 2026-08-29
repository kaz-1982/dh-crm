# 03. htmx 早見表

htmx 2.0.10 時点の一覧です。**太字**はこのアプリで実際に使っているもの。

---

## 1. 基本の4点セット

htmx で書くことの9割はこの4つの組み合わせです。

```html
<button hx-get="/companies/"    <!-- ① どこへ（メソッド + URL） -->
        hx-trigger="click"       <!-- ② いつ -->
        hx-target="#results"     <!-- ③ どこに -->
        hx-swap="outerHTML">     <!-- ④ どう入れるか -->
  読み込む
</button>
```

省略時のデフォルト:

| 属性 | 既定値 |
|---|---|
| `hx-trigger` | `<form>` は `submit`、`<input>/<select>/<textarea>` は `change`、それ以外は `click` |
| `hx-target` | その要素自身 |
| `hx-swap` | `innerHTML` |

---

## 2. リクエストを出す属性

| 属性 | 説明 |
|---|---|
| **`hx-get`** | GET |
| **`hx-post`** | POST |
| **`hx-delete`** | DELETE |
| `hx-put` / `hx-patch` | PUT / PATCH |
| **`hx-boost`** | 通常の `<a>` / `<form>` を ajax 化する。`body` に書けば全体に効く |

> `hx-boost` を使うと、リンク遷移が「`<body>` の中身だけ差し替え」になります。
> CSS や JS の再読み込みが起きないぶん、体感がかなり速くなります。
> 除外したいリンクには `hx-boost="false"`（CSV ダウンロードや `mailto:` など）。

---

## 3. `hx-trigger`（いつ）

### イベント名

DOM の任意のイベント名が書けます（`click` `change` `keyup` `submit` `blur` …）。
加えて htmx 独自のものが3つ:

| 疑似イベント | 意味 | このアプリでの使い所 |
|---|---|---|
| **`load`** | 要素が読み込まれた直後に1回 | ダッシュボードの遅延ロード |
| **`revealed`** | スクロールして画面に入った瞬間 | 活動履歴の無限スクロール |
| `intersect` | IntersectionObserver 版（`root:` `threshold:` 指定可） | — |
| **`every 30s`** | 定期実行（ポーリング） | KPI カード |

### 修飾子

| 修飾子 | 意味 | 例 |
|---|---|---|
| **`changed`** | 値が実際に変わったときだけ | 検索窓で無駄な再送を防ぐ |
| **`delay:<時間>`** | その時間、追加入力がなければ発火（デバウンス） | `delay:350ms` |
| `throttle:<時間>` | その時間に最大1回だけ（スロットル） | 連打対策 |
| **`from:<セレクタ>`** | 別の要素のイベントを拾う | `from:body` でカスタムイベント受信 |
| `once` | 1回だけ |  |
| `target:<セレクタ>` | イベントの発生元を絞る（イベント委譲） |  |
| `consume` | 親に伝播させない |  |
| `queue:first\|last\|all\|none` | 処理中に来たリクエストの扱い |  |

複数指定はカンマ区切り:

```html
<form hx-trigger="change, keyup changed delay:350ms, submit">
```

> **なぜフォームに1つ書けば済むのか**
> `change` と `keyup` は子要素からフォームまでバブリングします。
> 各 `<input>` に書く必要はありません。

---

## 4. `hx-target`（どこに）

| 値 | 意味 |
|---|---|
| `#results` | CSS セレクタ |
| **`this`** | 自分自身 |
| **`closest <sel>`** | 自分から見て最も近い祖先 |
| `find <sel>` | 自分の子孫から最初の1つ |
| `next <sel>` / `previous <sel>` | 次／前の兄弟 |

---

## 5. `hx-swap`（どう入れるか）

| 値 | 意味 |
|---|---|
| `innerHTML` | 中身を置き換え（**既定**） |
| **`outerHTML`** | 要素ごと置き換え |
| `textContent` | テキストとして挿入（HTML として解釈しない） |
| **`beforeend`** | 子の最後に追加（無限スクロール） |
| `afterbegin` | 子の最初に追加 |
| `beforebegin` / `afterend` | 自分の前／後に挿入 |
| `delete` | 要素を消す |
| `none` | 何もしない（`HX-Trigger` だけ受け取りたいとき） |

### swap の修飾子

| 修飾子 | 意味 | 例 |
|---|---|---|
| **`swap:<時間>`** | 消えるまでの待ち時間。CSS トランジションと合わせる | `outerHTML swap:300ms` |
| `settle:<時間>` | 挿入後、クラスが落ち着くまでの時間 |  |
| `transition:true` | View Transitions API を使う |  |
| `ignoreTitle:true` | レスポンス内の `<title>` を無視 |  |
| `scroll:top` / `show:top` | swap 後のスクロール位置 |  |

```html
<!-- 行を消してから 300ms かけてフェードアウトさせる -->
<button hx-delete="/companies/1/delete/"
        hx-target="#company-row-1"
        hx-swap="outerHTML swap:300ms">🗑</button>
```

---

## 6. 送るデータを制御する

| 属性 | 説明 |
|---|---|
| **`hx-vals`** | JSON で値を追加 `hx-vals='{"action":"delete"}'` |
| **`hx-include`** | 別の要素の値も一緒に送る `hx-include="#sort-state"` |
| `hx-params` | 送るパラメータを絞る（`*` `none` `not a,b` `a,b`） |
| **`hx-headers`** | リクエストヘッダを足す（CSRF トークンはこれ） |
| `hx-encoding` | `multipart/form-data`（ファイルアップロード） |

`<form>` に `hx-get` を書くと、**中の入力値が自動でクエリ文字列になります**。
`hx-vals` を手で書く必要はありません。

---

## 7. UI 補助

| 属性 | 説明 |
|---|---|
| **`hx-indicator`** | 通信中だけ表示する要素を指定（`.htmx-indicator` クラスと組み合わせ） |
| **`hx-disabled-elt`** | 通信中に `disabled` にする要素。二重送信対策 |
| **`hx-confirm`** | 送信前に `confirm()` を出す |
| `hx-prompt` | 送信前に `prompt()` を出し、`HX-Prompt` ヘッダで送る |
| **`hx-push-url`** | ブラウザの URL を書き換える（戻る・リロードが効く） |
| `hx-replace-url` | 履歴を増やさずに URL を書き換える |
| `hx-preserve` | swap されても消さない（動画プレイヤーなど） |
| `hx-sync` | 同じ要素からの同時リクエストの調停 |
| `hx-select` | レスポンスの一部だけを取り出して使う |
| **`hx-swap-oob`** | レスポンス側に書く。id を頼りに別の場所も同時更新 |
| `hx-select-oob` | レスポンスの一部を別の場所へ |
| **`hx-ext`** | 拡張機能の有効化 |
| **`hx-disinherit`** | 指定した属性を子に継承させない |
| `hx-inherit` | 継承する属性を明示（`htmx.config.disableInheritance` 使用時） |
| `hx-disable` | その要素以下で htmx を無効化（ユーザー投稿 HTML を出すときの安全弁） |
| `hx-on:イベント` | インラインのイベントハンドラ |

### 属性は子に継承される

これは強力ですが、事故のもとでもあります。

```html
<!-- body に書けば全リクエストに CSRF が付く（定石） -->
<body hx-headers='{"X-CSRFToken": "..."}' hx-boost="true">
```

```html
<!-- ⚠️ フォームに書いた hx-disabled-elt は、
     中の「自分でリクエストを出す input」にも継承されてしまう -->
<form hx-post="..." hx-disabled-elt="find button[type=submit]"
      hx-disinherit="hx-disabled-elt">
```

詳細は [06. ハマりどころ](06-pitfalls.md)。

---

## 8. レスポンスヘッダ（サーバ → ブラウザの指示）

| ヘッダ | 効果 | django-htmx |
|---|---|---|
| **`HX-Trigger`** | クライアント側でイベントを発火 | `trigger_client_event(res, "toast", {...})` |
| `HX-Trigger-After-Swap` | swap 後に発火 | `trigger_client_event(..., after="swap")` |
| `HX-Trigger-After-Settle` | settle 後に発火 | `after="settle"` |
| **`HX-Redirect`** | クライアント側でページ遷移 | `HttpResponseClientRedirect("/companies/")` |
| `HX-Refresh` | ページを丸ごとリロード | `HttpResponseClientRefresh()` |
| `HX-Location` | 遷移をクライアント側 ajax で行う | `HttpResponseLocation("/x/")` |
| `HX-Retarget` | 差し替え先を上書き | `retarget(res, "#error")` |
| `HX-Reswap` | swap 方法を上書き | `reswap(res, "outerHTML")` |
| `HX-Reselect` | レスポンスの一部を選択 | `reselect(res, "#part")` |
| `HX-Push-Url` / `HX-Replace-Url` | URL を書き換え | `push_url(res, "/x/")` |

ポーリングを止めたいときは HTTP **286** を返します。

```python
from django_htmx.http import HttpResponseStopPolling
return HttpResponseStopPolling()
```

### `HX-Trigger` の中身

```python
trigger_client_event(response, "toast", {"message": "保存しました", "level": "success"})
# → HX-Trigger: {"toast": {"message": "保存しました", "level": "success"}}
```

ブラウザ側では普通の `CustomEvent` として届きます。

```js
document.body.addEventListener("toast", (event) => {
  showToast(event.detail.message, event.detail.level);
});
```

---

## 9. リクエストヘッダ（ブラウザ → サーバ）

django-htmx がプロパティにしてくれます。

| プロパティ | ヘッダ | 内容 |
|---|---|---|
| **`request.htmx`** | `HX-Request` | htmx からのリクエストか（真偽値として使える） |
| `request.htmx.boosted` | `HX-Boosted` | `hx-boost` 経由か |
| **`request.htmx.target`** | `HX-Target` | 差し替え先要素の id |
| `request.htmx.trigger` | `HX-Trigger` | 発火元要素の id |
| `request.htmx.trigger_name` | `HX-Trigger-Name` | 発火元要素の name |
| `request.htmx.current_url` | `HX-Current-URL` | 現在の URL |
| `request.htmx.prompt` | `HX-Prompt` | `hx-prompt` の入力値 |

`HX-Target` は「どこから呼ばれたか」で挙動を変えるのに使えます。

```python
# 一覧の行から消されたのか、詳細画面から消されたのかで返すものを変える
if request.htmx and request.headers.get("HX-Target", "").startswith("company-row-"):
    return HttpResponse("")                       # 行を消すだけ
return HttpResponseClientRedirect("/companies/")  # 一覧へ飛ばす
```

---

## 10. JavaScript イベント（デバッグに効く）

| イベント | タイミング |
|---|---|
| `htmx:configRequest` | リクエスト組み立て時（パラメータを足せる） |
| `htmx:beforeRequest` | 送信直前（`preventDefault()` で中止できる） |
| `htmx:beforeSwap` | 差し替え直前（`detail.shouldSwap` を書き換えられる） |
| **`htmx:afterSwap`** | 差し替え直後 |
| **`htmx:afterSettle`** | 落ち着いた後（ライブラリの再初期化はここ） |
| **`htmx:responseError`** | 4xx / 5xx |
| **`htmx:sendError`** | ネットワークエラー |
| `htmx:load` | 新しく挿入された要素ごとに発火 |

**必ず書くべきなのはエラー処理です。** htmx はデフォルトでは
4xx/5xx のときに画面へ何も出しません（黙って失敗します）。

```js
document.body.addEventListener("htmx:responseError", (event) => {
  const status = event.detail.xhr.status;
  if (status === 422) return;                    // バリデーションは別処理
  showToast(`エラーが発生しました (HTTP ${status})`, "error");
});
```

---

## 11. CSS クラス

htmx が自動で付け外しするクラスです。

| クラス | 付く場所 | 意味 |
|---|---|---|
| `htmx-request` | リクエスト中の要素（と `hx-indicator` の対象） | 通信中 |
| `htmx-indicator` | 自分で付ける | `htmx-request` のときだけ表示させる相方 |
| `htmx-added` | 挿入直後の要素（settle まで） | 入場アニメーション用 |
| `htmx-swapping` | 消えていく要素（`swap:` 指定時） | 退場アニメーション用 |
| `htmx-settling` | settle 中 |  |

```css
.htmx-indicator { opacity: 0; transition: opacity .15s; }
.htmx-request .htmx-indicator,
.htmx-request.htmx-indicator { opacity: 1; }
```

---

## 12. `htmx.config`（挙動を宣言的に変える）

`htmx.config` を書き換えると、htmx 全体の既定動作を変えられます。
とくに `responseHandling` は知っておくと選択肢が広がります。

```js
// 既定値。先頭から順に評価され、最初にマッチしたものが使われる
htmx.config.responseHandling = [
  { code: "204",    swap: false },              // 本文なし → 差し替えない
  { code: "[23]..", swap: true  },              // 2xx / 3xx → 差し替える
  { code: "[45]..", swap: false, error: true }, // 4xx / 5xx → 差し替えない
];
```

**htmx が 4xx で何もしないのはこの設定のため**です。
422 を差し替えたいなら、拡張機能を入れずにここへ1行足すだけで済みます。

その他よく触る設定:

| キー | 既定 | 意味 |
|---|---|---|
| `defaultSwapStyle` | `"innerHTML"` | `hx-swap` 省略時 |
| `defaultSwapDelay` | `0` | swap までの待ち |
| `defaultSettleDelay` | `20` | settle までの待ち |
| `selfRequestsOnly` | `true` | 同一オリジン以外へのリクエストを禁止（htmx 2 から既定で有効） |
| `disableInheritance` | `false` | `true` にすると属性の継承をやめる（`hx-inherit` で個別に許可） |
| `allowNestedOobSwaps` | `true` | 入れ子の OOB を許可 |
| `globalViewTransitions` | `false` | View Transitions API を全体で使う |
| `includeIndicatorStyles` | `true` | `.htmx-indicator` の既定 CSS を注入 |

`<head>` の meta タグでも指定できます。

```html
<meta name="htmx-config" content='{"defaultSwapStyle":"outerHTML"}'>
```

---

## 13. JS から htmx を呼ぶ

属性で書けない場面（ドラッグ&ドロップなど）では JS から直接呼びます。

```js
htmx.ajax("POST", `/deals/${id}/move/`, {
  target: "#board",
  swap: "outerHTML",
  values: { stage: "won", order: [1, 2, 3] },
});
```

| API | 用途 |
|---|---|
| `htmx.ajax(verb, url, opts)` | リクエストを投げる |
| `htmx.trigger(elt, "イベント名")` | イベントを発火 |
| `htmx.process(elt)` | JS で挿入した DOM を htmx に認識させる |
| `htmx.logAll()` | 全イベントをコンソールに出す（デバッグ用） |
