"""React + Vite + TypeScript output. Same section pipeline as HTML mode: the model returns section html/css, the engine keeps those
as the source of truth in .agent/parts/ and derives src/sections/<Name>.tsx (+ .css) deterministically. Build is verified for real
(npm install -> tsc --noEmit && vite build) and the built `dist/` is what the browser tests and the live preview use."""
import json
import re
import shutil
from html import escape

from backend.agent import context
from backend.engines import animation_engine, design_engine, html2jsx
from backend.engines import code_engine as ce
from backend.tools import terminal

PKG = {
    "name": "generated-site", "private": True, "version": "0.1.0", "type": "module",
    "scripts": {"dev": "vite", "build": "tsc --noEmit && vite build", "typecheck": "tsc --noEmit", "preview": "vite preview"},
    "dependencies": {"react": "^18.3.1", "react-dom": "^18.3.1"},
    "devDependencies": {"@types/react": "^18.3.3", "@types/react-dom": "^18.3.0", "@vitejs/plugin-react": "^4.3.1",
                        "typescript": "^5.5.4", "vite": "^5.4.0"},
}
STATIC = ["vite.config.ts", "tsconfig.json", "src/main.tsx", "src/lib/motion.ts", "src/lib/MotionEffects.tsx", "src/vite-env.d.ts"]


def pascal(sid: str) -> str:
    n = "".join(w.capitalize() for w in re.split(r"[^a-z0-9]+", sid.lower()) if w) or "Section"
    return n if n[0].isalpha() else "S" + n


def _component(name: str, body: str, css_file: str | None) -> str:
    imp = f"import './{css_file}'\n\n" if css_file else ""
    return f"{imp}export default function {name}() {{\n  return (\n    <>\n      {body}\n    </>\n  )\n}}\n"


def restore_static(pf) -> list[str]:
    """Zero-token repair: rewrite any missing scaffold file (vite/tsconfig/main.tsx/lib/*) from the templates."""
    restored = []
    for rel in STATIC:
        if not (pf.root / rel).is_file():
            pf.write(rel, ce._tpl(f"react/{rel}"))
            restored.append(rel)
    return restored


def scaffold(pf, state) -> None:
    for rel in STATIC:
        pf.write(rel, ce._tpl(f"react/{rel}"))
    pf.write("package.json", json.dumps(PKG, indent=2) + "\n")
    pf.write(".gitignore", "node_modules\ndist\n")
    pf.write("src/styles/tokens.css", design_engine.render_tokens(state.design) + animation_engine.css_vars(state.motion))
    pf.write("src/styles/base.css", ce.base_css(state.plan.get("layout", "landing")))
    pf.write("src/styles/animations.css", ce._tpl("animation/animations.css"))
    pf.write("src/styles/reduced.css", ce.RM)
    brand = state.plan.get("brand") or "Brand"
    nav, footer = ce.nav_footer(state.plan.get("layout", "landing"), brand, state.plan["sections"])
    pf.write("src/components/Nav.tsx", _component("Nav", html2jsx.convert(nav), None))
    pf.write("src/components/Footer.tsx", _component("Footer", html2jsx.convert(footer), None))
    fonts = design_engine.fonts_link(state.design)
    pf.write("index.html", ce._tpl("react/index.html").replace("{{TITLE}}", escape(brand)).replace("{{FONTS}}", fonts))
    _write_app(pf, state)


def _present(pf, state) -> list[str]:
    return [s for s in state.plan["sections"] if (pf.root / "src" / "sections" / f"{pascal(s)}.tsx").is_file()]


def _write_app(pf, state) -> None:
    if state.plan.get("layout") == "app":
        from backend.engines import app_engine
        app_engine.generate(pf, state)
        return
    secs = _present(pf, state)
    layout = state.plan.get("layout", "landing")
    imports = "".join(f"import {pascal(s)} from './sections/{pascal(s)}'\n" for s in secs)
    shell_open, shell_close = ("<div className=\"shell\">\n      <Nav />\n      <div className=\"dash-main\">\n        <main>", "</main>\n      </div>\n    </div>") \
        if layout == "dashboard" else ("<Nav />\n      <main>", "</main>\n      <Footer />")
    body = "\n          ".join(f"<{pascal(s)} />" for s in secs)
    app = (f"import './styles/tokens.css'\nimport './styles/base.css'\nimport './styles/animations.css'\n"
           f"import Nav from './components/Nav'\nimport Footer from './components/Footer'\n{imports}"
           f"import './styles/reduced.css'\n\nexport default function App() {{\n  return (\n    <>\n      "
           f"{shell_open}\n          {body}\n        {shell_close}\n    </>\n  )\n}}\n")
    pf.write("src/App.tsx", app)


def insert(pf, state, sid: str, html: str, css: str) -> None:
    html, css = ce.clean_html(html), ce.clean_css(css)
    if not ce._has_id(html, sid):
        html = f'<div id="{sid}">{html}</div>'
    pf.write(f".agent/parts/{sid}.html", html)
    pf.write(f".agent/parts/{sid}.css", css)
    name = pascal(sid)
    pf.write(f"src/sections/{sid}.css", css)
    pf.write(f"src/sections/{name}.tsx", _component(name, html2jsx.convert(html), f"{sid}.css"))
    _write_app(pf, state)


def get_section(pf, sid: str):
    def rd(ext):
        try:
            return pf.read(f".agent/parts/{sid}.{ext}")
        except FileNotFoundError:
            return ""
    return rd("html").strip(), rd("css")


# ---------------------------------------------------------------------------------------------- build verification
SEC_FILE = re.compile(r"src/sections/([A-Za-z0-9]+)\.(?:tsx|css)")


def sid_from_output(text: str, state) -> str | None:
    m = SEC_FILE.search(text)
    if not m:
        return None
    for s in state.plan.get("sections", []):
        if pascal(s) == m.group(1):
            return s
    return None


def build(pf, state) -> dict:
    """Real build. Returns {issues, checks, note}. Missing tools => 'skipped' + an issue (never a fake pass)."""
    checks, issues = [], []

    def chk(name, status, detail=""):
        checks.append({"name": name, "viewport": "build", "status": status, "detail": detail})

    if not shutil.which("node") or not shutil.which("npm"):
        msg = "node/npm not found: React build, type check and browser tests could not run (install Node.js 18+)"
        for n in ("npm install", "type check", "production build"):
            chk(n, "skipped", msg)
        return {"issues": [{"sid": None, "msg": msg}], "checks": checks, "note": msg, "built": False}
    cwd = str(pf.root)
    if not (pf.root / "node_modules" / "vite").is_dir():
        context.progress("build", "npm install (first run can take a few minutes)")
        r = terminal.run(["npm", "install", "--no-audit", "--no-fund", "--prefer-offline"], cwd, timeout=900, max_out=1500)
        if r["code"] != 0:
            msg = f"npm install failed (code {r['code']}): {r['out'][-300:]}"
            chk("npm install", "failed", msg[:200])
            for n in ("type check", "production build"):
                chk(n, "skipped", "npm install failed")
            return {"issues": [{"sid": None, "msg": msg}], "checks": checks, "note": "npm install failed", "built": False}
    chk("npm install", "passed")
    context.progress("build", "tsc --noEmit && vite build")
    r = terminal.run(["npm", "run", "build"], cwd, timeout=300, max_out=6000)
    out = r["out"]
    if r["code"] == 0:
        chk("type check", "passed")
        chk("production build", "passed")
        return {"issues": [], "checks": checks, "note": "ok", "built": True}
    errs = [ln.strip() for ln in out.splitlines() if re.search(r"error|Error|✘|ERROR", ln)][:8] or [out[-300:]]
    ts = any("error TS" in ln for ln in errs)
    chk("type check", "failed" if ts else "passed", errs[0][:200] if ts else "")
    chk("production build", "skipped" if ts else "failed", "not executed: type check failed" if ts else errs[0][:200])
    for ln in errs[:6]:
        issues.append({"sid": sid_from_output(ln, state), "msg": f"build: {ln[:220]}"})
    return {"issues": issues, "checks": checks, "note": "build failed", "built": False}
