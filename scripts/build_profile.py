"""Rebuild the floating-bubbles project graphic for the profile README.

Reads your public repos from the GitHub API, draws one bubble per repo into
assets/repo-bubbles.svg, and refreshes the repo / live counts in the README
(between the COUNT and LIVE markers). Run by .github/workflows/update-profile.yml.
"""

import json
import os
import re
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

USER = os.environ.get("PROFILE_USER", "ivanedens55-web")
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "repo-bubbles.svg"
README = ROOT / "README.md"

# Optional: override the small line under a repo's name.
SUBTITLES = {
    "llm-response-evaluator": "LLM-as-judge",
    "labellint": "label auditing",
}

# Tech names to look for in a repo's description/topics, in display order.
TECH = [
    ("FastAPI", r"fastapi"), ("Flask", r"flask"), ("Gemini", r"gemini"),
    ("Streamlit", r"streamlit"), ("Next.js", r"next\.?js"), ("PostgreSQL", r"postgres(?:ql)?"),
    ("Supabase", r"supabase"), ("React", r"\breact\b"), ("Tailwind", r"tailwind"),
]
AI_WORDS = re.compile(r"\b(ai|llm|llms|gemini|openai|gpt)\b", re.I)
AI_TOPICS = {"ai", "llm", "gemini", "gemini-api", "openai", "llm-evaluation", "machine-learning", "rag"}

GOLD, VIOLET, GREEN = "#F5B700", "#a78bfa", "#34d058"
FONT = "'Segoe UI',-apple-system,'Helvetica Neue',Arial,sans-serif"
R, W = 72, 800
AI_PER_ROW, APP_PER_ROW = 4, 3
AI_GAP, APP_GAP, ROW_H = 180, 210, 170


def fetch_repos():
    """Public, non-fork, non-archived repos, most recently pushed first."""
    url = f"https://api.github.com/users/{USER}/repos?per_page=100&sort=pushed"
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=30) as response:
        repos = json.load(response)
    return [r for r in repos if not (r["fork"] or r["archived"] or r["private"] or r["name"] == USER)]


def is_ai(repo):
    text = f'{repo["name"]} {repo.get("description") or ""}'
    return bool(AI_TOPICS & set(repo.get("topics", []))) or bool(AI_WORDS.search(text))


def subtitle(repo):
    if repo["name"] in SUBTITLES:
        return SUBTITLES[repo["name"]]
    text = f'{repo.get("description") or ""} {" ".join(repo.get("topics", []))}'
    found = [label for label, pattern in TECH if re.search(pattern, text, re.I)]
    return " · ".join(found[:2]) or repo.get("language") or ""


def name_lines(name, limit=16):
    parts = name.split("-")
    lines, current = [], ""
    for i, part in enumerate(parts):
        piece = part + ("-" if i < len(parts) - 1 else "")
        if current and len(current + piece) > limit:
            lines.append(current)
            current = piece
        else:
            current += piece
    lines.append(current)
    return lines


def rows(items, per_row, gap, y0):
    """Centre each row of items on the canvas; returns (item, x, y) tuples."""
    placed = []
    for r in range(0, len(items), per_row):
        chunk = items[r:r + per_row]
        start = W / 2 - gap * (len(chunk) - 1) / 2
        for i, item in enumerate(chunk):
            placed.append((item, round(start + i * gap), y0 + (r // per_row) * ROW_H))
    return placed


def bubble(index, repo, x, y, kind):
    ring, halo = ("rG", "hG") if kind == "ai" else ("rV", "hV")
    lines = name_lines(repo["name"])
    sub = subtitle(repo)
    total = len(lines) * 17 + (21 if sub else 0)
    top = -total / 2
    text = "".join(
        f'<text x="0" y="{top + (j + 1) * 17 - 3:.1f}" text-anchor="middle" fill="#fff" font-size="14" font-weight="700">{escape(t)}</text>'
        for j, t in enumerate(lines)
    )
    if sub:
        text += f'<text x="0" y="{top + len(lines) * 17 + 19:.1f}" text-anchor="middle" fill="#b4afe0" font-size="11">{escape(sub)}</text>'
    live = ""
    if repo.get("homepage"):
        live = f'<circle class="lv" cx="{R * 0.71:.0f}" cy="{-R * 0.71:.0f}" r="6" fill="{GREEN}" stroke="#0d0b24" stroke-width="2.5"/>'
    css = f".b{index}{{animation:fl {6 + (index % 4) * 0.4:.1f}s ease-in-out {-index * 0.9:.1f}s infinite}}"
    shape = (
        f'<g transform="translate({x} {y})"><g class="b{index}">'
        f'<circle r="{R + 16}" fill="url(#{halo})"/>'
        f'<circle r="{R}" fill="url(#glass)" stroke="url(#{ring})" stroke-width="2.5"/>{text}{live}</g></g>'
    )
    return css, shape


def section(y, color, label):
    width = len(label) * 8.6 + 22
    return (
        f'<circle cx="46" cy="{y - 5}" r="5" fill="{color}"/>'
        f'<text x="60" y="{y}" fill="{color}" font-size="15" font-weight="700">{escape(label)}</text>'
        f'<line x1="{60 + width:.0f}" y1="{y - 5}" x2="760" y2="{y - 5}" stroke="#fff" stroke-opacity=".12"/>'
    )


def build_svg(repos):
    ai = [r for r in repos if is_ai(r)]
    apps = [r for r in repos if not is_ai(r)]
    live_total = sum(1 for r in repos if r.get("homepage"))
    css, shapes, labels = [], [], []
    y = 135
    index = 0
    for group, per_row, gap, color, title in (
        (ai, AI_PER_ROW, AI_GAP, GOLD, "AI & evaluation"),
        (apps, APP_PER_ROW, APP_GAP, VIOLET, None),
    ):
        if not group:
            continue
        if title is None:
            live = sum(1 for r in group if r.get("homepage"))
            title = "Full-stack apps · " + ("all live" if live == len(group) else f"{live} live")
        labels.append(section(y, color, title))
        kind = "ai" if color == GOLD else "app"
        for repo, x, cy in rows(group, per_row, gap, y + 90):
            index += 1
            c, s = bubble(index, repo, x, cy, kind)
            css.append(c)
            shapes.append(s)
        y += 90 + ((len(group) - 1) // per_row) * ROW_H + 125
    height = y - 20
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {height}" width="{W}" height="{height}" font-family="{FONT}" role="img" aria-label="My {len(repos)} public repositories as floating bubbles">
<defs>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0d0b24"/><stop offset="1" stop-color="#1b1647"/></linearGradient>
<radialGradient id="glass" cx=".32" cy=".25" r=".95"><stop offset="0" stop-color="#2a2566"/><stop offset="1" stop-color="#120f33"/></radialGradient>
<linearGradient id="rG" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffd84d"/><stop offset="1" stop-color="#d98e00"/></linearGradient>
<linearGradient id="rV" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#c4b5fd"/><stop offset="1" stop-color="#7c5ce6"/></linearGradient>
<radialGradient id="hG"><stop offset=".7" stop-color="{GOLD}" stop-opacity=".16"/><stop offset="1" stop-color="{GOLD}" stop-opacity="0"/></radialGradient>
<radialGradient id="hV"><stop offset=".7" stop-color="{VIOLET}" stop-opacity=".18"/><stop offset="1" stop-color="{VIOLET}" stop-opacity="0"/></radialGradient>
</defs>
<style>
@keyframes fl{{0%,100%{{transform:translateY(0)}}50%{{transform:translateY(-7px)}}}}
{chr(10).join(css)}
.lv{{animation:pu 2s ease-in-out infinite}}
@keyframes pu{{0%,100%{{opacity:1}}50%{{opacity:.35}}}}
@media (prefers-reduced-motion:reduce){{[class^="b"],.lv{{animation:none}}}}
</style>
<rect width="{W}" height="{height}" rx="22" fill="url(#bg)"/>
<text x="40" y="58" fill="#fff" font-size="28" font-weight="800">Projects</text>
<text x="40" y="82" fill="#b4afe0" font-size="14">{len(repos)} public repos · {live_total} live</text>
{chr(10).join(labels)}
{chr(10).join(shapes)}
</svg>
'''


def replace_between(text, marker, content):
    pattern = re.compile(rf"(<!-- {marker}:START -->)(.*?)(<!-- {marker}:END -->)", re.S)
    if not pattern.search(text):
        print(f"Note: README has no {marker} markers, skipping.")
        return text
    return pattern.sub(lambda m: m.group(1) + content + m.group(3), text)


def main():
    repos = fetch_repos()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build_svg(repos), encoding="utf-8")

    text = README.read_text(encoding="utf-8")
    text = replace_between(text, "COUNT", str(len(repos)))
    text = replace_between(text, "LIVE", str(sum(1 for r in repos if r.get("homepage"))))
    README.write_text(text, encoding="utf-8")
    print(f"Built bubbles for {len(repos)} repos.")


if __name__ == "__main__":
    main()
