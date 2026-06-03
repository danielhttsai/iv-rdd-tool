"use strict";

const API = "";  // same origin
const state = {
  source: null, columns: [], numeric: [],
  // remembered inputs/outputs so a language switch can re-render
  lastReq: null, nlData: null, fbData: null, cmpDone: false,
};
const tr = (zh, en) => window.IV.tr(zh, en);
const lang = () => window.IV.lang;

// ----- navigation: method dropdown + sub-tabs -----
const METHOD_PREFIX = { iv: "", rdd: "rdd", did: "did", tit: "tit", its: "its", perr: "perr" };
const PANEL_INIT = {
  play: () => refreshPlay(), ml: () => initMl(),
  rddplay: () => initRdd(), rddanalyze: () => initRddAnalyze(),
  rddassume: () => initRddAssume(), rddml: () => initRddMl(),
  didlearn: () => initDidLearn(), didplay: () => initDidPlay(), didanalyze: () => initDidAnalyze(),
  didassume: () => initDidAssume(), didml: () => initDidMl(),
  titlearn: () => initTitLearn(), titplay: () => initTitPlay(),
  titanalyze: () => initTitAnalyze(), titassume: () => initTitAssume(),
  itslearn: () => initItsLearn(), itsplay: () => initItsPlay(), itsanalyze: () => initItsAnalyze(),
  itsassume: () => initItsAssume(), itsml: () => initItsMl(),
  perrlearn: () => initPerrLearn(), perrplay: () => initPerrPlay(), perranalyze: () => initPerrAnalyze(),
  perrassume: () => initPerrAssume(), perrml: () => initPerrMl(),
  choose: () => initChoose(),
};
let curMethod = "iv", curSub = "learn";
const methodSelect = document.getElementById("methodSelect");
const subtabBtns = [...document.querySelectorAll(".subtab")];
const chooseTab = document.getElementById("chooseTab");

function showPanel(panelId) {
  document.querySelectorAll(".panel").forEach((x) => x.classList.remove("active"));
  const el = document.getElementById(panelId);
  if (el) el.classList.add("active");
  if (PANEL_INIT[panelId]) PANEL_INIT[panelId]();
  window.scrollTo(0, 0);
}
function showMethodSub() {
  chooseTab.classList.remove("active");
  subtabBtns.forEach((b) => b.classList.toggle("active", b.dataset.sub === curSub));
  showPanel(METHOD_PREFIX[curMethod] + curSub);
}
methodSelect.addEventListener("change", () => { curMethod = methodSelect.value; showMethodSub(); });
subtabBtns.forEach((b) => b.addEventListener("click", () => { curSub = b.dataset.sub; showMethodSub(); }));
chooseTab.addEventListener("click", () => {
  subtabBtns.forEach((x) => x.classList.remove("active"));
  chooseTab.classList.add("active");
  showPanel("choose");
});

async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
  return r.json();
}
async function postJSON(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
  return r.json();
}
const fmt = (x, d = 2) => (x === null || x === undefined || Number.isNaN(x) ? "–" : Number(x).toFixed(d));

// ======================================================================
// 2. Interactive teaching
// ======================================================================
const csSlider = document.getElementById("csSlider");
const stSlider = document.getElementById("stSlider");
let playTimer = null;

function scheduleRefreshPlay() {
  document.getElementById("csVal").textContent = Number(csSlider.value).toFixed(1) + "%";
  document.getElementById("stVal").textContent = Number(stSlider.value).toFixed(1) + "×";
  clearTimeout(playTimer);
  playTimer = setTimeout(refreshPlay, 120);
}
csSlider.addEventListener("input", scheduleRefreshPlay);
stSlider.addEventListener("input", scheduleRefreshPlay);

async function refreshPlay() {
  const cs = Number(csSlider.value) / 100;
  const st = Number(stSlider.value);
  let d;
  try {
    d = await getJSON(`${API}/api/interactive?complier_share=${cs}&strength=${st}`);
  } catch (e) { return; }

  document.getElementById("fStat").textContent = fmt(d.f_stat, 0);
  const weak = d.f_stat < 10;
  document.getElementById("fNote").textContent = weak
    ? tr("太弱，答案會亂跳 ⚠（F<10）", "Too weak, the answer jumps around ⚠ (F<10)")
    : tr("夠力 ✓（F>10）", "Strong enough ✓ (F>10)");
  document.getElementById("fNote").style.color = weak ? "var(--red)" : "var(--green)";
  document.getElementById("ivEst").textContent = fmt(d.estimate, 2);
  document.getElementById("ivCi").textContent = `${fmt(d.ci[0], 2)} ~ ${fmt(d.ci[1], 2)}`;
  const width = d.ci[1] - d.ci[0];
  document.getElementById("ciNote").textContent = tr(`寬度 ${fmt(width, 2)}`, `width ${fmt(width, 2)}`);

  Plotly.react("playChart", [
    {
      x: [tr("IV 估計", "IV estimate")], y: [d.estimate],
      error_y: { type: "data", symmetric: false,
        array: [d.ci[1] - d.estimate], arrayminus: [d.estimate - d.ci[0]], color: "#6366f1", thickness: 3, width: 14 },
      type: "scatter", mode: "markers", marker: { size: 16, color: "#6366f1" }, name: "IV",
    },
  ], {
    margin: { t: 24, r: 20, b: 40, l: 50 }, showlegend: false,
    yaxis: { title: tr("估計效果", "Estimated effect"), range: [-2, 5], zeroline: true },
    shapes: [{ type: "line", x0: -0.5, x1: 0.5, y0: 1.8, y1: 1.8, line: { color: "#10b981", dash: "dash", width: 2 } }],
    annotations: [{ x: 0.45, y: 1.8, text: tr("真值 1.80", "truth 1.80"), showarrow: false, font: { color: "#10b981" }, yshift: 12 }],
  }, { displayModeBar: false, responsive: true });
}

// ======================================================================
// 3. Analysis — data loading + column mapping
// ======================================================================
const dataStatus = document.getElementById("dataStatus");

function fillSelects() {
  const opts = state.columns.map((c) => `<option value="${c}">${c}</option>`).join("");
  ["selY", "selA", "selZ", "selCov"].forEach((id) => { document.getElementById(id).innerHTML = opts; });
  document.getElementById("colMap").classList.remove("hidden");
}

function applyDefaults(d) {
  if (!d) return;
  document.getElementById("selY").value = d.outcome;
  document.getElementById("selA").value = d.treatment;
  document.getElementById("selZ").value = d.instrument;
  const cov = document.getElementById("selCov");
  [...cov.options].forEach((o) => { o.selected = d.covariates.includes(o.value); });
}

document.getElementById("useExample").addEventListener("click", async () => {
  try {
    const d = await getJSON(`${API}/api/example`);
    state.source = "example"; state.columns = d.columns;
    dataStatus.textContent = tr(
      `已載入內建接種提醒示範資料（${d.n} 筆，合成虛構）`,
      `Loaded built-in vaccine-reminder demo data (${d.n} rows, synthetic & fictional)`);
    fillSelects(); applyDefaults(d.defaults);
  } catch (e) { dataStatus.textContent = tr("載入失敗：", "Load failed: ") + e.message; }
});

document.getElementById("fileInput").addEventListener("change", async (ev) => {
  const file = ev.target.files[0];
  if (!file) return;
  const fd = new FormData(); fd.append("file", file);
  dataStatus.textContent = tr("上傳中…", "Uploading…");
  try {
    const r = await fetch(`${API}/api/upload`, { method: "POST", body: fd });
    if (!r.ok) throw new Error((await r.json()).detail);
    const d = await r.json();
    state.source = d.token; state.columns = d.columns;
    dataStatus.textContent = tr(`已上傳「${file.name}」（${d.n} 筆）`, `Uploaded "${file.name}" (${d.n} rows)`);
    fillSelects();
  } catch (e) { dataStatus.textContent = tr("上傳失敗：", "Upload failed: ") + e.message; }
});

function currentMapping() {
  return {
    source: state.source,
    outcome: document.getElementById("selY").value,
    treatment: document.getElementById("selA").value,
    instrument: document.getElementById("selZ").value,
    covariates: [...document.getElementById("selCov").selectedOptions].map((o) => o.value),
    lang: lang(),
  };
}

document.getElementById("runAnalyze").addEventListener("click", async () => {
  const req = currentMapping();
  try {
    const out = await postJSON(`${API}/api/analyze`, req);
    state.lastReq = req;
    renderAnalysis(out);
    runAssumptions(req);  // keep dashboard in sync
  } catch (e) { alert(tr("分析失敗：", "Analysis failed: ") + e.message); }
});

function renderAnalysis(out) {
  document.getElementById("analyzeOut").classList.remove("hidden");
  const ivCov = out.iv_with_covariates;
  const labels = [tr("未調整 naive", "Naive"), tr("Wald", "Wald"), tr("2SLS", "2SLS")];
  const vals = [out.naive.estimate, out.wald.estimate, out.iv.estimate];
  if (ivCov) { labels.push(tr("2SLS+共變項", "2SLS+covariates")); vals.push(ivCov.estimate); }
  const colors = vals.map((_, i) => (i === 0 ? "#ef4444" : "#6366f1"));

  Plotly.react("estChart", [{
    x: labels, y: vals, type: "bar",
    marker: { color: colors },
    text: vals.map((v) => fmt(v, 2)), textposition: "outside",
  }], {
    margin: { t: 30, r: 20, b: 50, l: 50 },
    yaxis: { title: tr("對結果的估計效果", "Estimated effect on the outcome") },
    shapes: [{ type: "line", x0: -0.5, x1: labels.length - 0.5, y0: out.iv.estimate, y1: out.iv.estimate,
               line: { color: "#10b981", dash: "dot", width: 1.5 } }],
  }, { displayModeBar: false, responsive: true });

  const FS = tr("第一階段（工具→處置）", "First stage (instrument→treatment)");
  const cards = [
    [tr("未調整迴歸（naive）", "Naive regression"), out.naive.estimate, out.naive.interpretation, false],
    [FS, out.first_stage.coef, out.first_stage.interpretation, false],
    [tr("簡化式（工具→結果）", "Reduced form (instrument→outcome)"), out.reduced_form.coef, out.reduced_form.interpretation, false],
    [tr("Wald 估計", "Wald estimate"), out.wald.estimate, out.wald.interpretation, false],
    [tr("2SLS（工具變數）", "2SLS (instrumental variable)"), out.iv.estimate, out.iv.interpretation, true],
  ];
  if (ivCov) cards.push([tr("2SLS + 共變項", "2SLS + covariates"), ivCov.estimate, ivCov.interpretation, false]);
  document.getElementById("resultCards").innerHTML = cards.map(([t, v, desc, hl]) =>
    `<div class="rc ${hl ? "highlight" : ""}"><h3>${t}</h3><div class="big">${fmt(v, hl || t === FS ? 3 : 2)}</div><p>${desc}</p></div>`
  ).join("");
}

// ======================================================================
// 4. Assumptions dashboard
// ======================================================================
async function runAssumptions(req) {
  try {
    const out = await postJSON(`${API}/api/assumptions`, req);
    renderAssumptions(out);
  } catch (e) { /* ignore */ }
}

function renderAssumptions(out) {
  document.getElementById("assumeHint").classList.add("hidden");
  const ov = document.getElementById("overall");
  ov.classList.remove("hidden");
  ov.className = `overall st-${out.overall_status}`;
  ov.style.background = "#fff";
  ov.innerHTML = `<span class="dot bg-${out.overall_status}"></span> ${out.overall_headline}`;

  document.getElementById("assumeCards").innerHTML = out.checks.map((c) => {
    const metrics = c.metrics.map((m) =>
      `<li>${m.name}<b>${m.value}</b><span>${m.note || ""}</span></li>`).join("");
    return `<div class="acard st-${c.status}">
      <h3><span class="dot bg-${c.status}"></span>${c.title}
        <span class="badge bg-${c.status}">${statusText(c.status)}</span></h3>
      <p class="headline"><b>${c.headline}</b></p>
      <p class="plain">${c.plain}</p>
      <ul class="metrics">${metrics}</ul>
      <details class="term"><summary>${tr("看專有名詞解釋", "Show term explanation")}</summary><p>${c.term}</p></details>
    </div>`;
  }).join("");
}
function statusText(s) {
  const zh = { green: "通過", amber: "警示", red: "不符", info: "需判斷" };
  const en = { green: "Pass", amber: "Caution", red: "Fail", info: "Judgement" };
  return (lang() === "en" ? en : zh)[s] || s;
}

// ======================================================================
// 5. ML + IV demos
// ======================================================================
const TEAL = "#0d9488", AMBER = "#f59e0b", RED = "#ef4444", GREEN = "#10b981", INK = "#14283c";
const STATUS_COLOR = { good: TEAL, weak: AMBER, bad: RED, trap: AMBER };

// ---- deterministic seeded RNG for the "what does the data look like" mini charts ----
function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function randn(rng) {
  let u = 0, v = 0;
  while (u === 0) u = rng();
  while (v === 0) v = rng();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}
const SCENE_CFG = { displayModeBar: false, responsive: true };
const sceneLayout = (extra) => Object.assign({
  margin: { t: 26, r: 16, b: 40, l: 50 }, height: 280, showlegend: false,
  font: { size: 11 }, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
}, extra || {});

// scene 1 (IV remedy 1): one weak instrument — two barely-separated clouds
function drawSceneWeak() {
  if (!document.getElementById("sceneWeak")) return;
  const rng = mulberry32(101);
  const x0 = [], y0 = [], x1 = [], y1 = [];
  for (let i = 0; i < 150; i++) {
    const nudged = rng() < 0.5 ? 1 : 0;
    // weak: nudged only nudges shot probability a little
    const p = nudged ? 0.55 : 0.45;
    const shot = rng() < p ? 1 : 0;
    // spread each cloud out so the two bands read as fat clouds, not thin lines
    const xv = nudged + randn(rng) * 0.11;
    const yv = shot + randn(rng) * 0.12;
    if (nudged) { x1.push(xv); y1.push(yv); } else { x0.push(xv); y0.push(yv); }
  }
  const mk = (x, y, c) => ({ x, y, mode: "markers", type: "scatter",
    marker: { color: c, size: 7, opacity: 0.6 } });
  Plotly.react("sceneWeak", [mk(x0, y0, INK), mk(x1, y1, TEAL)], sceneLayout({
    xaxis: { tickvals: [0, 1], ticktext: [tr("沒被推", "not nudged"), tr("有被推", "nudged")], range: [-0.55, 1.55] },
    yaxis: { tickvals: [0, 1], ticktext: [tr("沒打針", "no shot"), tr("有打針", "got shot")], range: [-0.55, 1.55] },
  }), SCENE_CFG);
}

// scene 2 (IV remedy 2): hill-shaped first stage — distance vs uptake
function drawSceneBend() {
  if (!document.getElementById("sceneBend")) return;
  const rng = mulberry32(202);
  const xs = [], ys = [];
  for (let i = 0; i < 90; i++) {
    const d = rng() * 10;                 // distance 0..10 km
    const hill = Math.exp(-Math.pow((d - 5) / 2.4, 2)); // peak at 5
    const yv = 0.12 + 0.7 * hill + randn(rng) * 0.06;
    xs.push(d); ys.push(yv);
  }
  const cx = [], cy = [];
  for (let d = 0; d <= 10; d += 0.2) { cx.push(d); cy.push(0.12 + 0.7 * Math.exp(-Math.pow((d - 5) / 2.4, 2))); }
  const meanY = ys.reduce((a, b) => a + b, 0) / ys.length;
  const dots = { x: xs, y: ys, mode: "markers", type: "scatter", marker: { color: "#9aa6b2", size: 6, opacity: 0.7 } };
  const curve = { x: cx, y: cy, mode: "lines", type: "scatter", line: { color: TEAL, width: 3 } };
  const flat = { x: [0, 10], y: [meanY, meanY], mode: "lines", type: "scatter", line: { color: AMBER, width: 2, dash: "dash" } };
  Plotly.react("sceneBend", [dots, flat, curve], sceneLayout({
    xaxis: { title: tr("離快打車距離 (km)", "distance to van (km)"), range: [-0.3, 10.3] },
    yaxis: { title: tr("打針率", "uptake"), range: [0, 1] },
  }), SCENE_CFG);
}

// scene 3 (IV remedy 3): overfitting — red wiggle threads every point vs green truth
function drawSceneOverfit() {
  if (!document.getElementById("sceneOverfit")) return;
  const rng = mulberry32(303);
  const xs = [], ys = [];
  const truth = (x) => 0.5 + 0.35 * Math.sin(x * 0.9);
  for (let i = 0; i < 22; i++) {
    const x = (i / 21) * 10;
    xs.push(x); ys.push(truth(x) + randn(rng) * 0.16);
  }
  // green dashed truth
  const tx = [], ty = [];
  for (let x = 0; x <= 10; x += 0.1) { tx.push(x); ty.push(truth(x)); }
  // red wiggle: piecewise through every point (Catmull-Rom-ish via plotly spline)
  const dots = { x: xs, y: ys, mode: "markers", type: "scatter", marker: { color: INK, size: 7 } };
  const truthLine = { x: tx, y: ty, mode: "lines", type: "scatter", line: { color: GREEN, width: 3, dash: "dash" } };
  const wiggle = { x: xs, y: ys, mode: "lines", type: "scatter", line: { color: RED, width: 2, shape: "spline", smoothing: 1.3 } };
  Plotly.react("sceneOverfit", [truthLine, wiggle, dots], sceneLayout({
    xaxis: { title: tr("外力強度", "nudge strength"), range: [-0.3, 10.3] },
    yaxis: { title: tr("反應", "response"), range: [-0.2, 1.3] },
  }), SCENE_CFG);
}

// scene 4 (RDD remedy 1): sloped trend + jump at 65, wide window band
function drawSceneTrend() {
  if (!document.getElementById("sceneTrend")) return;
  const rng = mulberry32(404);
  const xl = [], yl = [], xr = [], yr = [];
  for (let i = 0; i < 120; i++) {
    const age = 45 + rng() * 40;          // 45..85
    const elig = age >= 65 ? 1 : 0;
    const yv = 0.42 * (age - 65) / 5 + 1.8 * elig + randn(rng) * 1.4 + 6;
    if (elig) { xr.push(age); yr.push(yv); } else { xl.push(age); yl.push(yv); }
  }
  const left = { x: xl, y: yl, mode: "markers", type: "scatter", marker: { color: "#9aa6b2", size: 5, opacity: 0.7 } };
  const right = { x: xr, y: yr, mode: "markers", type: "scatter", marker: { color: TEAL, size: 5, opacity: 0.7 } };
  Plotly.react("sceneTrend", [left, right], sceneLayout({
    xaxis: { title: tr("年齡", "age"), range: [44, 86] },
    yaxis: { title: tr("結果", "outcome") },
    shapes: [
      { type: "rect", x0: 53, x1: 77, y0: 0, y1: 1, yref: "paper", fillcolor: AMBER, opacity: 0.1, line: { width: 0 } },
      { type: "line", x0: 65, x1: 65, y0: 0, y1: 1, yref: "paper", line: { color: INK, width: 1.5, dash: "dot" } },
    ],
    annotations: [{ x: 65, y: 1, yref: "paper", text: tr("65 歲斷點", "cutoff 65"), showarrow: false, font: { size: 10, color: INK }, yshift: 6 }],
  }), SCENE_CFG);
}

// scene 5 (RDD remedy 2): swimmer plot — events vs censoring, frail censored earlier
function drawSceneCensor() {
  if (!document.getElementById("sceneCensor")) return;
  const rng = mulberry32(505);
  const lines = [], eventX = [], eventY = [], censX = [], censY = [], eventC = [], censC = [];
  const n = 14;
  for (let i = 0; i < n; i++) {
    const frail = rng() < 0.5;
    const col = frail ? AMBER : "#9aa6b2";
    const eventTime = (frail ? 2 + rng() * 5 : 4 + rng() * 6);
    const censTime = (frail ? 2 + rng() * 3 : 5 + rng() * 5); // frail censored earlier
    const observed = Math.min(eventTime, censTime);
    const isEvent = eventTime <= censTime;
    lines.push({ x: [0, observed], y: [i, i], mode: "lines", type: "scatter", line: { color: col, width: 3 }, hoverinfo: "skip" });
    if (isEvent) { eventX.push(observed); eventY.push(i); eventC.push(col); }
    else { censX.push(observed); censY.push(i); censC.push(col); }
  }
  const events = { x: eventX, y: eventY, mode: "markers", type: "scatter", marker: { color: RED, size: 9, symbol: "circle" }, name: "event" };
  const cens = { x: censX, y: censY, mode: "markers", type: "scatter", marker: { color: censC, size: 11, symbol: "line-ns-open", line: { width: 2 } }, name: "censored" };
  Plotly.react("sceneCensor", lines.concat([events, cens]), sceneLayout({
    xaxis: { title: tr("追蹤時間", "follow-up time"), range: [0, 11], zeroline: false },
    yaxis: { showticklabels: false, range: [-1, n], title: tr("每條線＝一個人", "each line = a person") },
    annotations: [
      { x: 10.6, y: n - 1, text: "● " + tr("事件", "event"), showarrow: false, font: { size: 10, color: RED }, xanchor: "right" },
      { x: 10.6, y: n - 2.4, text: "| " + tr("設限", "censored"), showarrow: false, font: { size: 10, color: INK }, xanchor: "right" },
    ],
  }), SCENE_CFG);
}

// rddplay ② intro: what censored time-to-event data looks like (swimmer plot).
// Each row is a person's follow-up; ● = the event happened, | = censored
// (follow-up ended event-free). Frail people (amber) tend to be censored earlier.
function drawSceneSurvIntro() {
  if (!document.getElementById("sceneSurvIntro")) return;
  const rng = mulberry32(606);
  const traces = [], evX = [], evY = [], cX = [], cY = [], cCol = [];
  const n = 16;
  for (let i = 0; i < n; i++) {
    const frail = rng() < 0.5;
    const col = frail ? AMBER : "#7e8a98";
    const eventTime = frail ? 2 + rng() * 5 : 4.5 + rng() * 6;
    const censTime = frail ? 2 + rng() * 3.5 : 5 + rng() * 5.5;  // frail lost earlier
    const observed = Math.min(eventTime, censTime, 11);
    const isEvent = eventTime <= censTime && eventTime <= 11;
    traces.push({ x: [0, observed], y: [i, i], mode: "lines", type: "scatter",
      line: { color: col, width: 3 }, hoverinfo: "skip" });
    if (isEvent) { evX.push(observed); evY.push(i); }
    else { cX.push(observed); cY.push(i); cCol.push(col); }
  }
  const events = { x: evX, y: evY, mode: "markers", type: "scatter",
    marker: { color: RED, size: 10, symbol: "circle" } };
  const cens = { x: cX, y: cY, mode: "markers", type: "scatter",
    marker: { color: cCol, size: 13, symbol: "line-ns-open", line: { width: 2.5 } } };
  Plotly.react("sceneSurvIntro", traces.concat([events, cens]), sceneLayout({
    xaxis: { title: tr("追蹤時間（年）", "follow-up time (years)"), range: [0, 11.6], zeroline: false },
    yaxis: { showticklabels: false, range: [-1, n], title: tr("每條線＝一個人", "each line = a person") },
    annotations: [
      { x: 11.4, y: n - 1, text: "● " + tr("事件發生", "event"), showarrow: false, font: { size: 10, color: RED }, xanchor: "right" },
      { x: 11.4, y: n - 2.5, text: "| " + tr("被設限", "censored"), showarrow: false, font: { size: 10, color: INK }, xanchor: "right" },
    ],
  }), SCENE_CFG);
}

function drawIvScenes() { drawSceneWeak(); drawSceneBend(); drawSceneOverfit(); }
function drawRddScenes() { drawSceneTrend(); drawSceneCensor(); }

let mlReady = false;
const kSlider = document.getElementById("kSlider");
const psSlider = document.getElementById("psSlider");
let synTimer = null;

function initMl() {
  if (mlReady) return;
  mlReady = true;
  drawIvScenes();
  refreshSynthesis();
}

function scheduleSynthesis() {
  document.getElementById("kVal").textContent = kSlider.value;
  document.getElementById("psVal").textContent = Number(psSlider.value).toFixed(1) + "%";
  clearTimeout(synTimer);
  synTimer = setTimeout(refreshSynthesis, 150);
}
kSlider.addEventListener("input", scheduleSynthesis);
psSlider.addEventListener("input", scheduleSynthesis);

async function refreshSynthesis() {
  const k = Number(kSlider.value);
  const ps = Number(psSlider.value) / 100;
  let d;
  try {
    d = await getJSON(`${API}/api/ml_synthesis?k_candidates=${k}&per_strength=${ps}`);
  } catch (e) { return; }

  document.getElementById("synSingleF").textContent = fmt(d.max_single_F, 1);
  const mlivF = d.mliv_crossfit.f_stat;
  const mEl = document.getElementById("synMlivF");
  mEl.textContent = fmt(mlivF, 1);
  mEl.style.color = mlivF >= 10 ? TEAL : AMBER;
  const est = d.mliv_crossfit.estimate, ci = d.mliv_crossfit.ci;
  document.getElementById("synEst").textContent = fmt(est, 2);
  document.querySelector("#synEst").parentElement.querySelector(".stat-foot").textContent =
    tr(`誤差範圍 ${fmt(ci[0], 1)} ~ ${fmt(ci[1], 1)}（真值 1.80）`,
       `margin ${fmt(ci[0], 1)} ~ ${fmt(ci[1], 1)} (truth 1.80)`);

  const labels = d.per_candidate_F.map((_, i) => tr(`外力${i + 1}`, `force ${i + 1}`)).concat([tr("AI 合成", "AI synthesis")]);
  const yvals = d.per_candidate_F.concat([mlivF]);
  const colors = d.per_candidate_F.map(() => "#9ca3af").concat([TEAL]);
  Plotly.react("synChart", [{
    x: labels, y: yvals, type: "bar", marker: { color: colors },
    text: yvals.map((v) => fmt(v, 0)), textposition: "outside",
  }], {
    margin: { t: 24, r: 20, b: 50, l: 50 },
    yaxis: { title: tr("外力強度（F 統計量）", "Force strength (F statistic)") },
    shapes: [{ type: "line", x0: -0.5, x1: labels.length - 0.5, y0: 10, y1: 10,
               line: { color: RED, dash: "dash", width: 1.5 } }],
    annotations: [{ x: 0, y: 10, text: tr("及格線 10", "pass line 10"), showarrow: false, font: { color: RED, size: 11 }, yshift: 10, xanchor: "left" }],
  }, { displayModeBar: false, responsive: true });
}

document.getElementById("runNonlinear").addEventListener("click", async () => {
  let d;
  try { d = await getJSON(`${API}/api/ml_nonlinear`); }
  catch (e) { alert(tr("執行失敗：", "Run failed: ") + e.message); return; }
  state.nlData = d;
  renderNonlinear(d);
});

function renderNonlinear(d) {
  document.getElementById("nlOut").classList.remove("hidden");
  const linF = d.linear_first_stage_F, flexF = d.flexible_first_stage_F;
  document.getElementById("nlLinF").textContent = fmt(linF, 1);
  document.getElementById("nlLinNote").textContent = linF < 10
    ? tr("抓不到 ⚠（F<10）", "can't catch it ⚠ (F<10)") : tr("夠力", "strong enough");
  document.getElementById("nlLinNote").style.color = linF < 10 ? RED : TEAL;
  document.getElementById("nlFlexF").textContent = fmt(flexF, 1);
  document.getElementById("nlFlexNote").textContent = flexF >= 10
    ? tr("抓到了 ✓（F>10）", "caught it ✓ (F>10)") : tr("仍偏弱", "still weak");
  document.getElementById("nlFlexNote").style.color = flexF >= 10 ? TEAL : AMBER;
  document.getElementById("nlFlexEst").textContent = fmt(d.flexible.estimate, 2);

  Plotly.react("nlChart", [
    { x: d.curve.dist, y: d.curve.line, type: "scatter", mode: "lines",
      name: tr("硬用直線", "forced straight line"), line: { color: "#3b82f6", width: 3 } },
    { x: d.curve.dist, y: d.curve.flex, type: "scatter", mode: "lines",
      name: tr("讓它可以彎", "let it bend"), line: { color: TEAL, width: 3 } },
  ], {
    margin: { t: 24, r: 20, b: 45, l: 55 },
    xaxis: { title: tr("離快打巡迴車的距離（公里）", "Distance to the mobile vaccination van (km)") },
    yaxis: { title: tr("去打針的機率", "Probability of getting vaccinated") },
    legend: { orientation: "h", y: 1.12 },
  }, { displayModeBar: false, responsive: true });
}

document.getElementById("runMlCompare").addEventListener("click", async () => {
  await runMlCompare();
});

async function runMlCompare() {
  let d;
  try { d = await getJSON(`${API}/api/ml_compare?lang=${lang()}`); }
  catch (e) { alert(tr("執行失敗：", "Run failed: ") + e.message); return; }
  state.cmpDone = true;
  document.getElementById("mlCompareOut").classList.remove("hidden");

  const labels = d.bars.map((b) => b.label);
  const vals = d.bars.map((b) => b.estimate);
  const colors = d.bars.map((b) => STATUS_COLOR[b.status] || INK);
  const errPlus = d.bars.map((b) => (b.ci ? b.ci[1] - b.estimate : 0));
  const errMinus = d.bars.map((b) => (b.ci ? b.estimate - b.ci[0] : 0));
  Plotly.react("mlCompareChart", [{
    x: labels, y: vals, type: "bar", marker: { color: colors },
    error_y: { type: "data", symmetric: false, array: errPlus, arrayminus: errMinus, color: INK, thickness: 1.5, width: 8 },
    text: vals.map((v) => fmt(v, 2)), textposition: "outside",
  }], {
    margin: { t: 30, r: 20, b: 70, l: 50 },
    yaxis: { title: tr("估出的疫苗效果", "Estimated vaccine effect") },
    shapes: [{ type: "line", x0: -0.5, x1: labels.length - 0.5, y0: d.true_late, y1: d.true_late,
               line: { color: GREEN, dash: "dash", width: 2 } }],
    annotations: [{ x: labels.length - 1, y: d.true_late, text: tr("真值 1.80", "truth 1.80"), showarrow: false, font: { color: GREEN }, yshift: 12 }],
  }, { displayModeBar: false, responsive: true });

  document.getElementById("mlCompareCards").innerHTML = d.bars.map((b) => {
    const fTxt = b.f === null || b.f === undefined ? "" : `<span>${tr("工具強度 F=", "strength F=")}${fmt(b.f, 1)}</span>`;
    return `<div class="rc"><h3>${b.label}</h3><div class="big">${fmt(b.estimate, 2)}</div>
      <p>${b.note}${fTxt ? "　" + fTxt : ""}</p></div>`;
  }).join("");
}

document.getElementById("runForbidden").addEventListener("click", async (ev) => {
  const btn = ev.target;
  const old = btn.dataset.zh !== undefined ? (lang() === "en" ? btn.dataset.en : btn.dataset.zh) : btn.textContent;
  btn.disabled = true; btn.textContent = tr("訓練模型中…（約幾秒）", "Training model… (a few seconds)");
  let d;
  try { d = await getJSON(`${API}/api/ml_forbidden`); }
  catch (e) { alert(tr("執行失敗：", "Run failed: ") + e.message); return; }
  finally { btn.disabled = false; btn.textContent = old; }
  state.fbData = d;
  renderForbidden(d);
});

function renderForbidden(d) {
  document.getElementById("fbOut").classList.remove("hidden");
  const trap = d.in_sample, cf = d.cross_fit;
  document.getElementById("fbNaive").textContent = fmt(d.naive, 2);
  document.getElementById("fbTrap").textContent = fmt(trap.estimate, 2);
  document.getElementById("fbTrap").style.color = AMBER;
  document.getElementById("fbTrapFoot").textContent =
    tr(`黏在 naive ⚠（看似 F=${fmt(trap.f_stat, 0)}，假的）`,
       `stuck on naive ⚠ (looks like F=${fmt(trap.f_stat, 0)}, but fake)`);
  document.getElementById("fbCf").textContent = fmt(cf.estimate, 2);
  document.getElementById("fbCf").style.color = TEAL;
  document.getElementById("fbCfFoot").textContent =
    tr(`拉回真值 ✓（F=${fmt(cf.f_stat, 0)}）`, `pulled back to truth ✓ (F=${fmt(cf.f_stat, 0)})`);

  const labels = [tr("未調整", "Naive"), tr("AI 偷看版", "AI peeking"), tr("AI 交叉擬合版", "AI cross-fit")];
  const vals = [d.naive, trap.estimate, cf.estimate];
  const colors = [RED, AMBER, TEAL];
  const errPlus = [0, trap.ci[1] - trap.estimate, cf.ci[1] - cf.estimate];
  const errMinus = [0, trap.estimate - trap.ci[0], cf.estimate - cf.ci[0]];
  Plotly.react("fbChart", [{
    x: labels, y: vals, type: "bar", marker: { color: colors },
    error_y: { type: "data", symmetric: false, array: errPlus, arrayminus: errMinus, color: INK, thickness: 1.5, width: 10 },
    text: vals.map((v) => fmt(v, 2)), textposition: "outside",
  }], {
    margin: { t: 30, r: 20, b: 50, l: 50 },
    yaxis: { title: tr("估出的疫苗效果", "Estimated vaccine effect"), range: [0, 3] },
    shapes: [{ type: "line", x0: -0.5, x1: 2.5, y0: d.true_late, y1: d.true_late,
               line: { color: GREEN, dash: "dash", width: 2 } }],
    annotations: [{ x: 2, y: d.true_late, text: tr("真值 1.80", "truth 1.80"), showarrow: false, font: { color: GREEN }, yshift: 12 }],
  }, { displayModeBar: false, responsive: true });
}

// ======================================================================
// 6. Regression Discontinuity — teaching + interactive (bandwidth slider)
// ======================================================================
const PURPLE = "#7c3aed", SLATE = "#64748b";
let rddReady = false, rddAssumeReady = false, rddBwTimer = null;
const rddBwSlider = document.getElementById("rddBwSlider");

function initRdd() {
  if (rddReady) return;
  rddReady = true;
  drawSceneSurvIntro();   // "what does censored time-to-event data look like"
  refreshRdd();
  // NOTE: the survival fit (IPCW/Cox/AFT) is heavy (~3s) and, on the
  // browser-only Pyodide build, runs synchronously and freezes the UI.
  // So it is gated behind an explicit button instead of auto-running.
}
function scheduleRdd() {
  document.getElementById("rddBwVal").textContent = Number(rddBwSlider.value).toFixed(1);
  clearTimeout(rddBwTimer);
  rddBwTimer = setTimeout(refreshRdd, 130);
}
rddBwSlider.addEventListener("input", scheduleRdd);

async function refreshRdd() {
  const bw = Number(rddBwSlider.value);
  let i, a;
  try {
    i = await getJSON(`${API}/api/rdd_interactive?bandwidth=${bw}&lang=${lang()}`);
    a = await postJSON(`${API}/api/rdd_analyze`, { source: "example_rdd", bandwidth: bw, lang: lang() });
  } catch (e) { return; }

  document.getElementById("rddTakeup").textContent = fmt(i.takeup_jump * 100, 0) + "%";
  document.getElementById("rddSharp").textContent = fmt(i.sharp, 2);
  document.getElementById("rddSharpCi").textContent =
    `${fmt(i.sharp_ci[0], 2)} ~ ${fmt(i.sharp_ci[1], 2)}`;
  const fuzzyEl = document.getElementById("rddFuzzy");
  fuzzyEl.textContent = fmt(i.fuzzy, 2);
  fuzzyEl.style.color = Math.abs(i.fuzzy - 1.8) < 0.4 ? TEAL : AMBER;

  renderRddPlotInto("rddPlot", a.plot);
  renderRddBwInto("rddBwChart", a.bandwidth_curve);
}

function renderRddPlotInto(elId, plot) {
  const c = plot.cutoff;
  const traces = [
    { x: plot.left.bx, y: plot.left.by, type: "scatter", mode: "markers",
      name: tr("斷點下方", "below cutoff"), marker: { color: SLATE, size: 7 } },
    { x: plot.right.bx, y: plot.right.by, type: "scatter", mode: "markers",
      name: tr("斷點上方", "above cutoff"), marker: { color: PURPLE, size: 7 } },
  ];
  if (plot.fit.left) traces.push({ x: plot.fit.left.x, y: plot.fit.left.y, type: "scatter",
    mode: "lines", name: tr("左側配適", "left fit"), line: { color: SLATE, width: 3 }, showlegend: false });
  if (plot.fit.right) traces.push({ x: plot.fit.right.x, y: plot.fit.right.y, type: "scatter",
    mode: "lines", name: tr("右側配適", "right fit"), line: { color: PURPLE, width: 3 }, showlegend: false });

  Plotly.react(elId, traces, {
    margin: { t: 24, r: 20, b: 45, l: 55 },
    xaxis: { title: tr("跑分變數", "Running variable") },
    yaxis: { title: tr("結果", "Outcome") },
    legend: { orientation: "h", y: 1.14 },
    shapes: [{ type: "line", x0: c, x1: c, yref: "paper", y0: 0, y1: 1,
               line: { color: RED, dash: "dash", width: 1.5 } }],
    annotations: [{ x: c, yref: "paper", y: 1, text: tr(`斷點 ${c}`, `cutoff ${c}`),
               showarrow: false, font: { color: RED, size: 11 }, yshift: 10 }],
  }, { displayModeBar: false, responsive: true });
}

function renderRddBwInto(elId, bw) {
  Plotly.react(elId, [
    { x: bw.h.concat(bw.h.slice().reverse()),
      y: bw.hi.concat(bw.lo.slice().reverse()),
      fill: "toself", fillcolor: "rgba(124,58,237,0.12)", line: { color: "transparent" },
      type: "scatter", mode: "lines", showlegend: false, hoverinfo: "skip" },
    { x: bw.h, y: bw.estimate, type: "scatter", mode: "lines+markers",
      line: { color: PURPLE, width: 3 }, marker: { size: 6 }, name: tr("模糊 RD 估計", "fuzzy RD estimate") },
  ], {
    margin: { t: 24, r: 20, b: 45, l: 55 },
    xaxis: { title: tr("觀察視窗（頻寬，年）", "Observation window (bandwidth, years)") },
    yaxis: { title: tr("模糊 RD 估計", "Fuzzy RD estimate") },
    showlegend: false,
    shapes: [{ type: "line", x0: bw.h[0], x1: bw.h[bw.h.length - 1], y0: 1.8, y1: 1.8,
               line: { color: GREEN, dash: "dash", width: 2 } }],
    annotations: [{ x: bw.h[bw.h.length - 1], y: 1.8, text: tr("真值 1.80", "truth 1.80"),
               showarrow: false, font: { color: GREEN }, yshift: 12, xanchor: "right" }],
  }, { displayModeBar: false, responsive: true });
}

const runRddSurvBtn = document.getElementById("runRddSurv");
if (runRddSurvBtn) {
  runRddSurvBtn.addEventListener("click", async () => {
    runRddSurvBtn.disabled = true;
    const label = runRddSurvBtn.textContent;
    runRddSurvBtn.textContent = tr("計算中…（約 3 秒）", "Computing… (~3 sec)");
    // let the button repaint before the synchronous Pyodide work blocks the thread
    await new Promise((r) => setTimeout(r, 30));
    await runRddSurvival();
    runRddSurvBtn.textContent = tr("重新計算設限校正", "Re-run censoring correction");
    runRddSurvBtn.disabled = false;
  });
}

async function runRddSurvival() {
  let s;
  try { s = await postJSON(`${API}/api/rdd_survival`, { source: "example_rdd", lang: lang() }); }
  catch (e) { return; }
  state.rddSurv = s;
  renderRddSurvival(s);
}
function renderRddSurvival(s) {
  const U = tr("Δlog（事件時間）", "Δlog(event time)");
  const cards = [];
  // baseline: ignoring censoring (biased)
  cards.push({
    t: tr("未處理設限（有偏）", "No censoring fix (biased)"),
    v: s.naive.estimate,
    p: tr("直接對 log（觀察時間）做 RD，被提早設限者往下拉。",
          "Plain RD on log(observed time); dragged down by early-censored subjects."),
    hl: false,
  });
  // sharp design, one card per outcome-regression method
  (s.sharp.methods || []).forEach((m, i) => {
    cards.push({
      t: tr("銳利 · ", "Sharp · ") + m.label,
      v: m.estimate,
      p: i === 0
        ? tr("跨越資格門檻對「log 事件時間」的跳躍（類似 ITT）。",
              "Jump in log event-time from crossing eligibility (ITT-like).")
        : tr("雙重穩健版：多帶結果模型校正設限。",
              "Doubly-robust: adds an outcome model on top of IPCW."),
      hl: false,
    });
  });
  // fuzzy design, primary (IPCW) — the LATE for compliers at the cutoff
  const fz = (s.fuzzy.methods && s.fuzzy.methods[0]) || { label: "IPCW", estimate: s.fuzzy.estimate };
  cards.push({
    t: tr("模糊 · ", "Fuzzy · ") + fz.label,
    v: fz.estimate,
    p: tr("斷點附近實際接種者的效果（complier 的 LATE）。",
          "Effect for those actually vaccinated near the cutoff (complier LATE)."),
    hl: true,
  });
  document.getElementById("rddSurvCards").innerHTML = cards.map(c =>
    `<div class="rc ${c.hl ? "highlight" : ""}"><h3>${c.t}</h3>` +
    `<div class="big">${fmt(c.v, 2)}</div>` +
    `<p class="caption">${U}</p><p>${c.p}</p></div>`
  ).join("");
}

// ======================================================================
// RDD ③ data analysis (load example / upload, map columns, run RDD)
// ======================================================================
const rddState = { source: null, columns: [], req: null };
let rddAnalyzeReady = false;

function initRddAnalyze() {
  if (rddAnalyzeReady) return;
  rddAnalyzeReady = true;
  document.getElementById("useRddExample").click();   // auto-load the demo
}

function rddFillSelects(cols) {
  const opts = cols.map((c) => `<option value="${c}">${c}</option>`).join("");
  const none = `<option value="">—</option>`;
  ["rddSelX", "rddSelY", "rddSelD", "rddSelCov"].forEach((id) => {
    document.getElementById(id).innerHTML = opts;
  });
  ["rddSelT", "rddSelE"].forEach((id) => {   // optional survival columns
    document.getElementById(id).innerHTML = none + opts;
  });
  document.getElementById("rddColMap").classList.remove("hidden");
}
function rddApplyDefaults(d) {
  if (!d) return;
  const set = (id, v) => { const el = document.getElementById(id); if (v != null) el.value = v; };
  set("rddSelX", d.running); set("rddSelY", d.outcome); set("rddSelD", d.treatment);
  set("rddSelC", d.cutoff); set("rddSelT", d.time); set("rddSelE", d.event);
  const cov = document.getElementById("rddSelCov");
  if (d.covariates) [...cov.options].forEach((o) => { o.selected = d.covariates.includes(o.value); });
}

document.getElementById("useRddExample").addEventListener("click", async () => {
  const st = document.getElementById("rddDataStatus");
  try {
    const d = await getJSON(`${API}/api/rdd_example`);
    rddState.source = "example_rdd"; rddState.columns = d.columns;
    st.textContent = tr(`已載入內建 65 歲範例（${d.n} 筆，合成虛構）`,
                        `Loaded built-in age-65 example (${d.n} rows, synthetic & fictional)`);
    rddFillSelects(d.columns); rddApplyDefaults(d.defaults);
    runRddAnalyze();
  } catch (e) { st.textContent = tr("載入失敗：", "Load failed: ") + e.message; }
});

document.getElementById("rddFileInput").addEventListener("change", async (ev) => {
  const file = ev.target.files[0];
  if (!file) return;
  const fd = new FormData(); fd.append("file", file);
  const st = document.getElementById("rddDataStatus");
  st.textContent = tr("上傳中…", "Uploading…");
  try {
    const r = await fetch(`${API}/api/upload`, { method: "POST", body: fd });
    if (!r.ok) throw new Error((await r.json()).detail);
    const d = await r.json();
    rddState.source = d.token; rddState.columns = d.columns;
    st.textContent = tr(`已上傳「${file.name}」（${d.n} 筆）`, `Uploaded "${file.name}" (${d.n} rows)`);
    rddFillSelects(d.columns);
  } catch (e) { st.textContent = tr("上傳失敗：", "Upload failed: ") + e.message; }
});

function rddCurrentMapping() {
  const v = (id) => document.getElementById(id).value;
  return {
    source: rddState.source,
    running: v("rddSelX"), outcome: v("rddSelY"), treatment: v("rddSelD"),
    cutoff: Number(v("rddSelC")),
    time: v("rddSelT"), event: v("rddSelE"),
    covariates: [...document.getElementById("rddSelCov").selectedOptions].map((o) => o.value),
    lang: lang(),
  };
}

document.getElementById("runRddAnalyze").addEventListener("click", runRddAnalyze);

async function runRddAnalyze() {
  const req = rddCurrentMapping();
  if (!req.source) return;
  rddState.req = req;
  try {
    const a = await postJSON(`${API}/api/rdd_analyze`, req);
    renderRddAnalyze(a);
    runRddAssumptions(req);   // keep the ④ dashboard in sync
  } catch (e) { alert(tr("分析失敗：", "Analysis failed: ") + e.message); return; }

  // optional survival RDD when both time + event columns are chosen.
  // The IPCW/doubly-robust fit is ~1.4 s of *synchronous* Pyodide compute,
  // which would freeze the whole UI the moment this tab opens. So we only
  // reveal the block + a button here, and compute on the user's click.
  const block = document.getElementById("rddSurvBlock");
  if (req.time && req.event) {
    block.classList.remove("hidden");
    state.rddAnalyzeSurv = null;
    document.getElementById("rddAnalyzeSurv").innerHTML = "";
    const b = document.getElementById("runRddAnalyzeSurv");
    if (b) {
      b.classList.remove("hidden");
      b.disabled = false;
      b.textContent = tr("跑設限校正估計（約 1.5 秒）", "Run the censoring-corrected estimate (~1.5 sec)");
    }
  } else {
    block.classList.add("hidden");
  }
}

// Button-gated survival fit for the analysis tab (heavy synchronous Pyodide).
document.getElementById("runRddAnalyzeSurv").addEventListener("click", async () => {
  const req = rddState.req;
  if (!req || !req.time || !req.event) return;
  const b = document.getElementById("runRddAnalyzeSurv");
  b.disabled = true;
  b.textContent = tr("計算中…（約 1.5 秒）", "Computing… (~1.5 sec)");
  await new Promise((r) => setTimeout(r, 30));   // let the button repaint first
  try {
    const s = await postJSON(`${API}/api/rdd_survival`, { ...req, lang: lang() });
    state.rddAnalyzeSurv = s;
    renderRddAnalyzeSurv(s);
    b.textContent = tr("重新計算設限校正", "Re-run censoring correction");
  } catch (e) {
    b.textContent = tr("計算失敗，再試一次", "Failed — try again");
  } finally {
    b.disabled = false;
  }
});

function renderRddAnalyze(a) {
  document.getElementById("rddAnalyzeOut").classList.remove("hidden");
  const cards = [
    [tr("接種率跳幅（第一階段）", "Take-up jump (first stage)"), a.takeup.estimate, a.takeup.interpretation, false],
    [tr("天真差異（有偏）", "Naive difference (biased)"), a.naive_difference, tr("直接比較有／無處置者，被干擾因子汙染。", "Direct treated-vs-untreated comparison, confounded."), false],
    [tr("銳利 RD（資格效果）", "Sharp RD (eligibility)"), a.sharp.estimate, a.sharp.interpretation, false],
    [tr("模糊 RD（斷點順從者）", "Fuzzy RD (compliers)"), a.fuzzy ? a.fuzzy.estimate : null, a.fuzzy ? a.fuzzy.interpretation : "", true],
  ];
  document.getElementById("rddAnalyzeCards").innerHTML = cards.map(([t, v, desc, hl]) =>
    `<div class="rc ${hl ? "highlight" : ""}"><h3>${t}</h3><div class="big">${fmt(v, hl ? 3 : 2)}</div><p>${desc}</p></div>`
  ).join("");
  if (a.plot) renderRddPlotInto("rddAnalyzePlot", a.plot);
  if (a.bandwidth_curve) renderRddBwInto("rddAnalyzeBw", a.bandwidth_curve);
}

function renderRddAnalyzeSurv(s) {
  const U = tr("Δlog（事件時間）", "Δlog(event time)");
  const rows = [];
  rows.push({ t: tr("未處理設限（有偏）", "No censoring fix (biased)"), v: s.naive.estimate, hl: false });
  (s.sharp.methods || []).forEach((m) => rows.push({ t: tr("銳利 · ", "Sharp · ") + m.label, v: m.estimate, hl: false }));
  const fz = (s.fuzzy.methods && s.fuzzy.methods[0]) || { label: "IPCW", estimate: s.fuzzy.estimate };
  rows.push({ t: tr("模糊 · ", "Fuzzy · ") + fz.label, v: fz.estimate, hl: true });
  document.getElementById("rddAnalyzeSurv").innerHTML = rows.map((c) =>
    `<div class="rc ${c.hl ? "highlight" : ""}"><h3>${c.t}</h3><div class="big">${fmt(c.v, 2)}</div><p class="caption">${U}</p></div>`
  ).join("");
}

// ======================================================================
// RDD ④ assumptions dashboard (R1–R5)
// ======================================================================
function initRddAssume() {
  if (rddAssumeReady) return;
  rddAssumeReady = true;
  runRddAssumptions(rddState.req || { source: "example_rdd", lang: lang() });
}
async function runRddAssumptions(req) {
  const body = req ? { ...req, lang: lang() } : { source: "example_rdd", lang: lang() };
  let out;
  try { out = await postJSON(`${API}/api/rdd_assumptions`, body); }
  catch (e) { return; }
  state.rddDash = out;
  renderRddAssumptions(out);
}
function worstStatus(checks) {
  const rank = { red: 3, amber: 2, info: 1, green: 0 };
  return checks.reduce((w, c) => (rank[c.status] > rank[w] ? c.status : w), "green");
}
function renderRddAssumptions(out) {
  document.getElementById("rddAssumeHint").classList.add("hidden");
  const ov = document.getElementById("rddOverall");
  const worst = worstStatus(out.checks);
  const head = {
    green: tr("各項佐證都通過，這個 RDD 設計看起來可信。", "All supporting checks pass — this RDD design looks credible."),
    amber: tr("有項目需要留意，請展開卡片細看。", "Some items need attention — expand the cards to see."),
    red: tr("有項目不符，RDD 結果要保守看待。", "Some items fail — interpret the RDD with caution."),
    info: tr("關鍵假設需靠領域知識判斷，請看各卡片說明。", "The key assumption needs domain judgement — see each card."),
  }[worst];
  ov.classList.remove("hidden");
  ov.className = `overall st-${worst}`;
  ov.style.background = "#fff";
  ov.innerHTML = `<span class="dot bg-${worst}"></span> ${head}`;

  document.getElementById("rddAssumeCards").innerHTML = out.checks.map((c) => {
    const metrics = c.metrics.map((m) =>
      `<li>${m.name}<b>${m.value === null ? "–" : m.value}</b><span>${m.note || ""}</span></li>`).join("");
    return `<div class="acard st-${c.status}">
      <h3><span class="dot bg-${c.status}"></span>${c.title}
        <span class="badge bg-${c.status}">${statusText(c.status)}</span></h3>
      <p class="headline"><b>${c.headline}</b></p>
      <p class="plain">${c.plain}</p>
      <ul class="metrics">${metrics}</ul>
      <details class="term"><summary>${tr("看專有名詞解釋", "Show term explanation")}</summary><p>${c.term}</p></details>
    </div>`;
  }).join("");
}

// ======================================================================
// RDD ⑤ Boost with AI — DML window-robustness + flexible-ML DR survival
// ======================================================================
let rddMlReady = false, rddDmlTimer = null;
const rddDmlWindow = document.getElementById("rddDmlWindow");

function initRddMl() {
  if (rddMlReady) return;
  rddMlReady = true;
  drawRddScenes();
  refreshRddDml();
}
function scheduleRddDml() {
  document.getElementById("rddDmlWinVal").textContent = Number(rddDmlWindow.value).toFixed(1);
  clearTimeout(rddDmlTimer);
  rddDmlTimer = setTimeout(refreshRddDml, 140);
}
rddDmlWindow.addEventListener("input", scheduleRddDml);

async function refreshRddDml() {
  const w = Number(rddDmlWindow.value);
  let d;
  try { d = await getJSON(`${API}/api/rdd_ml_bandwidth?window=${w}`); }
  catch (e) { return; }
  state.rddDml = d;

  const conv = d.conventional.estimate, dml = d.dml.estimate;
  const convEl = document.getElementById("rddDmlConv");
  convEl.textContent = fmt(conv, 2);
  convEl.style.color = AMBER;
  document.getElementById("rddDmlConvFoot").textContent =
    tr(`誤差 ${fmt(d.conventional.ci[0], 1)} ~ ${fmt(d.conventional.ci[1], 1)}`,
       `CI ${fmt(d.conventional.ci[0], 1)} ~ ${fmt(d.conventional.ci[1], 1)}`);
  const dmlEl = document.getElementById("rddDmlEst");
  dmlEl.textContent = fmt(dml, 2);
  dmlEl.style.color = Math.abs(dml - 1.8) < 0.4 ? TEAL : AMBER;
  document.getElementById("rddDmlGap").textContent = (conv >= 1.8 ? "+" : "") + fmt(conv - 1.8, 2);

  const c = d.curve;
  Plotly.react("rddDmlChart", [
    { x: c.window.concat(c.window.slice().reverse()),
      y: c.conv_hi.concat(c.conv_lo.slice().reverse()),
      fill: "toself", fillcolor: "rgba(245,158,11,0.10)", line: { color: "transparent" },
      type: "scatter", mode: "lines", showlegend: false, hoverinfo: "skip" },
    { x: c.window, y: c.conv, type: "scatter", mode: "lines+markers",
      name: tr("視窗內直接比較", "plain comparison"), line: { color: AMBER, width: 3 }, marker: { size: 6 } },
    { x: c.window.concat(c.window.slice().reverse()),
      y: c.dml_hi.concat(c.dml_lo.slice().reverse()),
      fill: "toself", fillcolor: "rgba(13,148,136,0.12)", line: { color: "transparent" },
      type: "scatter", mode: "lines", showlegend: false, hoverinfo: "skip" },
    { x: c.window, y: c.dml, type: "scatter", mode: "lines+markers",
      name: tr("DML（調整＋交叉擬合）", "DML (adjusted + cross-fit)"), line: { color: TEAL, width: 3 }, marker: { size: 6 } },
  ], {
    margin: { t: 24, r: 20, b: 45, l: 55 },
    xaxis: { title: tr("觀察視窗（半寬，年）", "Observation window (half-width, years)") },
    yaxis: { title: tr("估出的疫苗效果", "Estimated vaccine effect") },
    legend: { orientation: "h", y: 1.14 },
    shapes: [{ type: "line", x0: c.window[0], x1: c.window[c.window.length - 1], y0: 1.8, y1: 1.8,
               line: { color: GREEN, dash: "dash", width: 2 } }],
    annotations: [{ x: c.window[c.window.length - 1], y: 1.8, text: tr("真值 1.80", "truth 1.80"),
               showarrow: false, font: { color: GREEN }, yshift: 12, xanchor: "right" }],
  }, { displayModeBar: false, responsive: true });
}

document.getElementById("runRddSurvMl").addEventListener("click", async (ev) => {
  const btn = ev.target;
  const old = btn.dataset.zh !== undefined ? (lang() === "en" ? btn.dataset.en : btn.dataset.zh) : btn.textContent;
  btn.disabled = true; btn.textContent = tr("擬合模型中…（約幾秒）", "Fitting models… (a few seconds)");
  let d;
  try { d = await getJSON(`${API}/api/rdd_ml_survival?lang=${lang()}`); }
  catch (e) { alert(tr("執行失敗：", "Run failed: ") + e.message); return; }
  finally { btn.disabled = false; btn.textContent = old; }
  state.rddSurvMl = d;
  renderRddSurvMl(d);
});

function renderRddSurvMl(d) {
  document.getElementById("rddSurvMlOut").classList.remove("hidden");
  const labels = d.bars.map((b) => b.label);
  const vals = d.bars.map((b) => b.estimate);
  const colors = d.bars.map((b) => STATUS_COLOR[b.status] || INK);
  const errPlus = d.bars.map((b) => (b.ci ? b.ci[1] - b.estimate : 0));
  const errMinus = d.bars.map((b) => (b.ci ? b.estimate - b.ci[0] : 0));
  Plotly.react("rddSurvMlChart", [{
    x: labels, y: vals, type: "bar", marker: { color: colors },
    error_y: { type: "data", symmetric: false, array: errPlus, arrayminus: errMinus, color: INK, thickness: 1.5, width: 8 },
    text: vals.map((v) => fmt(v, 2)), textposition: "outside",
  }], {
    margin: { t: 30, r: 20, b: 70, l: 50 },
    yaxis: { title: tr("斷點處 Δlog（事件時間）", "Δlog(event time) at the cutoff") },
  }, { displayModeBar: false, responsive: true });

  document.getElementById("rddSurvMlCards").innerHTML = d.bars.map((b) =>
    `<div class="rc ${b.status === "good" ? "highlight" : ""}"><h3>${b.label}</h3>` +
    `<div class="big">${fmt(b.estimate, 2)}</div>` +
    `<p>${b.note}</p></div>`
  ).join("");
}

// ======================================================================
// 8. IV vs RDD — when to use which (comparison chart)
// ======================================================================
let chooseReady = false;

function initChoose() {
  if (chooseReady) return;
  chooseReady = true;
  drawChooseChart();
}
// Six methods, one vaccine question. Each method's truth is on a different scale
// (effect difference, odds ratio, rate ratio, level change…), so we plot every
// estimate ÷ its OWN truth: 1.0 = perfectly recovered. Amber = the naive comparison
// (biased, off 1.0); teal = the method's corrected estimate (back near 1.0).
// Representative values from this tool's verified demos.
function drawChooseChart() {
  if (!document.getElementById("chooseChart")) return;
  const M = [
    ["IV", 1.83, 1.00], ["RDD", 1.83, 1.00], ["DiD", 0.52, 1.00],
    ["TiT", 1.57, 1.08], ["ITS", 1.45, 1.00], ["PERR", 1.47, 1.06],
  ];
  const x = M.map((r) => r[0]);
  const naive = { x, y: M.map((r) => r[1]), type: "bar", name: tr("天真比較（被混淆帶偏）", "naive (confounded)"),
    marker: { color: AMBER }, text: M.map((r) => r[1].toFixed(2)), textposition: "outside" };
  const corr = { x, y: M.map((r) => r[2]), type: "bar", name: tr("該方法校正後", "method (corrected)"),
    marker: { color: TEAL }, text: M.map((r) => r[2].toFixed(2)), textposition: "outside" };
  Plotly.react("chooseChart", [naive, corr], sceneLayout({
    height: 340, barmode: "group", showlegend: true, legend: { orientation: "h", y: 1.12 },
    yaxis: { title: tr("估計 ÷ 各自真值（1.0＝命中）", "estimate ÷ own truth (1.0 = on target)"), range: [0, 2] },
    shapes: [{ type: "line", x0: -0.5, x1: 5.5, y0: 1, y1: 1, line: { color: GREEN, width: 2, dash: "dash" } }],
    annotations: [{ x: 5, y: 1, text: tr("真值＝1.0", "truth = 1.0"), showarrow: false,
      yshift: 10, font: { size: 10, color: GREEN } }],
  }), SCENE_CFG);
}

// ======================================================================
// Citation — JAMA text + BibTeX + downloadable RIS
// ======================================================================
const CITE = {
  authors: "Methodology Working Group, Population Health Data Center, National Cheng Kung University; Tsai DH-T, Lai EC-C.",
  publisher: "Population Health Data Center, National Cheng Kung University",
  titleZh: "工具變數 IV － 斷點回歸 RDD 線上工具",
  titleEn: "Instrumental Variables (IV) & Regression Discontinuity (RDD) — Online Teaching Tool",
  year: "2026",
  url: "https://danielhttsai.github.io/iv-rdd-tool/",
};
const MONTHS = ["January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"];

function accessDates() {
  const d = new Date();
  const y = d.getFullYear(), m = d.getMonth(), day = d.getDate();
  return {
    en: `${MONTHS[m]} ${day}, ${y}`,                                  // Accessed May 30, 2026
    zh: `${y}年${m + 1}月${day}日`,                                    // 2026年5月30日
    ris: `${y}/${String(m + 1).padStart(2, "0")}/${String(day).padStart(2, "0")}`, // 2026/05/30
  };
}

function citationText() {
  const a = accessDates();
  const title = lang() === "en" ? CITE.titleEn : CITE.titleZh;
  return lang() === "en"
    ? `${CITE.authors} ${title}. ${CITE.publisher}. Published ${CITE.year}. Accessed ${a.en}. ${CITE.url}`
    : `${CITE.authors} ${title}. ${CITE.publisher}. 發表於 ${CITE.year} 年。取用於 ${a.zh}。${CITE.url}`;
}

function bibtex() {
  const a = accessDates();
  return [
    "@misc{phdc-iv-rdd-tool-2026,",
    "  author       = {{Methodology Working Group, Population Health Data Center, National Cheng Kung University} and Tsai, DH-T and Lai, EC-C},",
    `  title        = {${CITE.titleEn}},`,
    `  year         = {${CITE.year}},`,
    `  publisher    = {${CITE.publisher}},`,
    `  howpublished = {\\url{${CITE.url}}},`,
    `  note         = {Accessed ${a.en}}`,
    "}",
  ].join("\n");
}

function risText() {
  const a = accessDates();
  return [
    "TY  - ELEC",
    "AU  - Methodology Working Group, Population Health Data Center, National Cheng Kung University",
    "AU  - Tsai, DH-T",
    "AU  - Lai, EC-C",
    `TI  - ${CITE.titleEn}`,
    `PY  - ${CITE.year}`,
    `PB  - ${CITE.publisher}`,
    `UR  - ${CITE.url}`,
    `Y2  - ${a.ris}`,
    "ER  - ",
    "",
  ].join("\r\n");
}

function renderCitation() {
  const el = document.getElementById("citeText");
  if (!el) return;
  const txt = citationText();
  // linkify the trailing URL
  el.innerHTML = txt.replace(CITE.url, `<a href="${CITE.url}" target="_blank" rel="noopener">${CITE.url}</a>`);
}

async function flash(btn, msg) {
  const cur = btn.textContent;
  btn.textContent = msg;
  setTimeout(() => { btn.textContent = cur; }, 1400);
}
async function copyText(text, btn) {
  try {
    await navigator.clipboard.writeText(text);
    flash(btn, tr("已複製 ✓", "Copied ✓"));
  } catch (e) {
    const ta = document.createElement("textarea");
    ta.value = text; document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); flash(btn, tr("已複製 ✓", "Copied ✓")); }
    catch (e2) { flash(btn, tr("複製失敗", "Copy failed")); }
    document.body.removeChild(ta);
  }
}

document.getElementById("copyCite").addEventListener("click", (e) => copyText(citationText(), e.target));
document.getElementById("copyBib").addEventListener("click", (e) => copyText(bibtex(), e.target));
document.getElementById("dlRis").addEventListener("click", () => {
  const blob = new Blob([risText()], { type: "application/x-research-info-systems" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = "iv-rdd-tool.ris";
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
renderCitation();

// ======================================================================
// Difference-in-differences (DiD method) — tabs ①–⑤
// ======================================================================
const didState = { source: null, columns: [], req: null };
let didLearnReady = false, didPlayReady = false, didAnalyzeReady = false,
    didAssumeReady = false, didMlReady = false;

// ---- shared DiD chart helpers ----
function didTrendInto(elId, trend, t0) {
  if (!document.getElementById(elId)) return;
  const P = trend.periods;
  const treated = { x: P, y: trend.treated, mode: "lines+markers", type: "scatter",
    name: tr("介入組", "treated"), line: { color: TEAL, width: 3 }, marker: { size: 7 } };
  const control = { x: P, y: trend.control, mode: "lines+markers", type: "scatter",
    name: tr("對照組", "control"), line: { color: "#9aa6b2", width: 3 }, marker: { size: 7 } };
  Plotly.react(elId, [control, treated], sceneLayout({
    height: 320, showlegend: true, legend: { orientation: "h", y: 1.15 },
    xaxis: { title: tr("期別", "period"), dtick: 1 },
    yaxis: { title: tr("平均結果", "mean outcome") },
    shapes: [{ type: "line", x0: t0 - 0.5, x1: t0 - 0.5, y0: 0, y1: 1, yref: "paper",
      line: { color: INK, width: 1.5, dash: "dot" } }],
    annotations: [{ x: t0 - 0.5, y: 1, yref: "paper", yshift: 6,
      text: tr("政策上路", "policy on"), showarrow: false, font: { size: 10, color: INK } }],
  }), SCENE_CFG);
}

function didEventInto(elId, ev) {
  if (!document.getElementById(elId)) return;
  const err = ev.coef.map((c, i) => (ev.hi[i] - ev.lo[i]) / 2);
  const colors = ev.periods.map((q) => (q < ev.t0 ? "#9aa6b2" : TEAL));
  const dots = { x: ev.periods, y: ev.coef, mode: "markers", type: "scatter",
    marker: { color: colors, size: 9 },
    error_y: { type: "data", array: err, visible: true, color: "#c2cad4", thickness: 1.2 } };
  Plotly.react(elId, [dots], sceneLayout({
    height: 300,
    xaxis: { title: tr("期別（相對基期）", "period (vs base)"), dtick: 1 },
    yaxis: { title: tr("介入−對照 係數", "treated−control coef") },
    shapes: [
      { type: "line", x0: Math.min(...ev.periods), x1: Math.max(...ev.periods), y0: 0, y1: 0,
        line: { color: GREEN, width: 1.5, dash: "dash" } },
      { type: "line", x0: ev.t0 - 0.5, x1: ev.t0 - 0.5, y0: 0, y1: 1, yref: "paper",
        line: { color: INK, width: 1.2, dash: "dot" } },
    ],
  }), SCENE_CFG);
}

function didBarsInto(elId, bars) {
  if (!document.getElementById(elId)) return;
  const n = bars.values.length;
  const colors = bars.values.map((v, i) => (i === 0 ? GREEN : (i === n - 1 ? TEAL : AMBER)));
  Plotly.react(elId, [{
    x: bars.labels, y: bars.values, type: "bar", marker: { color: colors },
    text: bars.values.map((v) => v.toFixed(2)), textposition: "auto",
  }], sceneLayout({ height: 260, margin: { t: 20, r: 16, b: 40, l: 40 }, yaxis: { title: "" } }), SCENE_CFG);
}

// ---- ① learn ----
function initDidLearn() {
  if (didLearnReady) return;
  didLearnReady = true;
  drawSceneDidParallel();
}
function drawSceneDidParallel() {
  if (!document.getElementById("sceneDidParallel")) return;
  const P = [0, 1, 2, 3, 4, 5], t0 = 3, att = 3.0;
  const control = P.map((p) => 60 + 2 * p);
  const treatedCf = P.map((p) => 64 + 2 * p);                  // parallel counterfactual (+4 gap)
  const treated = P.map((p) => 64 + 2 * p + (p >= t0 ? att : 0));
  const cline = { x: P, y: control, mode: "lines+markers", type: "scatter",
    name: tr("對照組", "control"), line: { color: "#9aa6b2", width: 3 }, marker: { size: 7 } };
  const cf = { x: P, y: treatedCf, mode: "lines", type: "scatter",
    name: tr("介入組（假如沒政策）", "treated (no policy)"), line: { color: TEAL, width: 2, dash: "dash" } };
  const tline = { x: P, y: treated, mode: "lines+markers", type: "scatter",
    name: tr("介入組", "treated"), line: { color: TEAL, width: 3 }, marker: { size: 7 } };
  Plotly.react("sceneDidParallel", [cline, cf, tline], sceneLayout({
    height: 300, showlegend: true, legend: { orientation: "h", y: 1.18 },
    xaxis: { title: tr("期別", "period"), dtick: 1 },
    yaxis: { title: tr("平均結果", "mean outcome") },
    shapes: [{ type: "line", x0: t0 - 0.5, x1: t0 - 0.5, y0: 0, y1: 1, yref: "paper",
      line: { color: INK, width: 1.5, dash: "dot" } }],
    annotations: [{ x: t0 - 0.5, y: 1, yref: "paper", yshift: 6,
      text: tr("政策上路", "policy on"), showarrow: false, font: { size: 10, color: INK } }],
  }), SCENE_CFG);
}

// ---- ② interactive ----
const didViolSlider = document.getElementById("didViolSlider");
let didPlayTimer = null;
function initDidPlay() {
  if (didPlayReady) return;
  didPlayReady = true;
  refreshDidPlay();
}
function scheduleDidPlay() {
  document.getElementById("didViolVal").textContent = Number(didViolSlider.value).toFixed(1);
  clearTimeout(didPlayTimer);
  didPlayTimer = setTimeout(refreshDidPlay, 120);
}
if (didViolSlider) didViolSlider.addEventListener("input", scheduleDidPlay);

async function refreshDidPlay() {
  const v = didViolSlider ? Number(didViolSlider.value) : 0;
  let d;
  try { d = await getJSON(`${API}/api/did_interactive?violation=${v}&lang=${lang()}`); }
  catch (e) { return; }
  state.didPlay = d;
  document.getElementById("didEst").textContent = fmt(d.estimate, 2);
  document.getElementById("didNaive").textContent = fmt(d.naive, 2);
  const p = d.event_study.pre_max_p;
  const ok = p >= 0.05;
  const pre = document.getElementById("didPre");
  pre.textContent = ok ? tr("平行 ✓", "parallel ✓") : tr("分岔 ⚠", "diverging ⚠");
  pre.style.color = ok ? "var(--green)" : "var(--red)";
  document.getElementById("didPreFoot").textContent = tr(`前期檢定 p=${fmt(p, 3)}`, `pre-trend p=${fmt(p, 3)}`);
  didTrendInto("didTrendChart", d.trend, d.t0);
  didEventInto("didEventChart", d.event_study);
}

// ---- ③ analyze ----
function initDidAnalyze() {
  if (didAnalyzeReady) return;
  didAnalyzeReady = true;
  document.getElementById("useDidExample").click();
}
function didFillSelects(cols) {
  const opts = cols.map((c) => `<option value="${c}">${c}</option>`).join("");
  ["didSelUnit", "didSelPeriod", "didSelGroup", "didSelY", "didSelCov"].forEach((id) => {
    document.getElementById(id).innerHTML = opts;
  });
  document.getElementById("didColMap").classList.remove("hidden");
}
function didApplyDefaults(d) {
  if (!d) return;
  const set = (id, v) => { const el = document.getElementById(id); if (v != null) el.value = v; };
  set("didSelUnit", d.unit); set("didSelPeriod", d.period); set("didSelGroup", d.group);
  set("didSelY", d.outcome); set("didSelT0", d.t0);
  const cov = document.getElementById("didSelCov");
  if (d.covariates) [...cov.options].forEach((o) => { o.selected = d.covariates.includes(o.value); });
}
document.getElementById("useDidExample").addEventListener("click", async () => {
  const st = document.getElementById("didDataStatus");
  try {
    const d = await getJSON(`${API}/api/did_example`);
    didState.source = "example_did"; didState.columns = d.columns;
    st.textContent = tr(`已載入內建政策範例（${d.n} 列＝單位×期，合成虛構）`,
                        `Loaded built-in policy example (${d.n} rows = unit×period, synthetic)`);
    didFillSelects(d.columns); didApplyDefaults(d.defaults);
    runDidAnalyze();
  } catch (e) { st.textContent = tr("載入失敗：", "Load failed: ") + e.message; }
});
document.getElementById("didFileInput").addEventListener("change", async (ev) => {
  const file = ev.target.files[0]; if (!file) return;
  const fd = new FormData(); fd.append("file", file);
  const st = document.getElementById("didDataStatus"); st.textContent = tr("上傳中…", "Uploading…");
  try {
    const r = await fetch(`${API}/api/upload`, { method: "POST", body: fd });
    if (!r.ok) throw new Error((await r.json()).detail);
    const d = await r.json();
    didState.source = d.token; didState.columns = d.columns;
    st.textContent = tr(`已上傳「${file.name}」（${d.n} 列）`, `Uploaded "${file.name}" (${d.n} rows)`);
    didFillSelects(d.columns);
  } catch (e) { st.textContent = tr("上傳失敗：", "Upload failed: ") + e.message; }
});
function didCurrentMapping() {
  const v = (id) => document.getElementById(id).value;
  return {
    source: didState.source, unit: v("didSelUnit"), period: v("didSelPeriod"),
    group: v("didSelGroup"), outcome: v("didSelY"), t0: Number(v("didSelT0")),
    covariates: [...document.getElementById("didSelCov").selectedOptions].map((o) => o.value),
    lang: lang(),
  };
}
document.getElementById("runDidAnalyze").addEventListener("click", runDidAnalyze);
async function runDidAnalyze() {
  const req = didCurrentMapping();
  if (!req.source) return;
  didState.req = req;
  try {
    const a = await postJSON(`${API}/api/did_analyze`, req);
    renderDidAnalyze(a);
    runDidAssumptions(req);
    renderDidVariants();   // advanced (non-AI) variants shown under ③
  } catch (e) { alert(tr("分析失敗：", "Analysis failed: ") + e.message); }
}
// advanced VARIANTS (not AI) rendered in tab ③ — light, no sklearn
async function renderDidVariants() {
  let d;
  try { d = await getJSON(`${API}/api/did_variants?lang=${lang()}`); } catch (e) { return; }
  state.didVar = d;
  drawDidStagScene(); didBarsInto("didStagChart", d.staggered.bars);
  document.getElementById("didStagReading").textContent = d.staggered.reading;
  drawDidUnivScene(d.universal); didBarsInto("didUnivChart", d.universal.bars);
  document.getElementById("didUnivReading").textContent = d.universal.reading;
  drawDidSynth(d.synth);
  document.getElementById("didSynthReading").textContent = d.synth.reading;
}
function renderDidAnalyze(a) {
  document.getElementById("didAnalyzeOut").classList.remove("hidden");
  const cards = [
    [tr("DiD（政策效果，ATT）", "DiD (policy effect, ATT)"), a.did.estimate, a.did.interpretation, true],
    [tr("2×2 點估計", "2×2 point estimate"), a.two_by_two.did,
      tr("四格平均的（後−前）−（後−前）。", "(after−before)−(after−before) of the four cell means."), false],
    [tr("天真：只看後期差（有偏）", "Naive: post-only gap (biased)"), a.naive_difference,
      tr("被各組固定落差汙染。", "contaminated by fixed group differences."), false],
  ];
  document.getElementById("didAnalyzeCards").innerHTML = cards.map(([t, v, desc, hl]) =>
    `<div class="rc ${hl ? "highlight" : ""}"><h3>${t}</h3><div class="big">${fmt(v, hl ? 3 : 2)}</div><p>${desc}</p></div>`
  ).join("");
  didTrendInto("didAnalyzePlot", a.trend, a.t0);
  didEventInto("didAnalyzeEvent", a.event_study);
}

// ---- ④ assumptions ----
function initDidAssume() {
  if (didAssumeReady) return;
  didAssumeReady = true;
  runDidAssumptions(didState.req || { source: "example_did", lang: lang() });
}
async function runDidAssumptions(req) {
  const body = req ? { ...req, lang: lang() } : { source: "example_did", lang: lang() };
  let out;
  try { out = await postJSON(`${API}/api/did_assumptions`, body); } catch (e) { return; }
  state.didDash = out;
  renderDidAssumptions(out);
}
function renderDidAssumptions(out) {
  document.getElementById("didAssumeHint").classList.add("hidden");
  const ov = document.getElementById("didOverall");
  const worst = worstStatus(out.checks);
  const head = {
    green: tr("各項佐證都通過，這個 DiD 看起來可信。", "All checks pass — this DiD looks credible."),
    amber: tr("有項目需要留意，請展開卡片細看。", "Some items need attention — expand the cards."),
    red: tr("有項目不符，DiD 結果要保守看待。", "Some items fail — interpret the DiD with caution."),
    info: tr("關鍵假設需靠領域知識判斷，請看各卡片說明。", "The key assumption needs domain judgement — see each card."),
  }[worst];
  ov.classList.remove("hidden");
  ov.className = `overall st-${worst}`; ov.style.background = "#fff";
  ov.innerHTML = `<span class="dot bg-${worst}"></span> ${head}`;
  document.getElementById("didAssumeCards").innerHTML = out.checks.map((c) => {
    const metrics = c.metrics.map((m) =>
      `<li>${m.name}<b>${m.value === null ? "–" : m.value}</b><span>${m.note || ""}</span></li>`).join("");
    return `<div class="acard st-${c.status}">
      <h3><span class="dot bg-${c.status}"></span>${c.title}
        <span class="badge bg-${c.status}">${statusText(c.status)}</span></h3>
      <p class="headline"><b>${c.headline}</b></p>
      <p class="plain">${c.plain}</p>
      <ul class="metrics">${metrics}</ul>
      <details class="term"><summary>${tr("看專有名詞解釋", "Show term explanation")}</summary><p>${c.term}</p></details>
    </div>`;
  }).join("");
}

// ---- ⑤ boost: the ONE real-ML estimator (DML), button-gated (loads sklearn) ----
function initDidMl() { didMlReady = true; if (state.didDml) renderDidDml(state.didDml); }
function renderDidDml(d) {
  document.getElementById("didDmlOut").classList.remove("hidden");
  didBarsInto("didDmlChart", d.bars);
  document.getElementById("didDmlReading").textContent = d.reading;
}
const _runDidDmlBtn = document.getElementById("runDidDml");
if (_runDidDmlBtn) _runDidDmlBtn.addEventListener("click", async () => {
  _runDidDmlBtn.disabled = true;
  const old = _runDidDmlBtn.textContent;
  _runDidDmlBtn.textContent = tr("計算中…（載入 ML 套件＋訓練）", "Computing… (loading ML package + training)");
  try {
    const d = await getJSON(`${API}/api/did_dml?lang=${lang()}`);
    state.didDml = d;
    renderDidDml(d);
    _runDidDmlBtn.textContent = tr("重新計算 DML", "Re-run DML");
  } catch (e) {
    _runDidDmlBtn.textContent = tr("計算失敗，再試一次", "Failed — try again");
  } finally { _runDidDmlBtn.disabled = false; }
});
function drawDidStagScene() {
  if (!document.getElementById("sceneDidStag")) return;
  const cohorts = [
    { g: 2, label: tr("早採用（第2期起）", "early (from t=2)"), y: 2 },
    { g: 4, label: tr("晚採用（第4期起）", "late (from t=4)"), y: 1 },
    { g: -1, label: tr("從不採用（對照）", "never (control)"), y: 0 },
  ];
  const rows = [], ann = [];
  cohorts.forEach((c) => {
    rows.push({ x: [0, 5], y: [c.y, c.y], mode: "lines", type: "scatter",
      line: { color: "#dce2e8", width: 12 }, hoverinfo: "skip" });
    if (c.g >= 0) rows.push({ x: [c.g, 5], y: [c.y, c.y], mode: "lines", type: "scatter",
      line: { color: TEAL, width: 12 }, hoverinfo: "skip" });
    ann.push({ x: 5.2, y: c.y, text: c.label, showarrow: false, xanchor: "left",
      font: { size: 10, color: INK } });
  });
  Plotly.react("sceneDidStag", rows, sceneLayout({
    height: 220, margin: { t: 18, r: 150, b: 38, l: 16 },
    xaxis: { title: tr("期別（青色＝已受處置）", "period (teal = treated)"), range: [-0.3, 8.5], dtick: 1 },
    yaxis: { showticklabels: false, range: [-0.6, 2.6] },
    annotations: ann,
  }), SCENE_CFG);
}
function drawDidUnivScene(u) {
  if (!document.getElementById("sceneDidUniv")) return;
  const pr = u.scene.probs;
  const xs = [tr("政策前", "pre"), tr("政策後", "post")];
  const treat = { x: xs, y: pr.treated, mode: "lines+markers", type: "scatter",
    name: tr("介入", "treated"), line: { color: TEAL, width: 3 }, marker: { size: 9 } };
  const ctrl = { x: xs, y: pr.control, mode: "lines+markers", type: "scatter",
    name: tr("對照", "control"), line: { color: "#9aa6b2", width: 3 }, marker: { size: 9 } };
  Plotly.react("sceneDidUniv", [ctrl, treat], sceneLayout({
    showlegend: true, legend: { orientation: "h", y: 1.18 },
    yaxis: { title: tr("事件發生率", "event rate"), range: [0, 1], tickformat: ".0%" },
  }), SCENE_CFG);
}
function drawDidSynth(s) {
  if (!document.getElementById("didSynthChart")) return;
  const P = s.series.periods;
  const treated = { x: P, y: s.series.treated, mode: "lines+markers", type: "scatter",
    name: tr("受處置單位", "treated unit"), line: { color: TEAL, width: 3 }, marker: { size: 6 } };
  const synth = { x: P, y: s.series.synth, mode: "lines", type: "scatter",
    name: tr("合成反事實", "synthetic"), line: { color: AMBER, width: 3, dash: "dash" } };
  Plotly.react("didSynthChart", [synth, treated], sceneLayout({
    height: 320, showlegend: true, legend: { orientation: "h", y: 1.15 },
    xaxis: { title: tr("期別", "period"), dtick: 1 }, yaxis: { title: tr("結果", "outcome") },
    shapes: [{ type: "line", x0: s.t0 - 0.5, x1: s.t0 - 0.5, y0: 0, y1: 1, yref: "paper",
      line: { color: INK, width: 1.5, dash: "dot" } }],
    annotations: [{ x: s.t0 - 0.5, y: 1, yref: "paper", yshift: 6,
      text: tr("政策上路", "policy on"), showarrow: false, font: { size: 10, color: INK } }],
  }), SCENE_CFG);
}

// ======================================================================
// Trend-in-trend (TiT method) — tabs ①–④ (⑤ is static honest-unknown HTML)
// ======================================================================
const titState = { source: null, columns: [], req: null };
let titLearnReady = false, titPlayReady = false, titAnalyzeReady = false, titAssumeReady = false;

function titColor(g, K) {
  const f = K > 1 ? g / (K - 1) : 0;
  const c0 = [154, 166, 178], c1 = [13, 148, 136];   // grey -> teal
  const c = c0.map((v, i) => Math.round(v + (c1[i] - v) * f));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}
function titCurvesInto(elId, curve, key, yTitle, pct) {
  if (!document.getElementById(elId)) return;
  const P = curve.periods, K = curve.strata.length;
  const traces = curve.strata.map((s) => ({
    x: P, y: s[key], mode: "lines+markers", type: "scatter",
    name: tr(`第 ${s.g + 1} 層`, `stratum ${s.g + 1}`),
    line: { color: titColor(s.g, K), width: 2.5 }, marker: { size: 5 },
  }));
  Plotly.react(elId, traces, sceneLayout({
    height: 320, showlegend: true, legend: { orientation: "h", y: 1.12, font: { size: 9 } },
    xaxis: { title: tr("期別（季）", "period (quarter)"), dtick: 1 },
    yaxis: Object.assign({ title: yTitle }, pct ? { tickformat: ".0%" } : {}),
  }), SCENE_CFG);
}

// ---- ① learn ----
function initTitLearn() {
  if (titLearnReady) return;
  titLearnReady = true;
  drawSceneTitFan();
}
function drawSceneTitFan() {
  if (!document.getElementById("sceneTitFan")) return;
  const rng = mulberry32(717);
  const P = Array.from({ length: 10 }, (_, i) => i), K = 5;
  const strata = [];
  for (let g = 0; g < K; g++) {
    const slope = 0.05 + 0.12 * g;
    const p = P.map((tp) => {
      const lo = -4.0 + slope * tp;
      const pr = 1 / (1 + Math.exp(-lo));
      return Math.max(0, pr + (rng() - 0.5) * 0.012);
    });
    strata.push({ g, p });
  }
  titCurvesInto("sceneTitFan", { periods: P, strata }, "p", tr("接種率", "vaccination rate"), true);
}

// ---- ② interactive ----
const titTrendSlider = document.getElementById("titTrendSlider");
let titPlayTimer = null;
function initTitPlay() {
  if (titPlayReady) return;
  titPlayReady = true;
  refreshTitPlay();
}
function scheduleTitPlay() {
  document.getElementById("titTrendVal").textContent = Number(titTrendSlider.value).toFixed(1);
  clearTimeout(titPlayTimer);
  titPlayTimer = setTimeout(refreshTitPlay, 180);
}
if (titTrendSlider) titTrendSlider.addEventListener("input", scheduleTitPlay);
async function refreshTitPlay() {
  const tv = titTrendSlider ? Number(titTrendSlider.value) : 1.0;
  let d;
  try { d = await getJSON(`${API}/api/tit_interactive?trend=${tv}&lang=${lang()}`); }
  catch (e) { return; }
  state.titPlay = d;
  document.getElementById("titOr").textContent = fmt(d.or, 2);
  const w = (d.ci[0] != null && d.ci[1] != null) ? d.ci[1] - d.ci[0] : null;
  document.getElementById("titCiW").textContent = w != null ? fmt(w, 2) : "–";
  document.getElementById("titCiFoot").textContent = (d.ci[0] != null)
    ? tr(`${fmt(d.ci[0], 2)}～${fmt(d.ci[1], 2)}`, `${fmt(d.ci[0], 2)}–${fmt(d.ci[1], 2)}`) : "";
  document.getElementById("titNaive").textContent = fmt(d.naive_or, 2);
  titCurvesInto("titExpoChart", d.exposure_curve, "p", tr("接種率", "vaccination rate"), true);
  titCurvesInto("titOutChart", d.outcome_curve, "q", tr("結果率", "outcome rate"), true);
}

// ---- ③ analyze ----
function initTitAnalyze() {
  if (titAnalyzeReady) return;
  titAnalyzeReady = true;
  document.getElementById("useTitExample").click();
}
function titFillCov(cols) {
  const cov = cols.filter((c) => !["pid", "period", "exposed", "outcome"].includes(c));
  document.getElementById("titSelCov").innerHTML =
    cov.map((c) => `<option value="${c}" selected>${c}</option>`).join("");
  document.getElementById("titColMap").classList.remove("hidden");
}
document.getElementById("useTitExample").addEventListener("click", async () => {
  const st = document.getElementById("titDataStatus");
  try {
    const d = await getJSON(`${API}/api/tit_example`);
    titState.source = "example_tit"; titState.columns = d.columns;
    st.textContent = tr(`已載入內建疫苗普及範例（${d.n_people} 人 × ${Math.round(d.n_rows / d.n_people)} 期，合成虛構）`,
                        `Loaded built-in vaccine-uptake example (${d.n_people} people × ${Math.round(d.n_rows / d.n_people)} periods, synthetic)`);
    titFillCov(d.columns);
    runTitAnalyze();
  } catch (e) { st.textContent = tr("載入失敗：", "Load failed: ") + e.message; }
});
document.getElementById("titFileInput").addEventListener("change", async (ev) => {
  const file = ev.target.files[0]; if (!file) return;
  const fd = new FormData(); fd.append("file", file);
  const st = document.getElementById("titDataStatus"); st.textContent = tr("上傳中…", "Uploading…");
  try {
    const r = await fetch(`${API}/api/upload`, { method: "POST", body: fd });
    if (!r.ok) throw new Error((await r.json()).detail);
    const d = await r.json();
    titState.source = d.token; titState.columns = d.columns;
    st.textContent = tr(`已上傳「${file.name}」（${d.n} 列）`, `Uploaded "${file.name}" (${d.n} rows)`);
    titFillCov(d.columns);
  } catch (e) { st.textContent = tr("上傳失敗：", "Upload failed: ") + e.message; }
});
function titCurrentMapping() {
  return {
    source: titState.source,
    K: Number(document.getElementById("titSelK").value),
    covariates: [...document.getElementById("titSelCov").selectedOptions].map((o) => o.value),
    lang: lang(),
  };
}
document.getElementById("runTitAnalyze").addEventListener("click", runTitAnalyze);
async function runTitAnalyze() {
  const req = titCurrentMapping();
  if (!req.source) return;
  titState.req = req;
  try {
    const a = await postJSON(`${API}/api/tit_analyze`, req);
    renderTitAnalyze(a);
    runTitAssumptions(req);
  } catch (e) { alert(tr("分析失敗：", "Analysis failed: ") + e.message); }
}
function renderTitAnalyze(a) {
  document.getElementById("titAnalyzeOut").classList.remove("hidden");
  const cards = [
    [tr("趨勢中的趨勢 OR（因果）", "Trend-in-trend OR (causal)"), a.or, a.interpretation, true],
    [tr("天真世代 OR（有偏）", "Naive cohort OR (biased)"), a.naive_or,
      tr("直接比較接種與未接種，被適應症混淆。", "Direct vaccinated-vs-unvaccinated comparison, confounded by indication."), false],
    [tr("CPE 分層品質（AUC）", "CPE stratification quality (AUC)"), a.cpe_auc,
      tr("越高代表分層越能拉開暴露趨勢。", "Higher = strata separate the exposure trends better."), false],
  ];
  document.getElementById("titAnalyzeCards").innerHTML = cards.map(([t, v, desc, hl]) =>
    `<div class="rc ${hl ? "highlight" : ""}"><h3>${t}</h3><div class="big">${fmt(v, 2)}</div><p>${desc}</p></div>`
  ).join("");
  titCurvesInto("titAnalyzeExpo", a.exposure_curve, "p", tr("接種率", "vaccination rate"), true);
  titCurvesInto("titAnalyzeOut2", a.outcome_curve, "q", tr("結果率", "outcome rate"), true);
}

// ---- ④ assumptions ----
function initTitAssume() {
  if (titAssumeReady) return;
  titAssumeReady = true;
  runTitAssumptions(titState.req || { source: "example_tit", lang: lang() });
}
async function runTitAssumptions(req) {
  const body = req ? { ...req, lang: lang() } : { source: "example_tit", lang: lang() };
  let out;
  try { out = await postJSON(`${API}/api/tit_assumptions`, body); } catch (e) { return; }
  state.titDash = out;
  renderTitAssumptions(out);
}
function renderTitAssumptions(out) {
  document.getElementById("titAssumeHint").classList.add("hidden");
  const ov = document.getElementById("titOverall");
  const worst = worstStatus(out.checks);
  const head = {
    green: tr("各項佐證都通過，這個 TiT 看起來可信。", "All checks pass — this TiT looks credible."),
    amber: tr("有項目需要留意，請展開卡片細看。", "Some items need attention — expand the cards."),
    red: tr("有項目不符，TiT 結果要保守看待。", "Some items fail — interpret the TiT with caution."),
    info: tr("關鍵假設需靠領域知識判斷，請看各卡片說明。", "The key assumption needs domain judgement — see each card."),
  }[worst];
  ov.classList.remove("hidden");
  ov.className = `overall st-${worst}`; ov.style.background = "#fff";
  ov.innerHTML = `<span class="dot bg-${worst}"></span> ${head}`;
  document.getElementById("titAssumeCards").innerHTML = out.checks.map((c) => {
    const metrics = c.metrics.map((m) =>
      `<li>${m.name}<b>${m.value === null ? "–" : m.value}</b><span>${m.note || ""}</span></li>`).join("");
    return `<div class="acard st-${c.status}">
      <h3><span class="dot bg-${c.status}"></span>${c.title}
        <span class="badge bg-${c.status}">${statusText(c.status)}</span></h3>
      <p class="headline"><b>${c.headline}</b></p>
      <p class="plain">${c.plain}</p>
      <ul class="metrics">${metrics}</ul>
      <details class="term"><summary>${tr("看專有名詞解釋", "Show term explanation")}</summary><p>${c.term}</p></details>
    </div>`;
  }).join("");
}

// ======================================================================
// Interrupted Time Series (ITS method) — tabs ①–⑤
// ======================================================================
const itsState = { source: null, columns: [], req: null };
let itsLearnReady = false, itsPlayReady = false, itsAnalyzeReady = false,
    itsAssumeReady = false, itsMlReady = false;

// shared: observed points + fitted pre/post segments + dashed counterfactual + cutoff
function itsSeriesInto(elId, plot) {
  if (!document.getElementById(elId)) return;
  const pts = { x: plot.points.x, y: plot.points.y, mode: "markers", type: "scatter",
    name: tr("觀察", "observed"), marker: { color: "#9aa6b2", size: 5, opacity: 0.85 } };
  const cf = { x: plot.counterfactual.x, y: plot.counterfactual.y, mode: "lines", type: "scatter",
    name: tr("反事實", "counterfactual"), line: { color: AMBER, width: 2.5, dash: "dash" } };
  const pre = { x: plot.pre.x, y: plot.pre.y, mode: "lines", type: "scatter",
    name: tr("前趨勢", "pre-trend"), line: { color: TEAL, width: 3 } };
  const post = { x: plot.post.x, y: plot.post.y, mode: "lines", type: "scatter",
    name: tr("介入後", "post"), line: { color: TEAL, width: 3 }, showlegend: false };
  Plotly.react(elId, [pts, cf, pre, post], sceneLayout({
    height: 340, showlegend: true, legend: { orientation: "h", y: 1.1, font: { size: 9 } },
    xaxis: { title: tr("期序", "period") }, yaxis: { title: tr("結果", "outcome") },
    shapes: [{ type: "line", x0: plot.t0 - 0.5, x1: plot.t0 - 0.5, y0: 0, y1: 1, yref: "paper",
      line: { color: INK, width: 1.5, dash: "dot" } }],
    annotations: [{ x: plot.t0 - 0.5, y: 1, yref: "paper", yshift: 6,
      text: tr("介入", "intervention"), showarrow: false, font: { size: 10, color: INK } }],
  }), SCENE_CFG);
}

// ---- ① learn ----
function initItsLearn() {
  if (itsLearnReady) return;
  itsLearnReady = true;
  drawSceneItsExplain();
}
function drawSceneItsExplain() {
  if (!document.getElementById("sceneItsExplain")) return;
  const rng = mulberry32(818);
  const n = 48, t0 = 24, b0 = 100, b1 = 0.4, lev = -12, slo = -0.6;
  const x = [], y = [];
  for (let t = 0; t < n; t++) {
    const post = t >= t0 ? 1 : 0, ts = post ? t - t0 : 0;
    x.push(t); y.push(b0 + b1 * t + lev * post + slo * ts + randn(rng) * 2.2);
  }
  itsSeriesInto("sceneItsExplain", {
    points: { x, y },
    pre: { x: [0, t0 - 1], y: [b0, b0 + b1 * (t0 - 1)] },
    post: { x: [t0, n - 1], y: [b0 + b1 * t0 + lev, b0 + b1 * (n - 1) + lev + slo * (n - 1 - t0)] },
    counterfactual: { x: [t0 - 1, n - 1], y: [b0 + b1 * (t0 - 1), b0 + b1 * (n - 1)] },
    t0,
  });
}

// ---- ② interactive ----
const itsLevelSlider = document.getElementById("itsLevelSlider");
let itsPlayTimer = null;
function initItsPlay() {
  if (itsPlayReady) return;
  itsPlayReady = true;
  refreshItsPlay();
}
function scheduleItsPlay() {
  document.getElementById("itsLevelVal").textContent = Number(itsLevelSlider.value).toFixed(0);
  clearTimeout(itsPlayTimer);
  itsPlayTimer = setTimeout(refreshItsPlay, 140);
}
if (itsLevelSlider) itsLevelSlider.addEventListener("input", scheduleItsPlay);
async function refreshItsPlay() {
  const lv = itsLevelSlider ? Number(itsLevelSlider.value) : -12;
  let d;
  try { d = await getJSON(`${API}/api/its_interactive?level=${lv}&lang=${lang()}`); }
  catch (e) { return; }
  state.itsPlay = d;
  document.getElementById("itsLevel").textContent = fmt(d.level.estimate, 1);
  document.getElementById("itsLevelFoot").textContent = tr(`你設定的真值 ${lv}`, `you set ${lv}`);
  document.getElementById("itsSlope").textContent = fmt(d.slope.estimate, 2);
  document.getElementById("itsEffEnd").textContent = fmt(d.effect_end, 1);
  itsSeriesInto("itsPlayChart", d.plot);
}

// ---- ③ analyze ----
function initItsAnalyze() {
  if (itsAnalyzeReady) return;
  itsAnalyzeReady = true;
  document.getElementById("useItsExample").click();
}
function itsFillSelects(cols) {
  const opts = cols.map((c) => `<option value="${c}">${c}</option>`).join("");
  ["itsSelTime", "itsSelY", "itsSelPost", "itsSelTs"].forEach((id) =>
    document.getElementById(id).innerHTML = opts);
  document.getElementById("itsColMap").classList.remove("hidden");
}
function itsApplyDefaults(d) {
  if (!d) return;
  const set = (id, v) => { const el = document.getElementById(id); if (v != null) el.value = v; };
  set("itsSelTime", d.time); set("itsSelY", d.outcome); set("itsSelPost", d.post); set("itsSelTs", d.t_since);
}
document.getElementById("useItsExample").addEventListener("click", async () => {
  const st = document.getElementById("itsDataStatus");
  try {
    const d = await getJSON(`${API}/api/its_example`);
    itsState.source = "example_its"; itsState.columns = d.columns;
    st.textContent = tr(`已載入內建每月範例（${d.n} 期，合成虛構）`,
                        `Loaded built-in monthly example (${d.n} months, synthetic)`);
    itsFillSelects(d.columns); itsApplyDefaults(d.defaults);
    runItsAnalyze();
  } catch (e) { st.textContent = tr("載入失敗：", "Load failed: ") + e.message; }
});
document.getElementById("itsFileInput").addEventListener("change", async (ev) => {
  const file = ev.target.files[0]; if (!file) return;
  const fd = new FormData(); fd.append("file", file);
  const st = document.getElementById("itsDataStatus"); st.textContent = tr("上傳中…", "Uploading…");
  try {
    const r = await fetch(`${API}/api/upload`, { method: "POST", body: fd });
    if (!r.ok) throw new Error((await r.json()).detail);
    const d = await r.json();
    itsState.source = d.token; itsState.columns = d.columns;
    st.textContent = tr(`已上傳「${file.name}」（${d.n} 列）`, `Uploaded "${file.name}" (${d.n} rows)`);
    itsFillSelects(d.columns);
  } catch (e) { st.textContent = tr("上傳失敗：", "Upload failed: ") + e.message; }
});
function itsCurrentMapping() {
  const v = (id) => document.getElementById(id).value;
  return { source: itsState.source, time: v("itsSelTime"), outcome: v("itsSelY"),
    post: v("itsSelPost"), t_since: v("itsSelTs"), lang: lang() };
}
document.getElementById("runItsAnalyze").addEventListener("click", runItsAnalyze);
async function runItsAnalyze() {
  const req = itsCurrentMapping();
  if (!req.source) return;
  itsState.req = req;
  try {
    const a = await postJSON(`${API}/api/its_analyze`, req);
    renderItsAnalyze(a);
    runItsAssumptions(req);
    renderItsVariants();   // advanced (non-AI) variants shown under ③
  } catch (e) { alert(tr("分析失敗：", "Analysis failed: ") + e.message); }
}
// advanced VARIANTS (not AI) rendered in tab ③ — light, no sklearn
async function renderItsVariants() {
  let d;
  try { d = await getJSON(`${API}/api/its_variants?lang=${lang()}`); } catch (e) { return; }
  state.itsVar = d;
  drawItsHac(d.hac); document.getElementById("itsHacReading").textContent = d.hac.reading;
  drawItsCtrl(d.controlled); document.getElementById("itsCtrlReading").textContent = d.controlled.reading;
  drawItsBsts(d.bsts); document.getElementById("itsBstsReading").textContent = d.bsts.reading;
}
function renderItsAnalyze(a) {
  document.getElementById("itsAnalyzeOut").classList.remove("hidden");
  const cards = [
    [tr("水準變化 β₂", "Level change β₂"), a.level.estimate, a.interpretation, true],
    [tr("斜率變化 β₃", "Slope change β₃"), a.slope.estimate,
      tr(`HAC 95% 區間 ${fmt(a.slope.ci[0], 2)}～${fmt(a.slope.ci[1], 2)}。`,
         `HAC 95% CI ${fmt(a.slope.ci[0], 2)}–${fmt(a.slope.ci[1], 2)}.`), false],
    [tr("追蹤結束時效果", "Effect at end"), a.effect_end,
      tr(`殘差自相關 lag-1≈${fmt(a.acf1, 2)}（已用 HAC 校正）。`,
         `residual lag-1 acf≈${fmt(a.acf1, 2)} (HAC-corrected).`), false],
  ];
  document.getElementById("itsAnalyzeCards").innerHTML = cards.map(([t, v, desc, hl]) =>
    `<div class="rc ${hl ? "highlight" : ""}"><h3>${t}</h3><div class="big">${fmt(v, hl ? 1 : 2)}</div><p>${desc}</p></div>`
  ).join("");
  itsSeriesInto("itsAnalyzeChart", a.plot);
}

// ---- ④ assumptions ----
function initItsAssume() {
  if (itsAssumeReady) return;
  itsAssumeReady = true;
  runItsAssumptions(itsState.req || { source: "example_its", lang: lang() });
}
async function runItsAssumptions(req) {
  const body = req ? { ...req, lang: lang() } : { source: "example_its", lang: lang() };
  let out;
  try { out = await postJSON(`${API}/api/its_assumptions`, body); } catch (e) { return; }
  state.itsDash = out;
  renderItsAssumptions(out);
}
function renderItsAssumptions(out) {
  document.getElementById("itsAssumeHint").classList.add("hidden");
  const ov = document.getElementById("itsOverall");
  const worst = worstStatus(out.checks);
  const head = {
    green: tr("各項佐證都通過，這個 ITS 看起來可信。", "All checks pass — this ITS looks credible."),
    amber: tr("有項目需要留意，請展開卡片細看。", "Some items need attention — expand the cards."),
    red: tr("有項目不符，ITS 結果要保守看待。", "Some items fail — interpret the ITS with caution."),
    info: tr("關鍵假設需靠領域知識判斷，請看各卡片說明。", "The key assumption needs domain judgement — see each card."),
  }[worst];
  ov.classList.remove("hidden");
  ov.className = `overall st-${worst}`; ov.style.background = "#fff";
  ov.innerHTML = `<span class="dot bg-${worst}"></span> ${head}`;
  document.getElementById("itsAssumeCards").innerHTML = out.checks.map((c) => {
    const metrics = c.metrics.map((m) =>
      `<li>${m.name}<b>${m.value === null ? "–" : m.value}</b><span>${m.note || ""}</span></li>`).join("");
    return `<div class="acard st-${c.status}">
      <h3><span class="dot bg-${c.status}"></span>${c.title}
        <span class="badge bg-${c.status}">${statusText(c.status)}</span></h3>
      <p class="headline"><b>${c.headline}</b></p>
      <p class="plain">${c.plain}</p>
      <ul class="metrics">${metrics}</ul>
      <details class="term"><summary>${tr("看專有名詞解釋", "Show term explanation")}</summary><p>${c.term}</p></details>
    </div>`;
  }).join("");
}

// ---- ⑤ boost: the ONE real-ML estimator (ML two-stage counterfactual), button-gated ----
function initItsMl() { itsMlReady = true; if (state.itsMlcf) renderItsMlcf(state.itsMlcf); }
function renderItsMlcf(d) {
  document.getElementById("itsMlcfOut").classList.remove("hidden");
  didBarsInto("itsMlcfChart", d.bars);
  document.getElementById("itsMlcfReading").textContent = d.reading;
  const s = d.series;
  const pts = { x: s.time, y: s.y, mode: "markers", type: "scatter",
    name: tr("觀察", "observed"), marker: { color: "#9aa6b2", size: 5 } };
  const cf = { x: s.time, y: s.cf, mode: "lines", type: "scatter",
    name: tr("ML 反事實", "ML counterfactual"), line: { color: AMBER, width: 2.5, dash: "dash" } };
  Plotly.react("itsMlcfSeries", [pts, cf], sceneLayout({
    height: 320, showlegend: true, legend: { orientation: "h", y: 1.12, font: { size: 9 } },
    xaxis: { title: tr("期序", "period") }, yaxis: { title: tr("結果", "outcome") },
    shapes: [_itsCutoff(s.t0)],
  }), SCENE_CFG);
}
const _runItsMlcfBtn = document.getElementById("runItsMlcf");
if (_runItsMlcfBtn) _runItsMlcfBtn.addEventListener("click", async () => {
  _runItsMlcfBtn.disabled = true;
  _runItsMlcfBtn.textContent = tr("計算中…（載入 ML 套件＋訓練）", "Computing… (loading ML package + training)");
  try {
    const d = await getJSON(`${API}/api/its_mlcf?lang=${lang()}`);
    state.itsMlcf = d;
    renderItsMlcf(d);
    _runItsMlcfBtn.textContent = tr("重新計算 ML 反事實", "Re-run ML counterfactual");
  } catch (e) {
    _runItsMlcfBtn.textContent = tr("計算失敗，再試一次", "Failed — try again");
  } finally { _runItsMlcfBtn.disabled = false; }
});
function _itsCutoff(t0) {
  return { type: "line", x0: t0 - 0.5, x1: t0 - 0.5, y0: 0, y1: 1, yref: "paper",
    line: { color: INK, width: 1.3, dash: "dot" } };
}
function drawItsHac(h) {
  if (!document.getElementById("itsHacChart")) return;
  const s = h.series;
  const pts = { x: s.time, y: s.y, mode: "lines+markers", type: "scatter",
    line: { color: "#9aa6b2", width: 1 }, marker: { color: INK, size: 4 }, name: tr("觀察", "observed") };
  Plotly.react("itsHacChart", [pts], sceneLayout({
    height: 300, xaxis: { title: tr("期序", "period") }, yaxis: { title: tr("結果", "outcome") },
    shapes: [_itsCutoff(s.t0)],
  }), SCENE_CFG);
}
function drawItsCtrl(c) {
  if (!document.getElementById("itsCtrlChart")) return;
  const s = c.series;
  const tr1 = { x: s.time, y: s.treated, mode: "lines+markers", type: "scatter",
    name: tr("介入序列", "treated"), line: { color: TEAL, width: 2 }, marker: { size: 4 } };
  const cr = { x: s.time, y: s.control, mode: "lines+markers", type: "scatter",
    name: tr("控制序列", "control"), line: { color: "#9aa6b2", width: 2 }, marker: { size: 4 } };
  Plotly.react("itsCtrlChart", [cr, tr1], sceneLayout({
    height: 320, showlegend: true, legend: { orientation: "h", y: 1.12, font: { size: 9 } },
    xaxis: { title: tr("期序", "period") }, yaxis: { title: tr("結果", "outcome") },
    shapes: [_itsCutoff(s.t0)],
  }), SCENE_CFG);
}
function drawItsFlex(f) {
  if (!document.getElementById("itsFlexChart")) return;
  const s = f.series;
  const pts = { x: s.time, y: s.y, mode: "markers", type: "scatter",
    name: tr("觀察", "observed"), marker: { color: "#9aa6b2", size: 5 } };
  const cf = { x: s.time, y: s.cf, mode: "lines", type: "scatter",
    name: tr("彈性反事實", "flexible counterfactual"), line: { color: AMBER, width: 2.5, dash: "dash" } };
  Plotly.react("itsFlexChart", [pts, cf], sceneLayout({
    height: 320, showlegend: true, legend: { orientation: "h", y: 1.12, font: { size: 9 } },
    xaxis: { title: tr("期序", "period") }, yaxis: { title: tr("結果", "outcome") },
    shapes: [_itsCutoff(s.t0)],
  }), SCENE_CFG);
}
function drawItsBsts(b) {
  if (!document.getElementById("itsBstsChart")) return;
  const s = b.series;
  const lo = { x: s.time, y: s.lo, mode: "lines", type: "scatter", line: { width: 0 },
    showlegend: false, hoverinfo: "skip" };
  const hi = { x: s.time, y: s.hi, mode: "lines", type: "scatter", line: { width: 0 },
    fill: "tonexty", fillcolor: "rgba(245,158,11,0.18)", name: tr("反事實不確定帶", "counterfactual band") };
  const cf = { x: s.time, y: s.cf, mode: "lines", type: "scatter",
    name: tr("反事實", "counterfactual"), line: { color: AMBER, width: 2, dash: "dash" } };
  const pts = { x: s.time, y: s.y, mode: "markers", type: "scatter",
    name: tr("觀察", "observed"), marker: { color: INK, size: 4 } };
  Plotly.react("itsBstsChart", [lo, hi, cf, pts], sceneLayout({
    height: 320, showlegend: true, legend: { orientation: "h", y: 1.12, font: { size: 9 } },
    xaxis: { title: tr("期序", "period") }, yaxis: { title: tr("結果", "outcome") },
    shapes: [_itsCutoff(s.t0)],
  }), SCENE_CFG);
}

// ======================================================================
// Prior Event Rate Ratio (PERR method) — tabs ①–⑤
// ======================================================================
const perrState = { source: null, columns: [], req: null };
let perrLearnReady = false, perrPlayReady = false, perrAnalyzeReady = false,
    perrAssumeReady = false, perrMlReady = false;

function perrRatesInto(elId, rates) {
  if (!document.getElementById(elId)) return;
  const x = [tr("事前期", "prior"), tr("事後期", "post")];
  const treated = { x, y: [rates.treated_prior, rates.treated_post], type: "bar",
    name: tr("處置組", "treated"), marker: { color: TEAL } };
  const control = { x, y: [rates.control_prior, rates.control_post], type: "bar",
    name: tr("對照組", "control"), marker: { color: "#9aa6b2" } };
  Plotly.react(elId, [treated, control], sceneLayout({
    height: 300, barmode: "group", showlegend: true, legend: { orientation: "h", y: 1.12 },
    yaxis: { title: tr("事件率（每人年）", "event rate (per person-year)") },
  }), SCENE_CFG);
}
function perrRatioBars(elId, d) {
  if (!document.getElementById(elId)) return;
  const labels = [tr("事前率比", "RR prior"), tr("天真事後", "naive post"), tr("PERR", "PERR")];
  const vals = [d.rr_prior, d.naive_rr, d.perr];
  Plotly.react(elId, [{ x: labels, y: vals, type: "bar",
    marker: { color: ["#9aa6b2", AMBER, TEAL] },
    text: vals.map((v) => v.toFixed(2)), textposition: "auto" }], sceneLayout({
    height: 300, yaxis: { title: tr("率比", "rate ratio") },
    shapes: [
      { type: "line", x0: -0.5, x1: 2.5, y0: 1.0, y1: 1.0, line: { color: "#9aa6b2", width: 1.5, dash: "dot" } },
      { type: "line", x0: -0.5, x1: 2.5, y0: d.true_rr, y1: d.true_rr, line: { color: GREEN, width: 2, dash: "dash" } },
    ],
    annotations: [{ x: 2, y: d.true_rr, text: tr("真值 0.70", "truth 0.70"), showarrow: false,
      yshift: -12, font: { size: 10, color: GREEN } }],
  }), SCENE_CFG);
}

// ---- ① learn ----
function initPerrLearn() {
  if (perrLearnReady) return;
  perrLearnReady = true;
  drawScenePerr();
}
function drawScenePerr() {
  if (!document.getElementById("perrScene")) return;
  perrRatesInto("perrScene", { treated_prior: 0.131, control_prior: 0.094,
    treated_post: 0.066, control_post: 0.064 });
}

// ---- ② interactive ----
const perrDriftSlider = document.getElementById("perrDriftSlider");
let perrPlayTimer = null;
function initPerrPlay() {
  if (perrPlayReady) return;
  perrPlayReady = true;
  refreshPerrPlay();
}
function schedulePerrPlay() {
  document.getElementById("perrDriftVal").textContent = Number(perrDriftSlider.value).toFixed(1);
  clearTimeout(perrPlayTimer);
  perrPlayTimer = setTimeout(refreshPerrPlay, 150);
}
if (perrDriftSlider) perrDriftSlider.addEventListener("input", schedulePerrPlay);
async function refreshPerrPlay() {
  const dv = perrDriftSlider ? Number(perrDriftSlider.value) : 0;
  let d;
  try { d = await getJSON(`${API}/api/perr_interactive?drift=${dv}&lang=${lang()}`); }
  catch (e) { return; }
  state.perrPlay = d;
  document.getElementById("perrEst").textContent = fmt(d.perr, 2);
  document.getElementById("perrNaive").textContent = fmt(d.naive_rr, 2);
  document.getElementById("perrPrior").textContent = fmt(d.rr_prior, 2);
  perrRatioBars("perrPlayChart", d);
}

// ---- ③ analyze ----
function initPerrAnalyze() {
  if (perrAnalyzeReady) return;
  perrAnalyzeReady = true;
  document.getElementById("usePerrExample").click();
}
function perrFillSelects(cols) {
  const opts = cols.map((c) => `<option value="${c}">${c}</option>`).join("");
  ["perrSelGroup", "perrSelEp", "perrSelPp", "perrSelEs", "perrSelPs"].forEach((id) =>
    document.getElementById(id).innerHTML = opts);
  document.getElementById("perrColMap").classList.remove("hidden");
}
function perrApplyDefaults(d) {
  if (!d) return;
  const set = (id, v) => { const el = document.getElementById(id); if (v != null) el.value = v; };
  set("perrSelGroup", d.group); set("perrSelEp", d.events_prior); set("perrSelPp", d.pt_prior);
  set("perrSelEs", d.events_post); set("perrSelPs", d.pt_post);
}
document.getElementById("usePerrExample").addEventListener("click", async () => {
  const st = document.getElementById("perrDataStatus");
  try {
    const d = await getJSON(`${API}/api/perr_example`);
    perrState.source = "example_perr"; perrState.columns = d.columns;
    st.textContent = tr(`已載入內建世代範例（${d.n} 人，合成虛構）`,
                        `Loaded built-in cohort example (${d.n} people, synthetic)`);
    perrFillSelects(d.columns); perrApplyDefaults(d.defaults);
    runPerrAnalyze();
  } catch (e) { st.textContent = tr("載入失敗：", "Load failed: ") + e.message; }
});
document.getElementById("perrFileInput").addEventListener("change", async (ev) => {
  const file = ev.target.files[0]; if (!file) return;
  const fd = new FormData(); fd.append("file", file);
  const st = document.getElementById("perrDataStatus"); st.textContent = tr("上傳中…", "Uploading…");
  try {
    const r = await fetch(`${API}/api/upload`, { method: "POST", body: fd });
    if (!r.ok) throw new Error((await r.json()).detail);
    const d = await r.json();
    perrState.source = d.token; perrState.columns = d.columns;
    st.textContent = tr(`已上傳「${file.name}」（${d.n} 列）`, `Uploaded "${file.name}" (${d.n} rows)`);
    perrFillSelects(d.columns);
  } catch (e) { st.textContent = tr("上傳失敗：", "Upload failed: ") + e.message; }
});
function perrCurrentMapping() {
  const v = (id) => document.getElementById(id).value;
  return { source: perrState.source, group: v("perrSelGroup"),
    events_prior: v("perrSelEp"), pt_prior: v("perrSelPp"),
    events_post: v("perrSelEs"), pt_post: v("perrSelPs"), lang: lang() };
}
document.getElementById("runPerrAnalyze").addEventListener("click", runPerrAnalyze);
async function runPerrAnalyze() {
  const req = perrCurrentMapping();
  if (!req.source) return;
  perrState.req = req;
  try {
    const a = await postJSON(`${API}/api/perr_analyze`, req);
    renderPerrAnalyze(a);
    runPerrAssumptions(req);
  } catch (e) { alert(tr("分析失敗：", "Analysis failed: ") + e.message); }
}
function renderPerrAnalyze(a) {
  document.getElementById("perrAnalyzeOut").classList.remove("hidden");
  const cards = [
    [tr("PERR（因果率比）", "PERR (causal rate ratio)"), a.perr, a.interpretation, true],
    [tr("天真事後率比（有偏）", "Naive post ratio (biased)"), a.naive_rr,
      tr("只看事後期，被適應症混淆掩蓋了效果。", "Post-only — confounding by indication hides the effect."), false],
    [tr("事前期率比（混淆指紋）", "Prior ratio (confounding fingerprint)"), a.rr_prior,
      tr(`PERR 95% 區間 ${fmt(a.ci[0], 2)}～${fmt(a.ci[1], 2)}。`,
         `PERR 95% CI ${fmt(a.ci[0], 2)}–${fmt(a.ci[1], 2)}.`), false],
  ];
  document.getElementById("perrAnalyzeCards").innerHTML = cards.map(([t, v, desc, hl]) =>
    `<div class="rc ${hl ? "highlight" : ""}"><h3>${t}</h3><div class="big">${fmt(v, 2)}</div><p>${desc}</p></div>`
  ).join("");
  perrRatesInto("perrAnalyzeChart", a.rates);
}

// ---- ④ assumptions ----
function initPerrAssume() {
  if (perrAssumeReady) return;
  perrAssumeReady = true;
  runPerrAssumptions(perrState.req || { source: "example_perr", lang: lang() });
}
async function runPerrAssumptions(req) {
  const body = req ? { ...req, lang: lang() } : { source: "example_perr", lang: lang() };
  let out;
  try { out = await postJSON(`${API}/api/perr_assumptions`, body); } catch (e) { return; }
  state.perrDash = out;
  renderPerrAssumptions(out);
}
function renderPerrAssumptions(out) {
  document.getElementById("perrAssumeHint").classList.add("hidden");
  const ov = document.getElementById("perrOverall");
  const worst = worstStatus(out.checks);
  const head = {
    green: tr("可測項目通過；關鍵假設仍需領域判斷。", "Testable checks pass; the key assumptions still need domain judgement."),
    amber: tr("有項目需要留意，請展開卡片細看。", "Some items need attention — expand the cards."),
    red: tr("有項目不符，PERR 結果要保守看待。", "Some items fail — interpret the PERR with caution."),
    info: tr("PERR 多數假設不可檢驗，需靠領域知識與敏感度分析。", "Most PERR assumptions are untestable — rely on domain knowledge and sensitivity analysis."),
  }[worst];
  ov.classList.remove("hidden");
  ov.className = `overall st-${worst}`; ov.style.background = "#fff";
  ov.innerHTML = `<span class="dot bg-${worst}"></span> ${head}`;
  document.getElementById("perrAssumeCards").innerHTML = out.checks.map((c) => {
    const metrics = c.metrics.map((m) =>
      `<li>${m.name}<b>${m.value === null ? "–" : m.value}</b><span>${m.note || ""}</span></li>`).join("");
    return `<div class="acard st-${c.status}">
      <h3><span class="dot bg-${c.status}"></span>${c.title}
        <span class="badge bg-${c.status}">${statusText(c.status)}</span></h3>
      <p class="headline"><b>${c.headline}</b></p>
      <p class="plain">${c.plain}</p>
      <ul class="metrics">${metrics}</ul>
      <details class="term"><summary>${tr("看專有名詞解釋", "Show term explanation")}</summary><p>${c.term}</p></details>
    </div>`;
  }).join("");
}

// ---- ⑤ scale sensitivity (documented refinement, not AI) ----
function initPerrMl() {
  if (perrMlReady) return;
  perrMlReady = true;
  refreshPerrMl();
}
async function refreshPerrMl() {
  let s;
  try { s = await getJSON(`${API}/api/perr_scale?lang=${lang()}`); } catch (e) { return; }
  state.perrScale = s;
  drawPerrScale(s);
  document.getElementById("perrScaleReading").textContent = s.reading;
}
function drawPerrScale(s) {
  if (!document.getElementById("perrScaleChart")) return;
  const y = [s.multiplicative.perr / s.multiplicative.true_rr, s.additive.perd / s.additive.true_diff];
  Plotly.react("perrScaleChart", [{
    x: [tr("乘法世界：看 PERR", "multiplicative: use PERR"), tr("加法世界：看 PERD", "additive: use PERD")],
    y, type: "bar", marker: { color: [TEAL, TEAL] },
    text: y.map((v) => v.toFixed(2) + "×"), textposition: "auto",
  }], sceneLayout({
    height: 280, yaxis: { title: tr("估計 ÷ 真值（1.0＝命中）", "estimate ÷ truth (1.0 = on target)"), range: [0, 1.4] },
    shapes: [{ type: "line", x0: -0.5, x1: 1.5, y0: 1, y1: 1, line: { color: GREEN, width: 2, dash: "dash" } }],
    annotations: [{ x: 1, y: 1, text: tr("命中真值", "on target"), showarrow: false, yshift: 10,
      font: { size: 10, color: GREEN } }],
  }), SCENE_CFG);
}

// ======================================================================
// Language switch — re-render any dynamic content already on screen
// ======================================================================
window.addEventListener("iv-lang", async () => {
  renderCitation();
  refreshPlay();                                   // interactive tab
  if (state.lastReq) {                             // analysis + dashboard
    const req = { ...state.lastReq, lang: lang() };
    state.lastReq = req;
    try {
      const out = await postJSON(`${API}/api/analyze`, req);
      renderAnalysis(out);
      runAssumptions(req);
    } catch (e) { /* ignore */ }
  }
  if (mlReady) { drawIvScenes(); refreshSynthesis(); } // ML scenes + synthesis
  if (state.nlData) renderNonlinear(state.nlData); // ML nonlinear
  if (state.cmpDone) runMlCompare();               // ML compare (backend text)
  if (state.fbData) renderForbidden(state.fbData); // ML forbidden
  if (rddReady) { drawSceneSurvIntro(); refreshRdd(); }  // RDD ② interactive
  if (state.rddSurv) renderRddSurvival(state.rddSurv);  // re-render cached survival (no recompute → no freeze)
  if (rddAnalyzeReady) {                                // RDD ③ data analysis
    const keepSurv = state.rddAnalyzeSurv;             // runRddAnalyze resets this
    await runRddAnalyze();                              // analyze+assumptions are light (~70 ms)
    if (keepSurv) {                                     // re-show a previously computed survival result
      state.rddAnalyzeSurv = keepSurv;
      renderRddAnalyzeSurv(keepSurv);
      const b = document.getElementById("runRddAnalyzeSurv");
      if (b) b.textContent = tr("重新計算設限校正", "Re-run censoring correction");
    }
  }
  if (rddAssumeReady) runRddAssumptions(rddState.req);  // RDD ④ assumptions (backend text)
  if (rddMlReady) { drawRddScenes(); refreshRddDml(); } // RDD ⑤ scenes + DML window-robustness
  if (state.rddSurvMl) {                                // RDD ⑤ survival (backend text)
    try {
      const d = await getJSON(`${API}/api/rdd_ml_survival?lang=${lang()}`);
      state.rddSurvMl = d; renderRddSurvMl(d);
    } catch (e) { /* ignore */ }
  }
  if (didLearnReady) drawSceneDidParallel();           // DiD ① learn scene
  if (didPlayReady) refreshDidPlay();                  // DiD ② interactive
  if (didAnalyzeReady) runDidAnalyze();                // DiD ③ analysis + dashboard
  else if (didAssumeReady) runDidAssumptions(didState.req);
  if (state.didDml) renderDidDml(state.didDml);        // DiD ⑤ real DML (re-render cached)
  if (titLearnReady) drawSceneTitFan();                // TiT ① learn scene
  if (titPlayReady) refreshTitPlay();                  // TiT ② interactive
  if (titAnalyzeReady) runTitAnalyze();                // TiT ③ analysis + dashboard
  else if (titAssumeReady) runTitAssumptions(titState.req);
  if (itsLearnReady) drawSceneItsExplain();            // ITS ① learn scene
  if (itsPlayReady) refreshItsPlay();                  // ITS ② interactive
  if (itsAnalyzeReady) runItsAnalyze();                // ITS ③ analysis + dashboard
  else if (itsAssumeReady) runItsAssumptions(itsState.req);
  if (state.itsMlcf) renderItsMlcf(state.itsMlcf);     // ITS ⑤ real ML counterfactual (re-render cached)
  if (perrLearnReady) drawScenePerr();                 // PERR ① learn scene
  if (perrPlayReady) refreshPerrPlay();                // PERR ② interactive
  if (perrAnalyzeReady) runPerrAnalyze();              // PERR ③ analysis + dashboard
  else if (perrAssumeReady) runPerrAssumptions(perrState.req);
  if (perrMlReady) refreshPerrMl();                    // PERR ⑤ scale sensitivity
  if (chooseReady) drawChooseChart();                  // six-method comparison chart
});

// initial render of interactive tab data
refreshPlay();
