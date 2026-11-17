#!/usr/bin/env python3
"""Render a GitHub profile dashboard from the account's accessible GraphQL data."""

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
TOKEN = os.environ.get("PROFILE_TOKEN") or os.environ.get("GITHUB_TOKEN")
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
      totalRepositoriesWithContributedCommits
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount contributionLevel } }
      }
    }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
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
CONTRIBUTION_COLORS = {
    "NONE": "#444444",
    "FIRST_QUARTILE": "#1B7D28",
    "SECOND_QUARTILE": "#24A736",
    "THIRD_QUARTILE": "#2DD143",
    "FOURTH_QUARTILE": "#57DA69",
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


def short_date(value: str) -> str:
    if value == "—":
        return value
    date = dt.date.fromisoformat(value)
    return f"{date.strftime('%b')} {date.day}"


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


def contribution_color(level: str) -> str:
    """Use the reference project's night-green color for each GitHub level."""
    return CONTRIBUTION_COLORS.get(level, CONTRIBUTION_COLORS["NONE"])


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
    active_runs = []
    active_run = []
    for day in days:
        if day["contributionCount"]:
            active_run.append(day)
        elif active_run:
            active_runs.append(active_run)
            active_run = []
    if active_run:
        active_runs.append(active_run)
    longest_run = max(active_runs, key=len, default=[])
    current_run = []
    today = dt.datetime.now(dt.timezone.utc).date()
    index = len(days) - 1
    if index >= 0 and days[index]["date"] == today.isoformat() and days[index]["contributionCount"] == 0:
        index -= 1
    while index >= 0 and days[index]["contributionCount"] > 0:
        current_run.append(days[index])
        index -= 1
    current_run.reverse()
    if current_run and (today - dt.date.fromisoformat(current_run[-1]["date"])).days > 1:
        current_run = []

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
        "reposContributedTo": collection["totalRepositoriesWithContributedCommits"],
        "repoCount": repositories["totalCount"],
        "stars": stars,
        "forks": forks,
        "followers": user["followers"]["totalCount"],
        "languages": sorted(languages.items(), key=lambda item: item[1]["size"], reverse=True),
        "activeDays": sum(1 for day in days if day["contributionCount"] > 0),
        "currentStreak": len(current_run),
        "currentStreakStart": current_run[0]["date"] if current_run else "—",
        "currentStreakEnd": current_run[-1]["date"] if current_run else "—",
        "longestStreak": len(longest_run),
        "longestStreakStart": longest_run[0]["date"] if longest_run else "—",
        "longestStreakEnd": longest_run[-1]["date"] if longest_run else "—",
        "updated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


def draw_calendar(stats: dict, out: list[str]) -> None:
    days = stats["days"]
    if not days:
        return

    # Port of the reference project's isometric projection: cells advance
    # diagonally by week and weekday, and each voxel is three transformed
    # rectangles. Chronological SVG order gives correct back-to-front overlap.
    dx = 760.0 / 64.0
    dy = dx * math.tan(math.radians(30))
    face = dx * .9
    face_depth = dy * .9
    first_date = dt.date.fromisoformat(days[0]["date"])
    first_weekday = (first_date.weekday() + 1) % 7  # Sunday = 0
    week_count = math.ceil((len(days) + first_weekday) / 7.0)
    offset_x = dx * 7
    offset_y = 455.0 - (week_count + 7) * dy
    scale_left = math.sqrt(face * face + face_depth * face_depth) / face
    scale_right = scale_left
    top_skew_x = math.degrees(math.atan(face / 2 / face_depth))

    for index, day in enumerate(days):
        date = dt.date.fromisoformat(day["date"])
        day_offset = (date.weekday() + 1) % 7
        week = (index + first_weekday) // 7
        base_x = offset_x + (week - day_offset) * dx
        base_y = offset_y + (week + day_offset) * dy
        count = day["contributionCount"]
        height = math.log10(count / 20.0 + 1) * 144.0 + 3.0
        top_color = contribution_color(day.get("contributionLevel", "NONE"))
        left_color = shade(top_color, .83666)
        right_color = shade(top_color, .7)

        delay = min(1.5, index * .003)
        title = f'{day["date"]}: {count} contribution' + ("s" if count != 1 else "")
        animation = (f'<animateTransform attributeName="transform" type="translate" '
                     f'values="{base_x:.2f} {base_y - 3:.2f};{base_x:.2f} {base_y - height:.2f}" '
                     f'dur="1.4s" begin="{delay:.3f}s" fill="freeze"/>') if count else ""
        out.append(f'<g transform="translate({base_x:.2f} {base_y - height:.2f})">'
                   f'<title>{esc(title)}</title>{animation}'
                   f'<rect x="0" y="0" width="{face:.2f}" height="{face:.2f}" fill="{top_color}" '
                   f'transform="skewY(-30) skewX({top_skew_x:.2f}) scale(1 {2 * face_depth / face:.4f})"/>'
                   f'<rect x="0" y="0" width="{face:.2f}" height="{height / scale_left:.2f}" fill="{left_color}" '
                   f'transform="skewY(30) scale(1 {scale_left:.4f})"/>'
                   f'<rect x="0" y="0" width="{face:.2f}" height="{height / scale_right:.2f}" fill="{right_color}" '
                   f'transform="translate({face:.2f} {face_depth:.2f}) skewY(-30) '
                   f'scale(1 {scale_right:.4f})"/></g>')


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
        out.append(label(35, 516, "No repository language data yet", size=11, color="#8b949e"))
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
                   f'<title>{esc(name)}: {percentage:.1f}% of accessible repository languages</title></path>')
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


def render_summary(stats: dict) -> str:
    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="710" viewBox="0 0 900 710" role="img" aria-labelledby="title desc">',
        '<title id="title">Live GitHub stats for DDSSMahith</title>',
        '<desc id="desc">Current stars, yearly commits, pull requests, issues, contributed repositories, contribution streaks, and programming language breakdown.</desc>',
        '<rect width="900" height="710" fill="#010409"/>',
        '<style>text{font-family:"Segoe UI",Ubuntu,sans-serif}@keyframes currstreak{0%{font-size:3px;opacity:.2}80%{font-size:34px;opacity:1}100%{font-size:28px;opacity:1}}@keyframes fadein{0%{opacity:0}100%{opacity:1}}@media(prefers-reduced-motion:reduce){animate,animateTransform{display:none}}</style>',
        '<defs><mask id="mask_out_ring_behind_fire" maskUnits="userSpaceOnUse"><rect width="900" height="710" fill="white"/><ellipse cx="450" cy="311" rx="13" ry="18" fill="black"/></mask></defs>',
    ]
    panel = "#0b100d"
    border = "#39443e"
    title_color = "#b6d900"
    value_color = "#59b78d"
    muted = "#8b9a91"

    # Account summary
    out.append(f'<rect x="20" y="16" width="860" height="220" rx="11" fill="{panel}" stroke="{border}" stroke-width="1.4"/>')
    out.append(label(46, 52, f'{stats["login"]} / GITHUB STATS', size=19, color=title_color, weight=700))
    rows = [
        ("Total Stars Earned", stats["stars"]),
        ("Total Commits (last year)", stats["commits"]),
        ("Total PRs (last year)", stats["pullRequests"]),
        ("Total Issues (last year)", stats["issues"]),
        ("Repositories contributed to", stats["reposContributedTo"]),
    ]
    for index, (name, value) in enumerate(rows):
        y = 87 + index * 27
        out.append(label(47, y, f"{name}:", size=13, color=value_color, weight=600))
        out.append(label(344, y, f"{value:,}", size=13, color=value_color, weight=700))
    cx, cy, radius = 743, 133, 48
    circumference = 2 * math.pi * radius
    active = min(stats["activeDays"] / 365, 1)
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="#263520" stroke-width="9"/>')
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="{title_color}" stroke-width="9" '
               f'stroke-dasharray="{circumference * active:.1f} {circumference * (1-active):.1f}" transform="rotate(-90 {cx} {cy})"/>')
    out.append(label(cx, cy + 3, f'{stats["activeDays"]}', size=23, color=value_color, anchor="middle", weight=700))
    out.append(label(cx, cy + 20, "ACTIVE DAYS", size=8, color=muted, anchor="middle", weight=600))

    # Profile grade sits in the open space between the account totals and active-days ring.
    grade_cx, grade_cy, grade_r = 580, 133, 48
    grade_circumference = 2 * math.pi * grade_r
    out.append(f'<circle cx="{grade_cx}" cy="{grade_cy}" r="{grade_r}" fill="none" stroke="#263520" stroke-width="9"/>')
    out.append(f'<circle cx="{grade_cx}" cy="{grade_cy}" r="{grade_r}" fill="none" stroke="{title_color}" stroke-width="9" '
               f'stroke-dasharray="{grade_circumference - 7:.1f} 7" transform="rotate(-90 {grade_cx} {grade_cy})">'
               f'<animate attributeName="stroke-dashoffset" from="{grade_circumference - 7:.1f}" to="0" dur="1.2s" fill="freeze"/></circle>')
    out.append(label(grade_cx, grade_cy + 3, "S", size=23, color=value_color, anchor="middle", weight=700))
    out.append(label(grade_cx, grade_cy + 20, "PROFILE RATING", size=8, color=muted, anchor="middle", weight=600))

    # Contribution totals and streaks
    out.append(f'<rect x="20" y="251" width="860" height="220" rx="11" fill="{panel}" stroke="{border}" stroke-width="1.4"/>')
    out.append(label(46, 283, "CONTRIBUTIONS & STREAKS", size=15, color=title_color, weight=700))
    out.append('<path d="M306 304V449M594 304V449" stroke="#59645d" stroke-width="1"/>')
    centers = [163, 450, 737]
    out.append(label(centers[0], 350, f'{stats["contributions"]:,}', size=31, color=title_color, anchor="middle", weight=700))
    out.append(label(centers[0], 377, "Total Contributions", size=13, color=title_color, anchor="middle", weight=600))
    out.append(label(centers[0], 405, f'{stats["days"][0]["date"]} – {stats["days"][-1]["date"]}', size=11, color=value_color, anchor="middle"))

    ring_r, ring_c = 40, centers[1]
    out.append(f'<circle cx="{ring_c}" cy="350" r="{ring_r}" fill="none" stroke="#ABD200" stroke-width="5" mask="url(#mask_out_ring_behind_fire)" style="opacity:0;animation:fadein .5s linear forwards .4s"/>')
    out.append(f'<g transform="translate({ring_c}, 298.5)" stroke-opacity="0" style="opacity:0;animation:fadein .5s linear forwards .6s"><title>Current streak flame</title>'
               '<path d="M -12 -0.5 L 15 -0.5 L 15 23.5 L -12 23.5 L -12 -0.5 Z" fill="none"/>'
               '<path d="M 1.5 0.67 C 1.5 0.67 2.24 3.32 2.24 5.47 C 2.24 7.53 0.89 9.2 -1.17 9.2 C -3.23 9.2 -4.79 7.53 -4.79 5.47 L -4.76 5.11 C -6.78 7.51 -8 10.62 -8 13.99 C -8 18.41 -4.42 22 0 22 C 4.42 22 8 18.41 8 13.99 C 8 8.6 5.41 3.79 1.5 0.67 Z M -0.29 19 C -2.07 19 -3.51 17.6 -3.51 15.86 C -3.51 14.24 -2.46 13.1 -0.7 12.74 C 1.07 12.38 2.9 11.53 3.92 10.16 C 4.31 11.45 4.51 12.81 4.51 14.2 C 4.51 16.85 2.36 19 -0.29 19 Z" fill="#ABD200" stroke-opacity="0"/></g>')
    out.append(f'<text x="{ring_c:.1f}" y="359.0" fill="#B7D364" font-family="Segoe UI, Ubuntu, sans-serif" font-weight="700" font-size="28px" text-anchor="middle" style="animation:currstreak .6s linear forwards">{esc(stats["currentStreak"])}</text>')
    out.append(label(ring_c, 418, "Current Streak", size=13, color="#B7D364", anchor="middle", weight=700, family="Segoe UI, Ubuntu, sans-serif"))
    streak_dates = f'{short_date(stats["currentStreakStart"])} – {short_date(stats["currentStreakEnd"])}'
    out.append(label(ring_c, 437, streak_dates, size=10, color="#68B587", anchor="middle", family="Segoe UI, Ubuntu, sans-serif"))

    out.append(label(centers[2], 350, f'{stats["longestStreak"]}', size=31, color=title_color, anchor="middle", weight=700))
    out.append(label(centers[2], 377, "Longest Streak (days)", size=13, color=title_color, anchor="middle", weight=600))
    out.append(label(centers[2], 405, f'{stats["longestStreakStart"]} – {stats["longestStreakEnd"]}', size=11, color=value_color, anchor="middle"))

    # Language breakdown
    out.append(f'<rect x="20" y="486" width="860" height="205" rx="11" fill="{panel}" stroke="{border}" stroke-width="1.4"/>')
    out.append(label(46, 520, "MOST USED LANGUAGES", size=17, color=title_color, weight=700))
    languages = stats["languages"]
    total = sum(item["size"] for _, item in languages)
    entries = [(name, item["size"], item["color"] or LANGUAGE_COLORS.get(name, "#8b949e")) for name, item in languages[:5]]
    if len(languages) > 5:
        entries.append(("Other", sum(item["size"] for _, item in languages[5:]), LANGUAGE_COLORS["Other"]))
    if total:
        bar_x, bar_y, bar_w = 46.0, 545.0, 808.0
        cursor = bar_x
        for name, size, color in entries:
            width = bar_w * size / total
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                color = LANGUAGE_COLORS.get(name, "#8b949e")
            out.append(f'<rect x="{cursor:.2f}" y="{bar_y}" width="{width:.2f}" height="11" fill="{color}"/>')
            cursor += width
        for index, (name, size, color) in enumerate(entries):
            column, row = divmod(index, 3)
            x, y = 49 + column * 394, 585 + row * 28
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                color = LANGUAGE_COLORS.get(name, "#8b949e")
            percent = size / total * 100
            display = name if len(name) <= 26 else name[:25] + "…"
            out.append(f'<circle cx="{x}" cy="{y-4}" r="5" fill="{color}"/>')
            out.append(label(x + 13, y, f"{display}  {percent:.2f}%", size=11, color=value_color))
    else:
        out.append(label(48, 582, "No repository language data yet", size=12, color=muted))
    out.append('</svg>')
    return "\n".join(out) + "\n"


def main() -> None:
    stats = summarize(fetch_data())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render(stats), encoding="utf-8")
    Path("assets/github-summary.svg").write_text(render_summary(stats), encoding="utf-8")
    print(f"Updated {OUTPUT} for @{stats['login']} ({stats['contributions']:,} contributions, {stats['repoCount']} accessible repositories).")


if __name__ == "__main__":
    main()
