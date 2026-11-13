"""Build the project website (static HTML) into site/.

    python scripts/build_site.py                # -> site/index.html and friends
    python scripts/build_site.py --no-replays   # skip the episode replays (no models/data needed)
    python scripts/build_site.py --repo-url https://github.com/<owner>/<repo>

Renders the Markdown docs and result reports to HTML with one shared layout,
copies the result figures, writes a landing page with the headline numbers
read from the committed metrics, and regenerates visual replays of a few test
episodes with the current models. The GitHub Actions workflow
(.github/workflows/site.yml) runs this on every push to main and publishes
site/ to GitHub Pages.
"""

import argparse
import datetime
import glob
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# source markdown -> (output page, nav title)
PAGES = [
    ("HANDOFF.md", "handoff.html", "Handoff"),
    ("README.md", "overview.html", "Overview"),
    ("results/REPORT.md", "results.html", "Results"),
    ("docs/STATUS.md", "status.html", "Status"),
    ("docs/ARCHITECTURE.md", "architecture.html", "Architecture"),
    ("docs/LLM_SETUP.md", "llm-setup.html", "LLM setup"),
    ("docs/ENGINEERING_PLAN.md", "plan.html", "Plan"),
    ("docs/SUPERVISOR_REVIEW.md", "review.html", "Review log"),
    ("docs/VERIFICATION_CHECKLIST.md", "checklist.html", "Checklist"),
    ("docs/review/LATEST_PROGRESS_REVIEW.md", "latest-review.html", None),
    ("docs/review/HANDOFF_RESULTS.md", "handoff-results.html", None),
    ("LICENSES.md", "licenses.html", None),
]
RUN_REPORTS = [  # glob -> (page, title)
    ("results/runs/test-multi/REPORT.md", "results-multi.html", "Results: multi-component cuts"),
    ("results/runs/test-offline-cap1-*/REPORT.md", "results-cap1.html", "Results: 1 LLM call per turn"),
    ("results/runs/test-offline-cap2-*/REPORT.md", "results-cap2.html", "Results: 2 LLM calls per turn"),
]
NAV = [("index.html", "Home"), ("handoff.html", "Handoff"), ("overview.html", "Overview"),
       ("results.html", "Results"), ("replays.html", "Replays"), ("status.html", "Status"),
       ("architecture.html", "Architecture"), ("review.html", "Review log")]

CSS = """
:root{--bg:#fafaf9;--fg:#1c1917;--muted:#78716c;--card:#fff;--line:#e7e5e4;--accent:#1d4ed8;--code:#f5f5f4;--hl:#fef3c7}
@media (prefers-color-scheme:dark){:root{--bg:#1c1917;--fg:#f5f5f4;--muted:#a8a29e;--card:#292524;--line:#44403c;--accent:#93c5fd;--code:#0c0a09;--hl:#422006}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 system-ui,-apple-system,sans-serif}
header{border-bottom:1px solid var(--line);background:var(--card);position:sticky;top:0;z-index:5}
.bar{max-width:1100px;margin:0 auto;padding:10px 16px;display:flex;flex-wrap:wrap;gap:4px 16px;align-items:center}
.brand{font-weight:700;margin-right:8px;color:var(--fg);text-decoration:none}.bar a.n{color:var(--muted);text-decoration:none;font-size:14px}
.bar a.n.on,.bar a.n:hover{color:var(--accent)}main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}
a{color:var(--accent)}h1{font-size:28px;line-height:1.25}h2{margin-top:2em;padding-top:.4em;border-top:1px solid var(--line)}h3{margin-top:1.6em}
code{background:var(--code);padding:1px 5px;border-radius:4px;font-size:.9em}pre{background:var(--code);padding:12px;border-radius:8px;overflow-x:auto}
pre code{padding:0;background:none}table{border-collapse:collapse;display:block;overflow-x:auto;max-width:100%;margin:12px 0;font-size:14px}
th,td{border:1px solid var(--line);padding:5px 9px;vertical-align:top}th{background:var(--code);text-align:left}
img{max-width:100%;height:auto;border:1px solid var(--line);border-radius:8px;background:#fff}blockquote{margin:0;padding:6px 14px;border-left:4px solid var(--accent);background:var(--code)}
.foot{color:var(--muted);font-size:13px;margin-top:48px;border-top:1px solid var(--line);padding-top:12px}
.hero p{font-size:17px;max-width:760px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin:18px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;text-decoration:none;color:var(--fg)}
.card b{display:block;margin-bottom:4px;color:var(--accent)}.card span{color:var(--muted);font-size:14px}
.note{background:var(--hl);padding:8px 12px;border-radius:8px;font-size:14px}
"""


def git(*args, default=""):
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return default


def layout(title, body, active, repo_url, sha, built):
    nav = "".join(f'<a class="n{" on" if href == active else ""}" href="{href}">{label}</a>' for href, label in NAV)
    src = f' · <a href="{repo_url}">source</a>' if repo_url else ""
    commit = f'<a href="{repo_url}/commit/{sha}">{sha}</a>' if repo_url and sha else (sha or "local build")
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title)} · TaskFlow-Travel</title><style>{CSS}</style></head><body>"
            f"<header><div class=bar><a class=brand href=index.html>TaskFlow-Travel</a>{nav}</div></header>"
            f"<main>{body}<div class=foot>Built from commit {commit} on {built}{src}. "
            f"This site is regenerated automatically on every push to main.</div></main></body></html>")


class Linker:
    """Rewrites links between Markdown files to site pages, everything else to the repo."""

    def __init__(self, page_of: dict, repo_url: str, images: dict):
        self.page_of, self.repo_url, self.images = page_of, repo_url, images

    def __call__(self, src_md: Path, body: str) -> str:
        def fix(m):
            attr, target = m.group(1), m.group(2)
            if re.match(r"^(https?:|mailto:|#)", target):
                return m.group(0)
            path, _, frag = target.partition("#")
            resolved = (src_md.parent / path).resolve()
            try:
                rel = resolved.relative_to(ROOT).as_posix()
            except ValueError:
                return m.group(0)
            if rel in self.page_of:
                new = self.page_of[rel] + (f"#{frag}" if frag else "")
            elif rel in self.images:
                new = self.images[rel]
            elif self.repo_url:
                kind = "tree" if resolved.is_dir() else "blob"
                new = f"{self.repo_url}/{kind}/main/{rel}" + (f"#{frag}" if frag else "")
            else:
                return m.group(0)
            return f'{attr}="{new}"'

        return re.sub(r'(href|src)="([^"]+)"', fix, body)


def render_md(path: Path) -> str:
    return markdown.markdown(path.read_text(), extensions=["tables", "fenced_code", "toc", "sane_lists"])


def headline(repo_url: str) -> str:
    """Key numbers straight from the committed metrics files."""
    try:
        main = json.loads((ROOT / "results/metrics.json").read_text())["systems"]
        cap1 = json.loads(Path(glob.glob(str(ROOT / "results/runs/test-offline-cap1-*/metrics.json"))[0]).read_text())["systems"]
        multi = json.loads((ROOT / "results/runs/test-multi/metrics.json").read_text())["systems"]
    except (FileNotFoundError, IndexError, KeyError):
        return "<p>Results not built yet.</p>"
    g = lambda d, n, k: d.get(n, {}).get("summary", {}).get(k, {}).get("mean")  # noqa: E731
    rows = [("Learned (BC + aug + DAgger)", "bc_aug_dagger3"), ("Static rules (cost-aware)", "static_cost_aware"),
            ("Static rules", "static_rules"), ("Always regenerate", "always_global")]
    def pct(x):
        return "–" if x is None else f"{100 * x:.1f}%"
    def num(x):
        return "–" if x is None else f"{x:.2f}"
    out = ["<table><tr><th>Coordinator</th><th>Revision success</th><th>LLM calls / turn</th>"
           "<th>Success with 1 LLM call / turn</th><th>Excess edits, multi-component cuts</th></tr>"]
    for label, key in rows:
        out.append(f"<tr><td>{label}</td><td>{pct(g(main, key, 'revision_success_rate'))}</td>"
                   f"<td>{num(g(main, key, 'llm_calls_per_turn'))}</td><td>{pct(g(cap1, key, 'revision_success_rate'))}</td>"
                   f"<td>{num(g(multi, key, 'excess_edits_per_turn'))}</td></tr>")
    out.append("</table><p class=note>Offline numbers: deterministic agents and a simulated LLM cost model. "
               "They still need confirming with real LLM agents (see the Handoff, task H4).</p>")
    return "".join(out)


REPLAYS = [
    ("replay-test.html", "test", None, "A 4-turn conversation from the held-out test set"),
    ("replay-multi-2.html", "test_multi", "L2", "A budget cut that needs two components changed"),
    ("replay-multi-3.html", "test_multi", "L3", "A budget cut that needs three components changed"),
    ("replay-impossible.html", "test_multi", "L0", "An impossible budget cut (the right answer is to ask)"),
]


def build_replays(out: Path) -> list[tuple[str, str]]:
    from taskflow.common import TASKS_DIR
    from taskflow.data.tasks import load

    made = []
    for page, split, level, desc in REPLAYS:
        cmd = [sys.executable, str(ROOT / "scripts/demo_html.py"), "--no-open", "--split", split,
               "--out", str(out / page)]
        if level:
            ep = next((e for e in load(TASKS_DIR, split) if e.episode_id.endswith(f"-{level}")), None)
            if ep is None:
                continue
            cmd += ["--episode", ep.episode_id]
        subprocess.run(cmd, check=True, cwd=ROOT, stdout=subprocess.DEVNULL)
        text = (out / page).read_text()
        text = text.replace("<main>", "<main><p><a href='replays.html'>← All replays</a> · "
                                      "<a href='index.html'>TaskFlow-Travel home</a></p>", 1)
        (out / page).write_text(text)
        made.append((page, desc))
    return made


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "site")
    ap.add_argument("--repo-url", default=None, help="defaults to the git remote 'origin'")
    ap.add_argument("--no-replays", action="store_true")
    a = ap.parse_args()
    repo_url = a.repo_url
    if repo_url is None:
        remote = git("remote", "get-url", "origin")
        m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", remote)
        repo_url = f"https://github.com/{m.group(1)}" if m else ""
    sha = git("rev-parse", "--short", "HEAD")
    built = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out = a.out
    if out.exists():
        shutil.rmtree(out)
    (out / "img").mkdir(parents=True)

    # Images referenced by reports
    images = {}
    for png in list((ROOT / "results").glob("*.png")) + list((ROOT / "results/runs").glob("*/*.png")):
        rel = png.relative_to(ROOT).as_posix()
        name = rel.replace("/", "_")
        shutil.copy(png, out / "img" / name)
        images[rel] = f"img/{name}"

    page_of = {src: page for src, page, _ in PAGES}
    run_pages = []
    for pattern, page, title in RUN_REPORTS:
        hits = sorted(glob.glob(str(ROOT / pattern)))
        if hits:
            rel = Path(hits[-1]).relative_to(ROOT).as_posix()
            page_of[rel] = page
            run_pages.append((rel, page, title))
    link = Linker(page_of, repo_url, images)

    for src, page, _title in PAGES + [(r, p, t) for r, p, t in run_pages]:
        p = ROOT / src
        if not p.exists():
            continue
        body = link(p, render_md(p))
        title = re.search(r"<h1[^>]*>(.*?)</h1>", body)
        title = re.sub("<.*?>", "", title.group(1)) if title else (_title or page)
        active = page if page in dict(NAV) else ("results.html" if page.startswith("results") else "")
        (out / page).write_text(layout(title, body, active, repo_url, sha, built))

    replays = [] if a.no_replays else build_replays(out)
    items = "".join(f"<a class=card href='{p}'><b>{html.escape(d)}</b><span>Every coordinator side by side, "
                    f"changed slots highlighted</span></a>" for p, d in replays) or "<p>Replays not built.</p>"
    (out / "replays.html").write_text(layout("Replays", (
        "<h1>Episode replays</h1><p>Recorded episodes from the test data, regenerated with the current models on "
        "every push. For the interactive version, where you type any start city and destination, run "
        "<code>make app</code> locally (it needs a Python server, so it can't run on this static site).</p>"
        f"<div class=cards>{items}</div>"), "replays.html", repo_url, sha, built))

    extra = "".join(f"<a class=card href='{p}'><b>{html.escape(t)}</b><span>Full report</span></a>"
                    for _, p, t in run_pages)
    index = f"""<div class=hero><h1>TaskFlow-Travel</h1>
<p>Imitation-learned coordination for multi-agent travel replanning under evolving user constraints.
A user keeps revising a 3-day itinerary; after each change a coordinator decides whether to keep the plan, ask,
search, repair one component, or rebuild. We train a small coordinator by behavior cloning, trajectory
augmentation and DAgger, and compare it with hand-written rules and full regeneration on TravelPlanner data.</p></div>
<div class=cards>
<a class=card href=handoff.html><b>Handoff</b><span>Everything done so far, what's left, how to run it</span></a>
<a class=card href=results.html><b>Results</b><span>Main benchmark report and figures</span></a>
<a class=card href=replays.html><b>Replays</b><span>Watch coordinators handle real test episodes</span></a>
<a class=card href=overview.html><b>Overview</b><span>Quickstart, results summary, caveats</span></a>
<a class=card href=architecture.html><b>Architecture</b><span>How the code fits together</span></a>
<a class=card href=review.html><b>Review log</b><span>Independent review findings and fixes</span></a>
{extra}
<a class=card href="{repo_url}"><b>Source code</b><span>{html.escape(repo_url or 'repository')}</span></a>
</div>
<h2>Headline numbers (test split)</h2>{headline(repo_url)}
<h2>Run it yourself</h2>
<pre><code>git clone {html.escape(repo_url or '<repo>')}.git
cd {html.escape((repo_url or 'taskflow-travel').rstrip('/').split('/')[-1])}
make setup test
make app        # interactive web app at http://localhost:8566</code></pre>"""
    (out / "index.html").write_text(layout("Home", index, "index.html", repo_url, sha, built))
    (out / ".nojekyll").write_text("")
    print(f"wrote {out} ({len(list(out.rglob('*.html')))} pages)")


if __name__ == "__main__":
    main()
