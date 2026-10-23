"""Render Matrix-styled stats cards from the GitHub GraphQL API.

Usage: GITHUB_TOKEN=... python3 scripts/matrix_cards.py <login> <outdir>
       python3 scripts/matrix_cards.py --demo <outdir>   (mock data, no network)
"""
import datetime as dt
import json
import os
import random
import sys
import urllib.request
from html import escape

GREEN, DIM, PALE, BG = "#00ff41", "#008f11", "#7dff9b", "#0d0208"
GLYPHS = "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ"


def gql(query, token):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": "matrix-cards"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.load(r)
    if body.get("errors"):
        raise SystemExit(f"GraphQL error: {body['errors']}")
    return body["data"]


def fetch(login, token):
    base = gql(f'''{{ user(login:"{login}") {{
      createdAt
      merged: pullRequests(states: MERGED) {{ totalCount }}
      prs: pullRequests {{ totalCount }}
      contributedTo: repositoriesContributedTo(contributionTypes: [COMMIT, PULL_REQUEST, PULL_REQUEST_REVIEW]) {{ totalCount }}
      repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {{
        nodes {{ languages(first: 10, orderBy: {{field: SIZE, direction: DESC}}) {{ edges {{ size node {{ name }} }} }} }}
      }}
    }} }}''', token)["user"]
    now = dt.datetime.now(dt.timezone.utc)
    years = range(int(base["createdAt"][:4]), now.year + 1)
    # contributionsCollection spans at most one year, so ask for each year under an alias.
    parts = "".join(f'''y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{min(dt.datetime(y, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc), now).isoformat()}") {{
        totalCommitContributions totalPullRequestContributions totalPullRequestReviewContributions
        totalIssueContributions restrictedContributionsCount
        contributionCalendar {{ totalContributions weeks {{ contributionDays {{ date contributionCount }} }} }}
      }} ''' for y in years)
    yearly = gql(f'{{ user(login:"{login}") {{ {parts} }} }}', token)["user"]
    langs = {}
    for repo in base["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            langs[e["node"]["name"]] = langs.get(e["node"]["name"], 0) + e["size"]
    days = {}
    for c in yearly.values():
        for w in c["contributionCalendar"]["weeks"]:
            for d in w["contributionDays"]:
                days[d["date"]] = d["contributionCount"]
    total = lambda k: sum(c[k] for c in yearly.values())
    return {
        "commits": total("totalCommitContributions"),
        "prs": base["prs"]["totalCount"],
        "merged": base["merged"]["totalCount"],
        "reviews": total("totalPullRequestReviewContributions"),
        "issues": total("totalIssueContributions"),
        "private": total("restrictedContributionsCount"),
        "repos": base["contributedTo"]["totalCount"],
        "years": {int(k[1:]): c["contributionCalendar"]["totalContributions"] for k, c in yearly.items()},
        "langs": langs,
        "days": days,
        "today": now.date().isoformat(),
    }


def streaks(days, today):
    """Return (current, longest) streak of consecutive days with contributions."""
    longest = run = 0
    for d in sorted(days):
        if d > today:
            break
        run = run + 1 if days[d] else 0
        longest = max(longest, run)
    current, d = 0, dt.date.fromisoformat(today)
    if not days.get(today):  # today not over yet: don't break the streak
        d -= dt.timedelta(days=1)
    while days.get(d.isoformat()):
        current += 1
        d -= dt.timedelta(days=1)
    return current, longest


def scramble(text, x, y, cls, anchor="start", delay=0.0):
    """Value that 'decodes' from katakana noise into its real text."""
    rnd = random.Random(text + str(x) + str(y))
    noise = "".join(rnd.choice(GLYPHS) for _ in text)
    t = f"{delay:.2f}s"
    return (f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}">{noise}'
            f'<set attributeName="opacity" to="0" begin="{t}" fill="freeze"/></text>'
            f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}" opacity="0">{escape(text)}'
            f'<set attributeName="opacity" to="1" begin="{t}" fill="freeze"/></text>')


def frame(w, h, title, body):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{escape(title)}">
<style>
text{{font-family:"SFMono-Regular",Consolas,"Liberation Mono",Menlo,monospace}}
.ttl{{font-size:14px;fill:{DIM}}}
.lbl{{font-size:13px;fill:{PALE};letter-spacing:1px}}
.val{{font-size:22px;font-weight:700;fill:{GREEN}}}
.big{{font-size:40px;font-weight:700;fill:{GREEN}}}
.sm{{font-size:12px;fill:{DIM}}}
.bar{{fill:{GREEN};transform-box:fill-box;transform-origin:left bottom;animation:grow 1.2s ease-out both}}
.vbar{{fill:{GREEN};transform-box:fill-box;transform-origin:center bottom;animation:rise 1.2s ease-out both}}
.track{{fill:#003b00;opacity:.45}}
@keyframes grow{{from{{transform:scaleX(0)}}}}
@keyframes rise{{from{{transform:scaleY(0)}}}}
@media (prefers-reduced-motion:reduce){{.bar,.vbar{{animation:none}}}}
</style>
<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="6" fill="{BG}" stroke="{DIM}" stroke-opacity=".6"/>
<circle cx="20" cy="20" r="5" fill="#003b00"/><circle cx="38" cy="20" r="5" fill="#008f11"/><circle cx="56" cy="20" r="5" fill="{GREEN}"/>
<text x="78" y="25" class="ttl">{escape(title)}</text>
<line x1="0" y1="40" x2="{w}" y2="40" stroke="{DIM}" stroke-opacity=".4"/>
{body}
</svg>'''


def stats_card(login, s):
    rows = [("COMMITS", s["commits"]), ("PULL REQUESTS", s["prs"]), ("PRs MERGED", s["merged"]),
            ("CODE REVIEWS", s["reviews"]), ("ISSUES", s["issues"]), ("CONTRIBUTED TO", s["repos"])]
    if s["private"]:
        rows.append(("PRIVATE CONTRIBS", s["private"]))
    rows.append(("TOTAL CONTRIBS", sum(s["years"].values())))
    body = []
    for i, (label, n) in enumerate(rows):
        x, y = (30 if i % 2 == 0 else 270), 82 + (i // 2) * 58
        body.append(f'<text x="{x}" y="{y}" class="lbl">{label}</text>')
        body.append(scramble(f"{n:,}", x, y + 26, "val", delay=0.3 + i * 0.15))
    years = s["years"]
    top = max(years.values()) or 1
    chart_x, chart_w, base_y, chart_h = 520, 450, 270, 170
    bw = chart_w / len(years)
    body.append(f'<text x="{chart_x}" y="70" class="lbl">CONTRIBUTIONS / YEAR</text>')
    for i, (y, n) in enumerate(sorted(years.items())):
        h = max(2, chart_h * n / top)
        x = chart_x + i * bw
        body.append(f'<rect x="{x + bw*.15:.1f}" y="{base_y - h:.1f}" width="{bw*.7:.1f}" height="{h:.1f}" class="vbar" style="animation-delay:{i*.1:.1f}s" opacity="{.45 + .55*n/top:.2f}"/>')
        body.append(f'<text x="{x + bw/2:.1f}" y="{base_y - h - 6:.1f}" class="sm" text-anchor="middle">{n:,}</text>')
        body.append(f'<text x="{x + bw/2:.1f}" y="{base_y + 18}" class="sm" text-anchor="middle">{y}</text>')
    return frame(1000, 300, f"{login}@zion:~$ ./stats --all-time", "\n".join(body))


def activity_card(login, s):
    current, longest = streaks(s["days"], s["today"])
    this_year = s["years"][max(s["years"])]
    body = []
    for i, (label, n, unit) in enumerate([("CURRENT STREAK", current, "days"), ("LONGEST STREAK", longest, "days"),
                                          (f"CONTRIBS {max(s['years'])}", this_year, "")]):
        y = 80 + i * 72
        body.append(f'<text x="30" y="{y}" class="lbl">{label}</text>')
        body.append(scramble(f"{n:,}", 30, y + 40, "big", delay=0.3 + i * 0.2))
        if unit:
            body.append(f'<text x="{40 + 24 * len(f"{n:,}")}" y="{y + 40}" class="sm">{unit}</text>')
    langs = sorted(s["langs"].items(), key=lambda kv: -kv[1])[:6]
    total = sum(s["langs"].values()) or 1
    body.append('<text x="380" y="80" class="lbl">TOP LANGUAGES (owned repos)</text>')
    for i, (name, size) in enumerate(langs):
        y, pct = 108 + i * 30, size / total
        body.append(f'<text x="380" y="{y + 12}" class="sm" style="fill:{PALE}">{escape(name)}</text>')
        body.append(f'<rect x="520" y="{y}" width="370" height="14" rx="2" class="track"/>')
        body.append(f'<rect x="520" y="{y}" width="{max(2, 370 * pct / (langs[0][1] / total)):.1f}" height="14" rx="2" class="bar" style="animation-delay:{i*.12:.2f}s" opacity="{1 - i*.1:.2f}"/>')
        body.append(f'<text x="970" y="{y + 12}" class="sm" text-anchor="end">{pct:.1%}</text>')
    return frame(1000, 300, f"{login}@zion:~$ ./activity --streak --langs", "\n".join(body))


def demo():
    today = dt.date(2026, 10, 24)
    days = {(today - dt.timedelta(days=i)).isoformat(): (0 if i in (12, 40) else 3) for i in range(400)}
    assert streaks(days, today.isoformat()) == (12, 400 - 41)
    days[today.isoformat()] = 0  # today empty must not reset the streak
    assert streaks(days, today.isoformat())[0] == 11
    return {"commits": 4821, "prs": 612, "merged": 540, "reviews": 733, "issues": 41, "private": 2210,
            "repos": 37, "years": {2020: 210, 2021: 480, 2022: 890, 2023: 1204, 2024: 1530, 2025: 2104, 2026: 1877},
            "langs": {"PHP": 900, "TypeScript": 300, "HTML": 150, "JavaScript": 120, "CSS": 90, "Vue": 40, "Go": 10},
            "days": days, "today": today.isoformat()}


if __name__ == "__main__":
    if sys.argv[1] == "--demo":
        login, s = "wadakatu", demo()
    else:
        login, s = sys.argv[1], fetch(sys.argv[1], os.environ["GITHUB_TOKEN"])
    out = sys.argv[2]
    os.makedirs(out, exist_ok=True)
    for name, svg in [("matrix-stats.svg", stats_card(login, s)), ("matrix-activity.svg", activity_card(login, s))]:
        with open(os.path.join(out, name), "w") as f:
            f.write(svg)
