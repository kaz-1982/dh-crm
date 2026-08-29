/* ==========================================================================
   htmx を補助する最小限の JavaScript。
   「SPA を書かない」のが htmx の主旨なので、ここに書くのは
   (1) サーバから飛んでくるイベントの受け口 (2) ライブラリの初期化 だけ。
   ========================================================================== */

(() => {
  "use strict";

  // --- 1. トースト ---------------------------------------------------------
  // サーバは HX-Trigger: {"toast": {...}} を返すだけ。
  // htmx がそれを body の CustomEvent に変換してくれるので、ここで受ける。
  document.body.addEventListener("toast", (event) => {
    showToast(event.detail.message, event.detail.level || "success");
  });

  function showToast(message, level = "success") {
    const host = document.getElementById("toasts");
    if (!host) return;
    const el = document.createElement("div");
    el.className = `toast ${level}`;
    el.setAttribute("role", "status");
    el.textContent = message;
    host.appendChild(el);
    setTimeout(() => {
      el.classList.add("leaving");
      el.addEventListener("animationend", () => el.remove());
    }, 3200);
  }
  window.showToast = showToast;

  // --- 2. モーダル ---------------------------------------------------------
  // <dialog> は標準要素。開閉だけ JS で面倒を見て、中身は htmx が入れ替える。
  const modal = document.getElementById("modal");

  // フォーム断片が #modal-body に入った瞬間にダイアログを開く
  document.body.addEventListener("htmx:afterSwap", (event) => {
    if (event.target.id === "modal-body" && !modal.open) modal.showModal();
  });

  // サーバから「閉じろ」と言われたら閉じる (HX-Trigger: closeModal)
  document.body.addEventListener("closeModal", () => closeModal());

  function closeModal() {
    if (!modal) return;
    if (modal.open) modal.close();
    clearModalLater();
  }
  window.closeModal = closeModal;

  // ⚠️ ここは実際にハマったポイント。
  // サーバは HX-Trigger で {closeModal, companyListChanged, toast} を
  // まとめて返すが、htmx はこれらを「リクエストを出した要素」の上で
  // 順番に発火させる。その要素はモーダルの中のフォームなので、
  // closeModal を受けた瞬間に innerHTML を空にしてしまうと、
  // フォームが DOM から切り離され、残りのイベントが body まで
  // バブリングしなくなる（＝一覧が更新されない）。
  // 片付けを次のタスクに回して、同期的な切断を避ける。
  function clearModalLater() {
    setTimeout(() => {
      const body = document.getElementById("modal-body");
      if (body && !modal.open) body.innerHTML = "";
    }, 0);
  }

  // 背景クリックで閉じる
  modal?.addEventListener("click", (event) => {
    if (event.target === modal) closeModal();
  });
  modal?.addEventListener("close", clearModalLater);

  // --- 3. カンバンのドラッグ&ドロップ --------------------------------------
  // SortableJS で並べ替え、確定したら htmx.ajax() でサーバに投げる。
  // htmx は属性で書くのが基本だが、こういう「JS 起点の通信」もできる。
  function initSortable() {
    document.querySelectorAll(".board-list").forEach((list) => {
      if (list.dataset.sortableReady) return;
      list.dataset.sortableReady = "1";
      Sortable.create(list, {
        group: "deals",
        animation: 140,
        ghostClass: "sortable-ghost",
        dragClass: "sortable-drag",
        // HTML5 のネイティブ DnD ではなく SortableJS 自身の実装を使う。
        //  - タッチ端末でも同じ挙動になる
        //  - dragClass のスタイル（傾き・影）がブラウザ差なく効く
        //  - ポインタイベントで動くので E2E テストから操作できる
        forceFallback: true,
        fallbackTolerance: 3,
        onEnd(event) {
          const card = event.item;
          const stage = event.to.dataset.stage;
          // ⚠️ children ではなく .deal-card を拾うこと。
          //    空の列には「ここにドラッグ」のプレースホルダが入っており、
          //    それも children に含まれるため undefined が混ざる。
          const order = Array.from(event.to.querySelectorAll(".deal-card"))
            .map((el) => el.dataset.dealId);
          htmx.ajax("POST", `/deals/${card.dataset.dealId}/move/`, {
            target: "#board",
            swap: "outerHTML",
            values: { stage, order },
          });
        },
      });
    });
  }

  // 初回 + htmx がボードを差し替えた後に再初期化する
  document.addEventListener("DOMContentLoaded", initSortable);
  document.body.addEventListener("htmx:afterSettle", initSortable);

  // --- 4. 一括操作のチェックボックス ---------------------------------------
  document.body.addEventListener("change", (event) => {
    if (event.target.matches("[data-check-all]")) {
      const scope = document.querySelector(event.target.dataset.checkAll);
      scope?.querySelectorAll("input[name=selected]").forEach((cb) => {
        cb.checked = event.target.checked;
      });
    }
    if (event.target.matches("[data-check-all], input[name=selected]")) {
      updateBulkBar();
    }
  });
  document.body.addEventListener("htmx:afterSettle", updateBulkBar);

  function updateBulkBar() {
    const bar = document.getElementById("bulk-bar");
    if (!bar) return;
    const n = document.querySelectorAll("input[name=selected]:checked").length;
    bar.hidden = n === 0;
    const label = bar.querySelector("[data-count]");
    if (label) label.textContent = n;
  }

  // --- 5. エラーハンドリング -----------------------------------------------
  // 4xx/5xx はデフォルトでは画面に何も出ないので、必ず自分で拾う。
  document.body.addEventListener("htmx:responseError", (event) => {
    const status = event.detail.xhr.status;
    if (status === 422) return; // バリデーションエラーは response-targets が処理
    if (status === 403) {
      showToast("権限がありません（セッション切れかも）", "error");
      return;
    }
    showToast(`エラーが発生しました (HTTP ${status})`, "error");
  });

  document.body.addEventListener("htmx:sendError", () => {
    showToast("サーバに接続できませんでした", "error");
  });

  // --- 6. 追加された行を光らせる -------------------------------------------
  document.body.addEventListener("htmx:afterSwap", (event) => {
    if (event.target.dataset?.flash !== undefined) {
      event.target.classList.add("flash-new");
      setTimeout(() => event.target.classList.remove("flash-new"), 1200);
    }
  });

  // --- 7. Esc でインライン編集をキャンセル ---------------------------------
  document.body.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const form = event.target.closest?.("[data-inline-form]");
    if (form) {
      event.preventDefault();
      htmx.trigger(form.querySelector("[data-cancel]"), "click");
    }
  });
})();
