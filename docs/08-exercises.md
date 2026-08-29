# 08. 練習問題

読むだけでは身につかないので、実際に手を動かす課題を用意しました。
**難易度順**に並んでいます。各問に「ヒント」と「確認方法」を付けてあります。

答えは書いていません。既存コードに必ず似た実装があるので、探して真似してください。

---

## Level 1 — 既存パターンをなぞる

### 問1. 担当者一覧に「役職」で並べ替えを追加する

いま担当者一覧は「氏名」と「取引先」でしか並べ替えられません。「役職」を足してください。

<details><summary>ヒント</summary>

- `crm/views.py` の `CONTACT_SORTS` に `"title": "title"` を追加
- `templates/crm/contact_list.html` の `<thead>` に、既存の列を真似て `<th>` を追加
- `{% next_dir %}` と `{% querystring %}` の組み合わせを使う
</details>

**確認**: 役職の見出しをクリックすると ▲▼ が出て、並びが変わる。
検索条件を入れたまま並べ替えても条件が消えない。

---

### 問2. 商談一覧に「営業担当で絞り込む」プルダウンを足す

<details><summary>ヒント</summary>

- `templates/crm/deal_table.html` の `#filters` フォームに `<select name="owner">` を追加
- ビューに `if owner := request.GET.get("owner"): queryset = queryset.filter(owner_id=owner)`
- 選択肢のユーザー一覧はコンテキストに詰める
- フォームに `hx-trigger="change, …"` が既にあるので、追加の htmx 属性は不要
</details>

**確認**: プルダウンを変えた瞬間に一覧が絞り込まれ、URL も変わる。

---

### 問3. タスクの「優先度」をインライン編集できるようにする

いまインライン編集できるのは取引先と商談だけです。

<details><summary>ヒント</summary>

- `crm/forms.py` の `INLINE_EDITABLE_FIELDS` に `"Task": ["title", "due_date", "priority"]`
- `crm/views.py` に `task_inline_field` を追加（`company_inline_field` をほぼコピー）
- `crm/urls.py` にルートを追加
- `templates/crm/_task_row.html` に `inline-display` / `inline-form` パーシャルを置く
</details>

**確認**: 優先度をクリックするとプルダウンになり、保存すると表示に戻る。
`/tasks/1/field/assignee/` を直接開くと 400 が返る。

---

## Level 2 — 組み合わせる

### 問4. 取引先詳細に「担当者をその場で追加」を作る

いまは詳細ページの「＋ 追加」がモーダルを開きます。
これを**インラインのフォーム**に変え、追加した行がリストの末尾に生えるようにしてください。

<details><summary>ヒント</summary>

- `hx-swap="beforeend"` でリストの末尾に追加する
- 成功時は 204 ではなく **新しい行の HTML** を返す
- 追加された行を光らせるなら `data-flash` 属性（`app.js` が拾う）
- フォームを初期状態に戻すには、OOB でフォーム自体も返す
</details>

**確認**: ページを再読み込みせずに行が増える。連続で追加できる。

---

### 問5. 商談ボードに「担当者で絞り込む」トグルを足す

「自分の商談だけ表示」のチェックボックスをボード上部に置いてください。

<details><summary>ヒント</summary>

- `deal_board` ビューで `request.GET.get("mine")` を見て `board_context()` に渡す
- チェックボックスは `hx-get` → `hx-target="#board"` → `hx-swap="outerHTML"`
- `hx-push-url="true"` を付けて、リロードしても状態が残るように
- ⚠️ ドラッグ後にサーバがボードを返すとき、**絞り込み条件を維持する**必要がある
  （`deal_move` にも同じパラメータを渡す）
</details>

**確認**: 絞り込んだ状態でカードをドラッグしても、絞り込みが解除されない。

---

### 問6. 活動履歴の削除機能を作る

<details><summary>ヒント</summary>

- `company_delete` の「呼び出し元で返すものを変える」パターンを踏襲
- 一覧では行（`<li>`）を消す。詳細ページからはリダイレクト
- `hx-confirm` を忘れずに
- ⚠️ 無限スクロールで読み込んだ最後の要素を消すと、
  次ページを取りに行くトリガーも消える。どう対処するか考えてみてください
</details>

---

### 問7. ダッシュボードに「今週の活動件数」グラフを足す

<details><summary>ヒント</summary>

- `dashboard_pipeline` と同じ「遅延ロード」パターン
- `Activity.objects.filter(occurred_at__gte=…).annotate(day=TruncDate("occurred_at"))`
- グラフは既存の `.stack` + 幅 % の div で十分（ライブラリ不要）
</details>

---

## Level 3 — 設計を考える

### 問8. 一覧に「検索条件を保存」機能を付ける

よく使う検索条件に名前を付けて保存し、ワンクリックで復元できるようにしてください。

<details><summary>設計の論点</summary>

- モデルは `SavedSearch(name, user, url_query, model_name)` あたり
- 「いまの検索条件」をどうやって取るか
  → `request.GET.urlencode()` をサーバ側で保存するのが簡単
- 復元は単なるリンク（`?q=…&industry=…`）でよい。htmx すら要らないかもしれない
- **htmx を使わない判断も設計のうち**です
</details>

---

### 問9. 商談の「担当者を変更」を一覧から直接できるようにする

一覧の営業担当セルをクリックするとプルダウンになり、選ぶと即保存される UI。

<details><summary>設計の論点</summary>

- インライン編集パターンの応用だが、**保存ボタンが無い**
- `<select>` の既定トリガーは `change` なので、`hx-post` を付けるだけで即保存になる
- 一覧の行だけを差し替えるか、行 + 集計を OOB で更新するか
- 楽観的 UI（先に画面を変える）にするか、サーバの応答を待つか
</details>

---

### 問10. 同時編集の衝突を検出する

2人が同じ取引先を同時に編集したとき、後勝ちで上書きされてしまいます。
これを検出して警告してください。

<details><summary>設計の論点</summary>

- フォームに `updated_at` を hidden で持たせ、保存時に照合する（楽観ロック）
- 衝突したら 409 を返し、`hx-target-409` で警告を出す
- あるいは `HX-Retarget` でサーバ側から差し替え先を変える
- どちらが読みやすいか比べてみてください
</details>

---

### 問11. 権限を入れる

いまは「ログインすれば全部見える」状態です。
「自分が担当する取引先だけ見える」ようにしてください。

<details><summary>設計の論点</summary>

- QuerySet を絞る層をどこに置くか
  （`Company.objects.visible_to(user)` のようなメソッドが素直）
- 一覧・詳細・編集・削除・インライン編集・一括操作、**すべての入口**を塞ぐ必要がある
- htmx では入口が増えるので、**漏れが起きやすい**。テストで守る
- `get_object_or_404(Company.objects.visible_to(request.user), pk=pk)` の形にすると
  404 に統一できて安全
</details>

**確認**: `suzuki` でログインして、`tanaka` 担当の取引先 URL を直接叩くと 404 になる。

---

### 問12. リアルタイム更新にする

いま KPI は 30 秒ポーリングです。誰かが商談を動かした瞬間に、
全員の画面が更新されるようにしてください。

<details><summary>設計の論点</summary>

- htmx の SSE 拡張（`htmx-ext-sse`）を使うのが最短
- Django 側は `StreamingHttpResponse` か、ASGI + `django-eventstream`
- **本当にリアルタイムが必要か**を先に考える。
  ポーリングの間隔を 10 秒にするだけで済む要件かもしれない
- 接続数がユーザー数ぶん増えることのコストも見積もる
</details>

---

## 課題を解くときのコツ

1. **まず既存の似た実装を探す**。このアプリには20パターン入っています
2. **DevTools の Network を開いたまま作る**。何が飛んで何が返ったかが全部見える
3. **テストを1本書いてから実装する**。htmx は入口が増えるので、
   手で全部試すのはすぐ破綻します
4. **迷ったら「状態をサーバに置く」**。クライアントに状態を持たせた瞬間に
   htmx の利点が消えます
