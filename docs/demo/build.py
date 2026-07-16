"""Build the browser demo page: copy yoda/static/index.html and inject
(1) a demo banner, (2) the Pyodide loader + api() shim that routes every
backend call into demo_shim.py running in WebAssembly.

Run from repo root:  python docs/demo/build.py
Idempotent — regenerates docs/demo/index.html and copies the current wheel.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "docs" / "demo"
SRC = ROOT / "yoda" / "static" / "index.html"

BANNER_CSS = """
  #demo-banner{background:var(--surface-2);border-bottom:1px solid var(--accent);
    padding:.5rem .9rem;font-size:.7rem;line-height:1.5;color:var(--text);
    display:flex;gap:.8rem;align-items:center;flex-wrap:wrap}
  #demo-banner b{color:var(--accent)}
  #demo-banner a{color:var(--accent-2)}
  #demo-status{color:var(--warn)}
  #btn-sample{font:inherit;font-size:.68rem;color:var(--bg);background:var(--accent);
    border:none;border-radius:var(--r);padding:.25rem .7rem;cursor:pointer;font-weight:700}
"""

BANNER_HTML = """
<div id="demo-banner">
  <span><b>BROWSER DEMO</b> — the whole pipeline runs in <b>your</b> browser via
  WebAssembly. Files you load never leave your machine (same guarantee as the
  real tool). The AI planner needs a local install with Ollama; this demo uses
  the deterministic rule-based planner.
  <a href="https://github.com/Zeref538/yoda" target="_blank" rel="noopener">Get the real thing →</a></span>
  <button id="btn-sample" disabled>Load sample messy CSV</button>
  <span id="demo-status">loading…</span>
</div>
"""

SHIM_JS = """
<script src="https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js"></script>
<script>
/* ---- YODA browser demo: route api() into Pyodide instead of fetch ---- */
let _dispatch = null;
const _pyReady = (async ()=>{
  const say = t => { const s = document.getElementById("demo-status");
                     if(s) s.textContent = t; };
  try{
    say("loading Python runtime…");
    const py = await loadPyodide();
    say("loading pandas (~15 MB, cached after first visit)…");
    await py.loadPackage(["pandas","micropip","sqlite3"]);
    say("installing YODA…");
    const wheel = document.querySelector('meta[name="demo-wheel"]').content;
    await py.runPythonAsync(`
import micropip
await micropip.install(["python-dateutil","jsonschema","openpyxl","pyyaml"])
await micropip.install("${new URL(wheel, location.href).href}", deps=False)
`);
    const shim = await (await fetch("demo_shim.py")).text();
    py.FS.writeFile("demo_shim.py", shim);
    await py.runPythonAsync("import demo_shim");
    _dispatch = py.pyimport("demo_shim").dispatch;
    say("ready — load a file or use the sample.");
    const b = document.getElementById("btn-sample");
    b.disabled = false;
    setTimeout(()=>{ const s=document.getElementById("demo-status");
                     if(s) s.textContent=""; }, 6000);
    return py;
  }catch(err){ say("demo failed to load: " + err.message); throw err; }
})();

window.api = async function(url, opts={}){
  await _pyReady;
  const u = new URL(url, location.href);
  const path = "/api/" + u.pathname.split("/api/").pop();
  const query = Object.fromEntries(u.searchParams.entries());
  const method = (opts.method || "GET").toUpperCase();
  let bodyJson = "null", fileName = "", fileBytes = null;
  if(opts.body instanceof FormData){
    const f = opts.body.get("file");
    fileName = f.name;
    fileBytes = new Uint8Array(await f.arrayBuffer());
  }else if(typeof opts.body === "string"){ bodyJson = opts.body; }
  const proxy = await _dispatch(method, path, JSON.stringify(query),
                                bodyJson, fileName, fileBytes);
  const res = proxy.toJs({dict_converter: Object.fromEntries});
  proxy.destroy();
  if(res.status >= 400){
    let detail = "error";
    try{ detail = JSON.parse(res.data).detail; }catch(_e){}
    throw new Error(detail);
  }
  return {
    ok: true,
    json: async ()=> JSON.parse(res.data),
    text: async ()=> res.data,
    blob: async ()=> new Blob([res.data],
      {type: res.media_type || "application/octet-stream"}),
    _demo: res,
  };
};

/* download links (<a href="/api/download…">) -> in-browser blob downloads */
document.addEventListener("click", async e=>{
  const a = e.target.closest('a[href^="/api/"]');
  if(!a) return;
  e.preventDefault();
  try{
    const r = await api(a.getAttribute("href"));
    const url = URL.createObjectURL(await r.blob());
    const tmp = document.createElement("a");
    tmp.href = url; tmp.download = r._demo.filename || "download";
    document.body.appendChild(tmp); tmp.click(); tmp.remove();
    URL.revokeObjectURL(url);
  }catch(err){ if(typeof toast === "function") toast(err.message); }
}, true);

/* sample data button */
document.getElementById("btn-sample").addEventListener("click", async ()=>{
  const blob = await (await fetch("sample_messy.csv")).blob();
  upload(new File([blob], "sample_messy.csv", {type: "text/csv"}));
});
</script>
"""


def main() -> None:
    html = SRC.read_text(encoding="utf-8")
    wheel = sorted((ROOT / "dist").glob("yoda_agent-*-py3-none-any.whl"))[-1]
    shutil.copy(wheel, DEMO / wheel.name)

    html = html.replace("</head>",
                        f'<meta name="demo-wheel" content="{wheel.name}">\n'
                        f"<style>{BANNER_CSS}</style>\n</head>")
    html = re.sub(r"(<body[^>]*>)", r"\1" + BANNER_HTML, html, count=1)
    html = html.replace("</body>", SHIM_JS + "\n</body>")
    (DEMO / "index.html").write_text(html, encoding="utf-8")
    print(f"wrote {DEMO / 'index.html'}  (wheel: {wheel.name})")


if __name__ == "__main__":
    main()
