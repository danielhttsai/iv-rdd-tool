/*
 * Pyodide 橋接：讓這個工具的 Python 後端完全在瀏覽器裡跑,不需要伺服器。
 *
 * 作法:載入 Pyodide 與數學套件,把 backend 的 .py 寫進 Pyodide 檔案系統,
 * 然後攔截所有對 /api/* 的 fetch,改交給 py/api.py 的 route() 處理。
 * 這樣原本的 app.js 一行都不用改 —— 它以為自己還在呼叫真的後端。
 *
 * 此檔由 build_docs.py 複製到 docs/。Python 來源仍是 backend/*.py(單一來源)。
 */
(function () {
  "use strict";

  // Pyodide 套件版本需與 index.html 載入的 pyodide.js 相符
  var PYODIDE_INDEX = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
  var PY_MODULES = ["i18n", "iv_core", "assumptions", "ml_iv", "gen_data", "rdd_core", "rdd_survival", "rdd_assumptions", "rdd_gen", "rdd_ml", "did_core", "did_gen", "did_assumptions", "did_ml", "tit_core", "tit_gen", "tit_assumptions", "its_core", "its_gen", "its_assumptions", "its_ml", "perr_core", "perr_gen", "perr_assumptions", "ccw_core", "ccw_gen", "ccw_assumptions", "cctc_core", "cctc_gen", "cctc_assumptions", "seq_core", "seq_gen", "seq_assumptions", "api"];

  var pyodide = null;
  var routeFn = null;
  var readyPromise = null;
  var sklearnLoaded = false;

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

  // ---- 初始化 Pyodide -----------------------------------------------------
  async function init() {
    if (document.readyState === "loading") {
      await new Promise(function (r) { document.addEventListener("DOMContentLoaded", r); });
    }
    buildOverlay();
    try {
      setStatus("正在載入運算核心(Pyodide)…", 12);
      pyodide = await loadPyodide({ indexURL: PYODIDE_INDEX });

      setStatus("正在載入數學套件(numpy / scipy / pandas)…", 38);
      await pyodide.loadPackage(["numpy", "scipy", "pandas"]);

      setStatus("正在載入分析程式…", 72);
      for (var i = 0; i < PY_MODULES.length; i++) {
        var name = PY_MODULES[i];
        var resp = await fetch("py/" + name + ".py");
        if (!resp.ok) throw new Error("載入 " + name + ".py 失敗(" + resp.status + ")");
        var src = await resp.text();
        pyodide.FS.writeFile(name + ".py", src);
      }
      await pyodide.runPythonAsync("import api");
      routeFn = pyodide.runPython("api.route");

      // 預熱：在遮罩還在時先跑一次常用分析,觸發 numpy/scipy 的 JIT 編譯,
      // 這樣使用者第一次點分頁時不會卡住幾秒(設限存活除外,它在按鈕後才算)。
      setStatus("正在預熱分析核心…", 90);
      warmup();

      setStatus("準備就緒 ✓", 100);
      hideOverlay();
    } catch (err) {
      setStatus("載入失敗：" + (err && err.message ? err.message : err), null);
      console.error("[pyodide-bridge] init failed", err);
      throw err;
    }
  }
  function ready() {
    if (!readyPromise) readyPromise = init();
    return readyPromise;
  }

  // 跑幾個常用端點一次,讓 Pyodide 先把熱路徑編譯好(結果丟棄)。
  function warmup() {
    var calls = [
      ["GET", "/api/example", "{}", "{}"],
      ["GET", "/api/rdd_example", "{}", "{}"],
      ["POST", "/api/analyze", "{}", JSON.stringify({ source: "example", lang: "zh" })],
      ["POST", "/api/rdd_analyze", "{}", JSON.stringify({
        source: "example_rdd", running: "age", outcome: "health_score_change",
        treatment: "vaccinated", cutoff: 65, time: "event_time", event: "event",
        covariates: ["female", "bmi", "chronic_conditions", "income_band"], lang: "zh",
      })],
      ["POST", "/api/rdd_assumptions", "{}", JSON.stringify({ source: "example_rdd", lang: "zh" })],
      ["GET", "/api/did_example", "{}", "{}"],
      ["POST", "/api/did_analyze", "{}", JSON.stringify({ source: "example_did", lang: "zh" })],
      ["POST", "/api/did_assumptions", "{}", JSON.stringify({ source: "example_did", lang: "zh" })],
      ["GET", "/api/tit_example", "{}", "{}"],
      ["POST", "/api/tit_analyze", "{}", JSON.stringify({ source: "example_tit", lang: "zh" })],
      ["GET", "/api/its_example", "{}", "{}"],
      ["POST", "/api/its_analyze", "{}", JSON.stringify({ source: "example_its", lang: "zh" })],
      ["GET", "/api/perr_example", "{}", "{}"],
      ["POST", "/api/perr_analyze", "{}", JSON.stringify({ source: "example_perr", lang: "zh" })],
      ["GET", "/api/ccw_example", "{}", "{}"],
      ["POST", "/api/ccw_analyze", "{}", JSON.stringify({ source: "example_ccw", lang: "zh" })],
      ["GET", "/api/cctc_example", "{}", "{}"],
      ["POST", "/api/cctc_analyze", "{}", JSON.stringify({ source: "example_cctc", lang: "zh" })],
      ["GET", "/api/seq_example", "{}", "{}"],
      ["POST", "/api/seq_analyze", "{}", JSON.stringify({ source: "example_seq", lang: "zh" })],
    ];
    for (var i = 0; i < calls.length; i++) {
      try { routeFn(calls[i][0], calls[i][1], calls[i][2], calls[i][3]); }
      catch (e) { /* 預熱失敗不影響功能,忽略 */ }
    }
  }

  async function ensureSklearn() {
    if (sklearnLoaded) return;
    await pyodide.loadPackage("scikit-learn");
    sklearnLoaded = true;
  }

  // ---- 處理一個 /api/* 請求 ----------------------------------------------
  async function handleApi(method, url, init) {
    await ready();
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

    if (path === "/api/ml_forbidden" || path === "/api/did_dml" || path === "/api/its_mlcf") {
      setStatus && null; // sklearn 首次載入(無遮罩,由按鈕顯示「計算中」)
      await ensureSklearn();
    }

    var out = routeFn(method, path, JSON.stringify(query), JSON.stringify(bodyObj));
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

  // 立刻開始載入(背景),這樣 app.js 載入時遮罩已在跑
  ready();
})();
