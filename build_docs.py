"""把這個工具打包成可放上 GitHub Pages 的純靜態網站(輸出到 docs/)。

它不需要伺服器:所有計算改用 Pyodide 在瀏覽器裡跑(見 web/pyodide-bridge.js)。
單一來源原則 —— Python 仍然只有 backend/*.py + web/api.py;前端只有 frontend/* +
web/pyodide-bridge.js。docs/ 是「產生出來」的成品,改了來源後重跑這支程式即可。

用法:
    python build_docs.py
然後把 GitHub Pages 設成 main 分支的 /docs 目錄。
"""
from __future__ import annotations

import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
FRONTEND = os.path.join(HERE, "frontend")
BACKEND = os.path.join(HERE, "backend")
WEB = os.path.join(HERE, "web")
DOCS = os.path.join(HERE, "docs")

PYODIDE_SCRIPT = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js"
BACKEND_PY = ["i18n.py", "iv_core.py", "assumptions.py", "ml_iv.py", "gen_data.py",
              "rdd_core.py", "rdd_survival.py", "rdd_assumptions.py", "rdd_gen.py",
              "rdd_ml.py",
              "did_core.py", "did_gen.py", "did_assumptions.py", "did_ml.py",
              "tit_core.py", "tit_gen.py", "tit_assumptions.py",
              "its_core.py", "its_gen.py", "its_assumptions.py", "its_ml.py",
              "perr_core.py", "perr_gen.py", "perr_assumptions.py",
              "ccw_core.py", "ccw_gen.py", "ccw_assumptions.py"]


def _clean_docs():
    if os.path.isdir(DOCS):
        shutil.rmtree(DOCS)
    os.makedirs(os.path.join(DOCS, "py"), exist_ok=True)


def _build_index():
    with open(os.path.join(FRONTEND, "index.html"), encoding="utf-8") as f:
        html = f.read()

    # 1) 絕對路徑改成相對路徑(GitHub Pages 會掛在 /<repo>/ 子路徑底下)。
    #    用 regex 一併處理帶快取破壞查詢字串(?v=N)的版本,否則 /app.js?v=7
    #    這種帶問號的字串比對不到,會原封不動留下絕對路徑而在 Pages 上 404。
    html = re.sub(r'(href|src)="/(styles\.css|i18n\.js|app\.js)', r'\1="\2', html)

    # 2) 在 </head> 前注入 Pyodide 與橋接(必須在 app.js 之前先攔截 fetch)
    inject = (
        f'<script src="{PYODIDE_SCRIPT}"></script>\n'
        '<script src="pyodide-bridge.js?v=29"></script>\n'
        "<!-- 本檔由 build_docs.py 產生,請勿手改;來源為 frontend/index.html -->\n"
    )
    html = re.sub(r"</head>", inject + "</head>", html, count=1)

    with open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(html)


def _copy_assets():
    shutil.copyfile(os.path.join(FRONTEND, "app.js"), os.path.join(DOCS, "app.js"))
    shutil.copyfile(os.path.join(FRONTEND, "i18n.js"), os.path.join(DOCS, "i18n.js"))
    shutil.copyfile(os.path.join(FRONTEND, "styles.css"), os.path.join(DOCS, "styles.css"))
    shutil.copyfile(os.path.join(WEB, "pyodide-bridge.js"), os.path.join(DOCS, "pyodide-bridge.js"))

    # 靜態資產(logo 等):整個 frontend/assets 目錄原樣複製到 docs/assets
    assets_src = os.path.join(FRONTEND, "assets")
    if os.path.isdir(assets_src):
        shutil.copytree(assets_src, os.path.join(DOCS, "assets"))

    for name in BACKEND_PY:
        shutil.copyfile(os.path.join(BACKEND, name), os.path.join(DOCS, "py", name))
    shutil.copyfile(os.path.join(WEB, "api.py"), os.path.join(DOCS, "py", "api.py"))

    # .nojekyll 讓 GitHub Pages 不要用 Jekyll 處理(更快、且不過濾任何檔案)
    open(os.path.join(DOCS, ".nojekyll"), "w").close()


def main():
    _clean_docs()
    _build_index()
    _copy_assets()
    files = []
    for root, _dirs, names in os.walk(DOCS):
        for n in names:
            files.append(os.path.relpath(os.path.join(root, n), DOCS))
    print("已產生 docs/ :")
    for f in sorted(files):
        print("  docs/" + f.replace("\\", "/"))


if __name__ == "__main__":
    main()
