#!/usr/bin/env python3
"""Render a GitHub profile dashboard from the account's public GraphQL data."""

from __future__ import annotations

import datetime as dt
import html
import json
import math
import os
import re
import urllib.request
from collections import defaultdict
from pathlib import Path


USERNAME = os.environ.get("GITHUB_USERNAME", "DDSSMahith")
TOKEN = os.environ.get("GITHUB_TOKEN")
OUTPUT = Path("assets/github-activity.svg")
QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    login
    followers { totalCount }
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalIssueContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      totalRepositoryContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount contributionLevel } }
      }
    }
    repositories(first: 100, ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false) {
      totalCount
      nodes {
        stargazerCount
        forkCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""

WIDTH, HEIGHT = 1100, 650
LEVEL_COLORS = {
    "NONE": "#30363d",
    "FIRST_QUARTILE": "#0e4429",
    "SECOND_QUARTILE": "#006d32",
    "THIRD_QUARTILE": "#26a641",
    "FOURTH_QUARTILE": "#39d353",
}
LANGUAGE_COLORS = {
    "Python": "#3572A5", "TypeScript": "#3178c6", "JavaScript": "#f1e05a",
    "Jupyter Notebook": "#DA5B0B", "HTML": "#e34c26", "CSS": "#663399",
    "Rust": "#dea584", "Java": "#b07219", "C++": "#f34b7d", "C": "#555555",
    "Shell": "#89e051", "Go": "#00ADD8", "Kotlin": "#A97BFF", "Dart": "#00B4AB",
    "C#": "#178600", "Vue": "#41b883", "SCSS": "#c6538c", "Other": "#8b949e",
}


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def label(x: float, y: float, value: object, *, size: int = 12, color: str = "#c9d1d9",
          anchor: str = "start", weight: int = 400, family: str = "Arial, sans-serif") -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" fill="{color}" font-family="{family}" '
            f'font-size="{size}px" font-weight="{weight}" text-anchor="{anchor}">{esc(value)}</text>')


def polygon(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def shade(color: str, factor: float) -> str:
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        return "#39d353"
    rgb = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{max(0, min(255, round(c * factor))):02x}" for c in rgb)


def fetch_data() -> dict:
    if not TOKEN:
        raise RuntimeError("GITHUB_TOKEN is required to fetch live GitHub profile data.")
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    variables = {
        "login": USERNAME,
        "from": (now - dt.timedelta(days=365)).isoformat().replace("+00:00", "Z"),
        "to": now.isoformat().replace("+00:00", "Z"),
    }
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json",
                  "User-Agent": "DDSSMahith-profile-readme"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    if result.get("errors"):
        raise RuntimeError("GitHub GraphQL query failed: " + "; ".join(e["message"] for e in result["errors"]))
    user = result.get("data", {}).get("user")
    if not user:
        raise RuntimeError(f"GitHub user @{USERNAME} was not found.")
    return user


def summarize(user: dict) -> dict:
    collection = user["contributionsCollection"]
    calendar = collection["contributionCalendar"]
    repositories = user["repositories"]
    languages: dict[str, dict] = defaultdict(lambda: {"size": 0, "color": ""})
    stars = forks = 0
    for repo in repositories["nodes"]:
        stars += repo["stargazerCount"]
        forks += repo["forkCount"]
        for edge in repo["languages"]["edges"]:
            language = edge["node"]["name"]
            languages[language]["size"] += edge["size"]
            languages[language]["color"] = edge["node"].get("color") or LANGUAGE_COLORS.get(language, "#8b949e")

    days = [day for week in calendar["weeks"] for day in week["contributionDays"]]
    days.sort(key=lambda day: day["date"])
    counts = [day["contributionCount"] for day in days]
    current_streak = 0
    today = dt.datetime.now(dt.timezone.utc).date()
    index = len(days) - 1
    if index >= 0 and days[index]["date"] == today.isoformat() and days[index]["contributionCount"] == 0:
        index -= 1
    while index >= 0 and days[index]["contributionCount"] > 0:
        current_streak += 1
        index -= 1
    longest_streak = streak = 0
    for count in counts:
        streak = streak + 1 if count else 0
        longest_streak = max(longest_streak, streak)

    return {
        "login": user["login"],
        "calendar": calendar,
        "days": days,
        "contributions": calendar["totalContributions"],
        "commits": collection["totalCommitContributions"],
        "issues": collection["totalIssueContributions"],
        "pullRequests": collection["totalPullRequestContributions"],
        "reviews": collection["totalPullRequestReviewContributions"],
        "reposCreated": collection["totalRepositoryContributions"],
        "repoCount": repositories["totalCount"],
        "stars": stars,
        "forks": forks,
        "followers": user["followers"]["totalCount"],
        "languages": sorted(languages.items(), key=lambda item: item[1]["size"], reverse=True),
        "currentStreak": current_streak,
        "longestStreak": longest_streak,
        "updated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


def draw_calendar(stats: dict, out: list[str]) -> None:
    weeks = stats["calendar"]["weeks"]
    cells = []
    for col, week in enumerate(weeks):
        for row, day in enumerate(week["contributionDays"]):
            cells.append((col, row, day))
    cells.sort(key=lambda cell: (cell[0] + cell[1], cell[1]))

    ox, oy, step = 22.0, 86.0, 12.15
    for col, row, day in cells:
        x, y = ox + step * (col + row), oy + step * (col - row) * 0.5
        top = [(x, y), (x + step, y - step * .5), (x + 2 * step, y), (x + step, y + step * .5)]
        level = day.get("contributionLevel", "NONE")
        base = LEVEL_COLORS.get(level, LEVEL_COLORS["NONE"])
        out.append(f'<polygon points="{polygon(top)}" fill="#262b31" stroke="#06090c" stroke-width=".65"/>')
        count = day["contributionCount"]
        if not count:
            continue
        height = min(50.0, 7.0 + math.log2(count + 1) * 6.2)
        raised = [(px, py - height) for px, py in top]
        left = [top[3], top[0], raised[0], raised[3]]
        right = [top[0], top[1], raised[1], raised[0]]
        delay = ((col * 7 + row) % 72) * .012
        title = f'{day["date"]}: {count} contribution' + ("s" if count != 1 else "")
        out.append(f'<g><title>{esc(title)}</title>'
                   f'<animateTransform attributeName="transform" type="translate" values="0 2;0 0" '
                   f'dur=".38s" begin="{delay:.2f}s" fill="freeze"/>'
                   f'<polygon points="{polygon(left)}" fill="{shade(base, .58)}"/>'
                   f'<polygon points="{polygon(right)}" fill="{shade(base, .76)}"/>'
                   f'<polygon points="{polygon(raised)}" fill="{base}" stroke="#7ee787" stroke-opacity=".17" stroke-width=".5"/>'
                   f'</g>')


def draw_radar(stats: dict, out: list[str]) -> None:
    cx, cy, radius = 932.0, 203.0, 98.0
    axes = [
        ("Commit", stats["commits"]), ("Issue", stats["issues"]),
        ("Pull Req", stats["pullRequests"]), ("Review", stats["reviews"]),
        ("Repo", stats["reposCreated"]),
    ]
    angles = [-math.pi / 2 + 2 * math.pi * i / len(axes) for i in range(len(axes))]
    out.append(label(805, 76, "ACTIVITY RADAR", size=11, color="#8b949e", weight=600))
    for value in (10, 100, 1000, 10000):
        r = radius * math.log10(value) / 4
        points = [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in angles]
        out.append(f'<polygon points="{polygon(points)}" fill="none" stroke="#8b949e" stroke-opacity=".48" stroke-width=".8" stroke-dasharray="2.5 4"/>')
        out.append(label(cx + 4, cy - r + 9, f"{value:,}", size=8, color="#8b949e"))
    for index, ((name, value), angle) in enumerate(zip(axes, angles)):
        ex, ey = cx + radius * math.cos(angle), cy + radius * math.sin(angle)
        out.append(f'<path d="M{cx:.1f} {cy:.1f}L{ex:.1f} {ey:.1f}" stroke="#8b949e" stroke-opacity=".42" stroke-width=".8" stroke-dasharray="2 4"/>')
        lx, ly = cx + (radius + 24) * math.cos(angle), cy + (radius + 24) * math.sin(angle)
        anchor = "middle" if index in (0, 2, 3) else ("start" if index == 1 else "end")
        out.append(label(lx, ly + (3 if index == 0 else 5), name, size=12, color="#e6edf3", anchor=anchor))
    values = [radius * min(1.0, math.log10(value + 1) / 4) for _, value in axes]
    points = [(cx + r * math.cos(a), cy + r * math.sin(a)) for r, a in zip(values, angles)]
    out.append(f'<polygon points="{polygon(points)}" fill="#39d353" fill-opacity=".30" stroke="#56d364" stroke-width="2.2">'
               '<title>Actual public GitHub contributions in the last 12 months; radar uses a logarithmic scale.</title>'
               '<animate attributeName="fill-opacity" values=".20;.34;.20" dur="5s" repeatCount="indefinite"/></polygon>')
    for (name, value), (x, y) in zip(axes, points):
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="#8bff9d"><title>{esc(name)}: {value:,}</title></circle>')
    out.append('<path d="M805 375H1070" stroke="#30363d" stroke-width="1"/>')
    out.append(label(805, 398, "CURRENT STREAK", size=9, color="#8b949e", weight=600))
    out.append(label(1070, 398, "LONGEST STREAK", size=9, color="#8b949e", anchor="end", weight=600))
    current_unit = "day" if stats["currentStreak"] == 1 else "days"
    longest_unit = "day" if stats["longestStreak"] == 1 else "days"
    out.append(label(805, 424, f'{stats["currentStreak"]} {current_unit}', size=17, color="#e6edf3", weight=700))
    out.append(label(1070, 424, f'{stats["longestStreak"]} {longest_unit}', size=17, color="#e6edf3", anchor="end", weight=700))
    out.append(label(805, 451, f'ISSUES  {stats["issues"]:,}', size=10, color="#8b949e"))
    out.append(label(1070, 451, f'REVIEWS  {stats["reviews"]:,}', size=10, color="#8b949e", anchor="end"))


def donut_path(start_degrees: float, end_degrees: float, outer: float, inner: float) -> str:
    span = end_degrees - start_degrees
    if span >= 359.99:
        mid = start_degrees + 180
        def point(radius: float, angle: float) -> tuple[float, float]:
            radians = math.radians(angle)
            return radius * math.cos(radians), radius * math.sin(radians)
        p0, p1 = point(outer, start_degrees), point(outer, mid)
        q0, q1 = point(inner, start_degrees), point(inner, mid)
        return (f"M{p0[0]:.2f},{p0[1]:.2f} A{outer},{outer} 0 1 1 {p1[0]:.2f},{p1[1]:.2f} "
                f"A{outer},{outer} 0 1 1 {p0[0]:.2f},{p0[1]:.2f} "
                f"L{q0[0]:.2f},{q0[1]:.2f} A{inner},{inner} 0 1 0 {q1[0]:.2f},{q1[1]:.2f} "
                f"A{inner},{inner} 0 1 0 {q0[0]:.2f},{q0[1]:.2f} Z")
    start, end = math.radians(start_degrees), math.radians(end_degrees)
    x0, y0 = outer * math.cos(start), outer * math.sin(start)
    x1, y1 = outer * math.cos(end), outer * math.sin(end)
    ix1, iy1 = inner * math.cos(end), inner * math.sin(end)
    ix0, iy0 = inner * math.cos(start), inner * math.sin(start)
    large = 1 if span > 180 else 0
    return (f"M{x0:.2f},{y0:.2f} A{outer},{outer} 0 {large} 1 {x1:.2f},{y1:.2f} "
            f"L{ix1:.2f},{iy1:.2f} A{inner},{inner} 0 {large} 0 {ix0:.2f},{iy0:.2f} Z")


def draw_languages(stats: dict, out: list[str]) -> None:
    entries = stats["languages"]
    total = sum(item["size"] for _, item in entries)
    if not total:
        out.append(label(35, 490, "LANGUAGES", size=12, color="#8b949e", weight=600))
        out.append(label(35, 516, "No public language data yet", size=11, color="#8b949e"))
        return
    top = entries[:5]
    other = sum(item["size"] for _, item in entries[5:])
    segments = [(name, item["size"], item["color"] or LANGUAGE_COLORS.get(name, "#8b949e")) for name, item in top]
    if other:
        segments.append(("Other", other, LANGUAGE_COLORS["Other"]))
    cx, cy, radius = 132.0, 544.0, 63.0
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="#30363d"/>')
    angle = -90.0
    for name, size, color in segments:
        span = 360 * size / total
        path = donut_path(angle, angle + span, radius, 34)
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            color = LANGUAGE_COLORS.get(name, "#8b949e")
        percentage = size / total * 100
        out.append(f'<path d="{path}" transform="translate({cx} {cy})" fill="{color}" stroke="#0d1117" stroke-width="1.4">'
                   f'<title>{esc(name)}: {percentage:.1f}% of public repository languages</title></path>')
        angle += span
    out.append(label(cx, cy - 2, "LANG", size=9, color="#8b949e", anchor="middle", weight=600))
    out.append(label(cx, cy + 12, f"{len(entries)}", size=12, color="#e6edf3", anchor="middle", weight=600))
    out.append(label(229, 492, "MOST USED LANGUAGES", size=11, color="#8b949e", weight=600))
    for index, (name, size, color) in enumerate(segments):
        column, row = divmod(index, 3)
        x, y = 229 + column * 170, 516 + row * 24
        percentage = size / total * 100
        out.append(f'<circle cx="{x}" cy="{y - 3}" r="4" fill="{color}"/>')
        display = name if len(name) <= 15 else name[:14] + "…"
        out.append(label(x + 10, y, f"{display}  {percentage:.1f}%", size=10, color="#c9d1d9"))


def render(stats: dict) -> str:
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc">',
           '<title id="title">Live GitHub activity for DDSSMahith</title>',
           '<desc id="desc">Animated isometric contribution calendar, activity radar, and donut chart of public repository languages, generated from GitHub data.</desc>',
           '<rect width="100%" height="100%" fill="#010409"/>',
           '<style>text{font-family:Arial,Helvetica,sans-serif}@media(prefers-reduced-motion:reduce){animate,animateTransform{display:none}}</style>',
           label(25, 32, "GITHUB ACTIVITY  /  LAST 12 MONTHS", size=11, color="#8b949e", weight=600),
           label(1075, 32, f'{stats["days"][0]["date"]}  —  {stats["days"][-1]["date"]}', size=10, color="#8b949e", anchor="end"),
           label(1075, 48, f'Updated {stats["updated"]}', size=9, color="#6e7681", anchor="end")]
    draw_calendar(stats, out)
    draw_radar(stats, out)
    draw_languages(stats, out)
    out.append('<path d="M25 614H1075" stroke="#30363d" stroke-width="1"/>')
    footer = [
        (36, f'{stats["contributions"]:,}', "CONTRIBUTIONS"),
        (286, f'{stats["commits"]:,}', "COMMITS"),
        (496, f'{stats["pullRequests"]:,}', "PULL REQUESTS"),
        (714, f'{stats["stars"]:,}', "STARS"),
        (898, f'{stats["followers"]:,}', "FOLLOWERS"),
    ]
    for x, value, name in footer:
        out.append(label(x, 640, value, size=16, color="#e6edf3", weight=700))
        out.append(label(x + 64, 639, name, size=9, color="#8b949e", weight=600))
    out.append('</svg>')
    return "\n".join(out) + "\n"


def main() -> None:
    stats = summarize(fetch_data())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render(stats), encoding="utf-8")
    print(f"Updated {OUTPUT} for @{stats['login']} ({stats['contributions']:,} contributions, {stats['repoCount']} public repositories).")


if __name__ == "__main__":
    main()
