"use strict";

// ======================================================================
// Tiny bilingual engine (中文 default ⇄ English)
//
// Static text lives co-located in the HTML: the Chinese is the element's
// innerHTML, the English is in a `data-en="..."` attribute. Swapping only
// touches text, so interactive elements + event listeners survive.
//
// Dynamic text (built in app.js) uses IV.tr(zh, en). After a switch we fire
// the `iv-lang` event so app.js can re-fetch / re-render dynamic content.
// ======================================================================

(function () {
  const KEY = "iv-lang";
  const saved = (function () {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }
  })();

  const IV = {
    lang: saved === "en" ? "en" : "zh",
    tr(zh, en) { return this.lang === "en" ? en : zh; },
  };
  window.IV = IV;

  // --- the document-level bits that aren't covered by [data-en] ---
  const TITLE = { zh: "準實驗工具箱：IV · RDD · DiD · TiT · ITS · PERR · CCW",
                  en: "Quasi-experimental Toolbox: IV · RDD · DiD · TiT · ITS · PERR · CCW" };
  const HTMLLANG = { zh: "zh-Hant", en: "en" };
  const BTN = { zh: "EN", en: "中文" };          // button shows the OTHER language
  const BTNTITLE = { zh: "切換到英文", en: "切換到中文" };

  function applyStatic(lang) {
    document.querySelectorAll("[data-en]").forEach((el) => {
      // First time we touch an element, stash its original (Chinese) markup.
      if (el.dataset.zh === undefined) el.dataset.zh = el.innerHTML;
      el.innerHTML = lang === "en" ? el.dataset.en : el.dataset.zh;
    });
    document.title = TITLE[lang];
    document.documentElement.lang = HTMLLANG[lang];
    const btn = document.getElementById("langToggle");
    if (btn) { btn.textContent = BTN[lang]; btn.title = BTNTITLE[lang]; }
  }

  function setLang(lang) {
    IV.lang = lang === "en" ? "en" : "zh";
    try { localStorage.setItem(KEY, IV.lang); } catch (e) { /* ignore */ }
    applyStatic(IV.lang);
    // Let app.js re-render any dynamic (JS-built) content in the new language.
    window.dispatchEvent(new CustomEvent("iv-lang", { detail: { lang: IV.lang } }));
  }
  IV.setLang = setLang;

  function init() {
    const btn = document.getElementById("langToggle");
    if (btn) btn.addEventListener("click", () => setLang(IV.lang === "en" ? "zh" : "en"));
    applyStatic(IV.lang);            // honour the saved choice on load
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
