"use strict";

const API = "";  // same origin
const state = {
  source: null, columns: [], numeric: [],
  // remembered inputs/outputs so a language switch can re-render
  lastReq: null, nlData: null, fbData: null, cmpDone: false,
};
const tr = (zh, en) => window.IV.tr(zh, en);
const lang = () => window.IV.lang;

// ----- tab switching -----
document.querySelectorAll(".tab").forEach((t) => {
  t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    document.getElementById(t.dataset.tab).classList.add("active");
    if (t.dataset.tab === "play") refreshPlay();
    if (t.dataset.tab === "ml") initMl();
    if (t.dataset.tab === "rddplay") initRdd();
    if (t.dataset.tab === "rddanalyze") initRddAnalyze();
    if (t.dataset.tab === "rddassume") initRddAssume();
    if (t.dataset.tab === "rddml") initRddMl();
    if (t.dataset.tab === "choose") initChoose();
  });
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
  refreshChoose();
}
async function refreshChoose() {
  let iv, rd;
  try {
    iv = await postJSON(`${API}/api/analyze`, {
      source: "example", outcome: "health_score_change", treatment: "vaccinated",
      instrument: "vaccine_reminder", covariates: [], lang: lang(),
    });
    rd = await postJSON(`${API}/api/rdd_analyze`, { source: "example_rdd", lang: lang() });
  } catch (e) { return; }
  state.chooseDone = true;
  renderChoose(iv, rd);
}
function renderChoose(iv, rd) {
  const labels = [
    tr("IV：天真", "IV: naive"), tr("IV：2SLS", "IV: 2SLS"),
    tr("RDD：天真", "RDD: naive"), tr("RDD：模糊", "RDD: fuzzy"),
  ];
  const vals = [iv.naive.estimate, iv.iv.estimate, rd.naive_difference, rd.fuzzy.estimate];
  const colors = [RED, "#6366f1", RED, PURPLE];
  Plotly.react("chooseChart", [{
    x: labels, y: vals, type: "bar", marker: { color: colors },
    text: vals.map((v) => fmt(v, 2)), textposition: "outside",
  }], {
    margin: { t: 30, r: 20, b: 60, l: 50 },
    yaxis: { title: tr("估出的疫苗效果", "Estimated vaccine effect"), range: [0, 3] },
    shapes: [
      { type: "line", x0: -0.5, x1: 3.5, y0: 1.8, y1: 1.8,
        line: { color: GREEN, dash: "dash", width: 2 } },
      { type: "line", x0: 1.5, x1: 1.5, yref: "paper", y0: 0, y1: 1,
        line: { color: "#cbd5e1", width: 1 } },
    ],
    annotations: [{ x: 3, y: 1.8, text: tr("真值 1.80", "truth 1.80"),
      showarrow: false, font: { color: GREEN }, yshift: 12 }],
  }, { displayModeBar: false, responsive: true });
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
  if (state.chooseDone) refreshChoose();                // IV vs RDD comparison
});

// initial render of interactive tab data
refreshPlay();
