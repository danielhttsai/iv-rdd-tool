/*
 * Pyodide Web Worker —— 把所有 Python 運算搬到背景執行緒。
 *
 * 為什麼：Pyodide 在主執行緒同步跑 Python，任何較重的分析（或啟動時的暖機）
 * 都會凍住 UI，造成「網頁有點當」。把 Pyodide 整個放進 Worker 後，主執行緒
 * 永遠不被 Python 阻塞——載入、暖機、按下分析都不再卡住捲動或互動。
 *
 * 主執行緒（pyodide-bridge.js）只負責 UI 遮罩與攔截 fetch，透過 postMessage
 * 把 /api/* 請求丟給這個 Worker、再把結果回傳。Python 來源仍是 backend/*.py。
 *
 * 此檔由 build_docs.py 複製到 docs/。
 */
/* global loadPyodide */

var PYODIDE_INDEX = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
// 與 pyodide-bridge.js 的 py 來源快取破壞一致；任何 backend .py 變更時一起 bump。
var PY_VER = "92";
var PY_MODULES = ["i18n", "iv_core", "assumptions", "ml_iv", "gen_data", "rdd_core", "rdd_survival", "rdd_assumptions", "rdd_gen", "rdd_ml", "did_core", "did_gen", "did_assumptions", "did_ml", "tit_core", "tit_gen", "tit_assumptions", "tit_realmle", "its_core", "its_gen", "its_assumptions", "its_ml", "perr_core", "perr_gen", "perr_assumptions", "ccw_core", "ccw_gen", "ccw_assumptions", "cctc_core", "cctc_gen", "cctc_assumptions", "seq_core", "seq_gen", "seq_assumptions", "cc_core", "cc_gen", "cc_assumptions", "cc_ml", "sccs_core", "sccs_gen", "sccs_assumptions", "sccs_ml", "acnu_core", "acnu_gen", "acnu_assumptions", "acnu_ml", "pnu_core", "pnu_gen", "pnu_assumptions", "pnu_ml", "nc_core", "nc_gen", "nc_assumptions", "nc_ml", "med_core", "med_gen", "med_assumptions", "med_ml", "ps_core", "ps_gen", "ps_assumptions", "ps_ml", "tmle_core", "tmle_gen", "tmle_assumptions", "tmle_ml", "gm_core", "gm_gen", "gm_assumptions", "gm_ml", "tnd_core", "tnd_gen", "tnd_assumptions", "tnd_ml", "pssa_core", "pssa_gen", "pssa_assumptions", "tscan_core", "tscan_gen", "tscan_assumptions", "wce_core", "wce_gen", "wce_assumptions", "missing_core", "missing_gen", "transport_core", "transport_gen", "transport_assumptions", "srma_core", "srma_gen", "extctrl_core", "extctrl_gen", "extctrl_assumptions", "api"];

var pyodide = null;
var routeFn = null;
var sklearnLoaded = false;
var readyResolve;
var readyPromise = new Promise(function (r) { readyResolve = r; });

function post(o) { self.postMessage(o); }
function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

importScripts(PYODIDE_INDEX + "pyodide.js");

async function init() {
  post({ type: "status", msg: "正在載入運算核心(Pyodide)…", pct: 25 });
  pyodide = await loadPyodide({ indexURL: PYODIDE_INDEX });

  // 核心就緒：主執行緒可立刻撤遮罩，使用者馬上能讀教學（純前端）。較重的
  // 數學套件與分析程式在背景的這個 Worker 繼續載入，完全不阻塞 UI。
  post({ type: "status", msg: "運算核心就緒 ✓", pct: 100 });
  post({ type: "ready" });

  // 套件下載(CDN)與分析程式抓取(同源)並行，縮短總等待。
  var fetchP = Promise.all(PY_MODULES.map(function (name) {
    return fetch("py/" + name + ".py?v=" + PY_VER).then(function (resp) {
      if (!resp.ok) throw new Error("載入 " + name + ".py 失敗(" + resp.status + ")");
      return resp.text().then(function (src) { return [name, src]; });
    });
  }));
  await pyodide.loadPackage(["numpy", "scipy", "pandas"]);
  var sources = await fetchP;
  sources.forEach(function (ns) { pyodide.FS.writeFile(ns[0] + ".py", ns[1]); });
  await pyodide.runPythonAsync("import api");
  routeFn = pyodide.runPython("api.route");
  readyResolve();

  // 暖機：在 Worker 執行緒上預先編譯 numpy/scipy 熱路徑，主執行緒不受影響。
  // 步驟之間讓出 Worker 事件圈，好讓使用者剛按下的分析能插隊先跑。
  await sleep(300);
  try { routeFn("GET", "/api/example", "{}", "{}"); } catch (e) { /* ignore */ }
  await sleep(50);
  try { routeFn("POST", "/api/analyze", "{}", JSON.stringify({ source: "example", lang: "zh" })); } catch (e) { /* ignore */ }
  post({ type: "warmup-done" });
}

init().catch(function (err) {
  post({ type: "init-error", message: err && err.message ? err.message : String(err) });
});

self.onmessage = async function (e) {
  var m = e.data || {};
  if (m.type !== "route") return;
  try {
    await readyPromise;
    if (m.needSklearn && !sklearnLoaded) {
      await pyodide.loadPackage("scikit-learn");
      sklearnLoaded = true;
    }
    var out = routeFn(m.method, m.path, m.query, m.body);
    post({ type: "result", id: m.id, out: out });
  } catch (err) {
    post({ type: "error", id: m.id, message: err && err.message ? err.message : String(err) });
  }
};
