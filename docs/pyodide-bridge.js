/*
 * Pyodide 橋接（主執行緒）：把這個工具的 Python 後端跑在背景 Web Worker 裡，
 * 不需要伺服器、也不阻塞 UI。
 *
 * 作法：spawn 一個 Worker（pyodide-worker.js）載入 Pyodide 與數學套件、把
 * backend 的 .py 寫進 Pyodide 檔案系統。本檔只負責：①載入遮罩與進度，②攔截
 * 所有對 /api/* 的 fetch、透過 postMessage 丟給 Worker、再把結果包成 Response。
 * 原本的 app.js 一行都不用改 —— 它以為自己還在呼叫真的後端。
 *
 * 重點：Python 運算在 Worker 執行緒上跑，主執行緒永遠不會被「暖機」或「分析」
 * 凍住，所以一開始進頁面或按下分析時不再卡頓。
 *
 * 此檔由 build_docs.py 複製到 docs/。Python 來源仍是 backend/*.py（單一來源）。
 */
(function () {
  "use strict";

  // Worker 檔的快取破壞；改動 worker 或 bridge 邏輯時 bump（py 來源版本在 worker 內的 PY_VER）。
  var WORKER_VER = "3";

  // ⑤「用 AI 強化」等需要 scikit-learn 的端點：首次呼叫時請 Worker 載入 sklearn。
  var SKLEARN_PATHS = {
    "/api/ml_forbidden": 1, "/api/did_dml": 1, "/api/its_mlcf": 1, "/api/cc_forest": 1,
    "/api/sccs_selfmatch": 1, "/api/acnu_psml": 1, "/api/pnu_psml": 1, "/api/med_natural_ml": 1,
    "/api/ps_ml": 1, "/api/tmle_ml": 1, "/api/gm_ml": 1, "/api/tnd_ml": 1,
  };

  // ---- 載入進度遮罩 -------------------------------------------------------
  function buildOverlay() {
    var o = document.createElement("div");
    o.id = "pyloader";
    o.innerHTML =
      '<div class="pyloader-box">' +
      '<div class="pyloader-logo"><img src="assets/phdc-logo.png" alt="PHDc · Population Health Data Center" /></div>' +
      '<div class="pyloader-title">真實世界證據與準實驗<span>工具箱</span></div>' +
      '<div class="pyloader-msg" id="pyloader-msg">啟動中…</div>' +
      '<div class="pyloader-track"><div class="pyloader-bar" id="pyloader-bar"></div></div>' +
      '<div class="pyloader-note">第一次開啟需下載運算核心,請稍候;之後會被瀏覽器快取。</div>' +
      "</div>";
    var css = document.createElement("style");
    css.textContent =
      "#pyloader{position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;" +
      "background:radial-gradient(120% 120% at 50% 0%,#ffffff 0%,#f1f7f6 60%,#e6f1ef 100%);color:#14283c;" +
      "transition:opacity .5s ease;font-family:system-ui,'Noto Sans TC',sans-serif}" +
      ".pyloader-box{max-width:460px;width:86%;text-align:center;padding:2rem}" +
      ".pyloader-logo{margin:0 auto 1.5rem;display:block}" +
      ".pyloader-logo img{height:96px;width:auto;display:block;margin:0 auto}" +
      ".pyloader-title{font-size:1.5rem;font-weight:800;margin-bottom:1.2rem;letter-spacing:.5px;color:#14283c}" +
      ".pyloader-title span{color:#3f8268}" +
      ".pyloader-msg{font-size:1rem;margin-bottom:1rem;min-height:1.4em;color:#334155}" +
      ".pyloader-track{height:8px;border-radius:99px;background:#dbe7e4;overflow:hidden}" +
      ".pyloader-bar{height:100%;width:5%;border-radius:99px;background:linear-gradient(90deg,#3f8268,#79c2a2);transition:width .4s ease}" +
      ".pyloader-note{margin-top:1.2rem;font-size:.8rem;color:#64748b;line-height:1.6}";
    document.head.appendChild(css);
    (document.body || document.documentElement).appendChild(o);
  }
  function setStatus(msg, pct) {
    var m = document.getElementById("pyloader-msg");
    if (m && msg != null) m.textContent = msg;
    var b = document.getElementById("pyloader-bar");
    if (b && pct != null) b.style.width = pct + "%";
  }
  function hideOverlay() {
    var o = document.getElementById("pyloader");
    if (!o) return;
    o.style.opacity = "0";
    setTimeout(function () { if (o.parentNode) o.parentNode.removeChild(o); }, 600);
  }

  // ---- 背景載入小提示(角落膠囊)------------------------------------------
  function buildPill() {
    if (document.getElementById("pycompute")) return;
    var en = (document.documentElement.lang || "").indexOf("en") === 0;
    var p = document.createElement("div");
    p.id = "pycompute";
    p.innerHTML = '<span class="pyc-dot"></span><span id="pyc-msg">' +
      (en ? "Warming up the compute core… (you can read the teaching tabs now)"
          : "運算核心熱機中…（教學分頁已可閱讀）") + "</span>";
    var css = document.createElement("style");
    css.textContent =
      "#pycompute{position:fixed;right:14px;bottom:14px;z-index:9998;display:flex;align-items:center;gap:.5rem;" +
      "background:#14283c;color:#fff;padding:.5rem .9rem;border-radius:999px;max-width:80vw;" +
      "font:600 .82rem system-ui,'Noto Sans TC',sans-serif;box-shadow:0 4px 14px rgba(0,0,0,.18);" +
      "opacity:.96;transition:opacity .4s}" +
      ".pyc-dot{width:9px;height:9px;border-radius:50%;background:#79c2a2;flex:0 0 auto;animation:pycpulse 1s infinite}" +
      "@keyframes pycpulse{0%,100%{opacity:.35}50%{opacity:1}}";
    document.head.appendChild(css);
    (document.body || document.documentElement).appendChild(p);
  }
  function setPill(msg) { var m = document.getElementById("pyc-msg"); if (m && msg) m.textContent = msg; }
  function removePill() {
    var p = document.getElementById("pycompute"); if (!p) return;
    p.style.opacity = "0";
    setTimeout(function () { if (p.parentNode) p.parentNode.removeChild(p); }, 400);
  }

  // ---- Worker：所有 Python 都在這顆背景執行緒裡跑 -------------------------
  buildOverlay();   // 同步蓋上遮罩（此時 <body> 尚未繪出，避免閃第一頁）

  var worker = new Worker("pyodide-worker.js?v=" + WORKER_VER);
  var nextId = 1;
  var pending = {};         // id -> {resolve, reject}
  var coreReadyResolve;
  var coreReady = new Promise(function (r) { coreReadyResolve = r; });

  worker.onmessage = function (e) {
    var m = e.data || {};
    switch (m.type) {
      case "status": setStatus(m.msg, m.pct); break;
      case "ready":
        setStatus("運算核心就緒 ✓", 100);
        hideOverlay();
        buildPill();
        coreReadyResolve();
        break;
      case "warmup-done": removePill(); break;
      case "init-error":
        setStatus("載入失敗：" + m.message, null);
        setPill("載入失敗：" + m.message);
        console.error("[pyodide-bridge] worker init failed", m.message);
        break;
      case "result": {
        var pr = pending[m.id];
        if (pr) { delete pending[m.id]; pr.resolve(m.out); }
        break;
      }
      case "error": {
        var pe = pending[m.id];
        if (pe) { delete pending[m.id]; pe.reject(new Error(m.message)); }
        break;
      }
    }
  };
  worker.onerror = function (err) {
    setStatus("載入失敗：" + (err && err.message ? err.message : "worker error"), null);
    console.error("[pyodide-bridge] worker error", err);
  };

  function callRoute(method, path, query, body, needSklearn) {
    return new Promise(function (resolve, reject) {
      var id = nextId++;
      pending[id] = { resolve: resolve, reject: reject };
      worker.postMessage({ type: "route", id: id, method: method, path: path,
        query: query, body: body, needSklearn: !!needSklearn });
    });
  }

  // ---- 處理一個 /api/* 請求 ----------------------------------------------
  async function handleApi(method, url, init) {
    var u = new URL(url, location.href);
    var path = u.pathname;
    var query = {};
    u.searchParams.forEach(function (v, k) { query[k] = v; });

    var bodyObj = {};
    if (init && init.body) {
      if (typeof FormData !== "undefined" && init.body instanceof FormData) {
        var file = init.body.get("file");
        bodyObj = { _csv_text: file ? await file.text() : "" };
      } else if (typeof init.body === "string") {
        try { bodyObj = JSON.parse(init.body); } catch (e) { bodyObj = {}; }
      }
    }

    var out = await callRoute(method, path, JSON.stringify(query), JSON.stringify(bodyObj),
      SKLEARN_PATHS[path] === 1);
    var env = JSON.parse(out);
    return new Response(JSON.stringify(env.body), {
      status: env.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  // ---- 攔截 fetch ---------------------------------------------------------
  var realFetch = window.fetch ? window.fetch.bind(window) : null;
  window.fetch = function (input, init) {
    var url = typeof input === "string" ? input : (input && input.url) || "";
    if (url && url.indexOf("/api/") !== -1) {
      var method = (init && init.method) ||
        (typeof input !== "string" && input && input.method) || "GET";
      return handleApi(method, url, init || {});
    }
    return realFetch(input, init);
  };

  // 讓 app.js（若有需要）能等核心就緒；目前各分頁都靠 fetch 攔截即可。
  window.__pyReady = coreReady;
})();
