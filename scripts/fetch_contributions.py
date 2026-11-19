#!/usr/bin/env python3
"""Refresh data/contributions.json (run daily by the GitHub Action).

Schema consumed by build_cards.py:
{
  "login": "...", "generated": "YYYY-MM-DD",
  "days":  [{"date": "YYYY-MM-DD", "count": 3}, ...],        # last 365 days
  "repos": {"owner/name": {"stars": 1, "forks": 0, "language": "JavaScript", "language_color": "#f1e05a"}}
}
Needs GITHUB_TOKEN (the Action's default token works for public data).
"""
import json
import os
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build_cards import FEATURED, PROFILE  # noqa: E402

TOKEN = os.environ["GITHUB_TOKEN"]


def gql(query: str, variables: dict) -> dict:
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


today = date.today()
cal = gql(
    """query($login:String!,$from:DateTime!,$to:DateTime!){
      user(login:$login){contributionsCollection(from:$from,to:$to){
        contributionCalendar{weeks{contributionDays{date contributionCount}}}}}}""",
    {"login": PROFILE["login"], "from": f"{today - timedelta(days=364)}T00:00:00Z", "to": f"{today}T23:59:59Z"},
)
if "errors" in cal or not cal.get("data", {}).get("user"):
    sys.exit(f"contribution query failed: {cal.get('errors')}")
weeks = cal["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
days = [{"date": d["date"], "count": d["contributionCount"]} for w in weeks for d in w["contributionDays"]]

repos = {}
for item in FEATURED:
    owner, name = item["repo"].split("/")
    res = gql(
        """query($o:String!,$n:String!){repository(owner:$o,name:$n){
          stargazerCount forkCount primaryLanguage{name color}}}""",
        {"o": owner, "n": name},
    )
    repo = (res.get("data") or {}).get("repository")
    if not repo:
        print(f"skipping stats for {item['repo']} (not found or no access)", file=sys.stderr)
        continue
    lang = repo.get("primaryLanguage") or {}
    repos[item["repo"]] = {
        "stars": repo["stargazerCount"], "forks": repo["forkCount"],
        "language": lang.get("name"), "language_color": lang.get("color"),
    }

out = ROOT / "data" / "contributions.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps({"login": PROFILE["login"], "generated": today.isoformat(),
                           "days": days, "repos": repos}, indent=1), encoding="utf-8")
print(f"wrote {out} ({len(days)} days, {len(repos)} repos)")
