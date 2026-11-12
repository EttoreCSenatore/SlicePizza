"""Add a release-date table to a Dependabot Pull Request.

For every dependency the PR updates, looks up when the old and the new version were
published (PyPI, npm, Docker Hub or GitHub Releases) and writes a table at the top of the
PR description, between two markers, so running again replaces it. If a new version is
younger than the cooldown in .github/dependabot.yml, the table comes with a warning.

Usage: dependabot_release_dates.py <pr-number> [--dry-run]
Environment: GITHUB_TOKEN, GITHUB_REPOSITORY (owner/repo).
Only the standard library is used, so the workflow needs no install step.
"""

import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

COOLDOWN_DAYS = 7
START = "<!-- dependabot-release-dates:start -->"
END = "<!-- dependabot-release-dates:end -->"
# Branch names are dependabot/<ecosystem>/...
ECOSYSTEM_NAMES = {
    "pip": "pip",
    "npm_and_yarn": "npm",
    "docker": "Docker",
    "docker_compose": "Docker Compose",
    "github_actions": "GitHub Actions",
}


def http_json(url, token=None):
    headers = {"Accept": "application/json", "User-Agent": "dependabot-release-dates"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def github(path, token, method="GET", body=None):
    url = f"https://api.github.com/{path}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "dependabot-release-dates",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def parse_date(value):
    if not value:
        return None
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.timezone.utc)


# --- Release dates per registry ------------------------------------------------------------

def pypi_date(name, version):
    data = http_json(f"https://pypi.org/pypi/{urllib.parse.quote(name)}/{urllib.parse.quote(version)}/json")
    if not data and version.count(".") == 1:
        # A range floor like ">=2.0" names the release 2.0.0 on PyPI.
        data = http_json(f"https://pypi.org/pypi/{urllib.parse.quote(name)}/{urllib.parse.quote(version)}.0/json")
    if not data:
        return None
    times = [parse_date(f.get("upload_time_iso_8601")) for f in data.get("urls", [])]
    times = [t for t in times if t]
    return min(times) if times else None


def npm_date(name, version):
    data = http_json(f"https://registry.npmjs.org/{urllib.parse.quote(name, safe='@')}")
    return parse_date((data or {}).get("time", {}).get(version))


def docker_date(name, tag):
    # Official images live under "library". Docker Hub only keeps the tag's last push:
    # official tags such as python:3.12-slim are rebuilt regularly, so this is the date of
    # the latest rebuild, not of the first release.
    namespace, _, repo = name.rpartition("/")
    namespace = namespace or "library"
    data = http_json(f"https://hub.docker.com/v2/namespaces/{namespace}/repositories/{repo}/tags/{urllib.parse.quote(tag)}")
    return parse_date((data or {}).get("tag_last_pushed") or (data or {}).get("last_updated"))


def action_date(name, version, token):
    # "actions/checkout" or "owner/repo/path". Dependabot gives "7", "v7" or "v7.0.0";
    # a major tag points to the newest release of that major.
    owner, repo = name.split("/")[:2]
    releases = github(f"repos/{owner}/{repo}/releases?per_page=100", token)
    wanted = version if version.startswith("v") else f"v{version}"
    for release in releases:  # newest first
        tag = release["tag_name"]
        if tag in (wanted, version) or tag.startswith(wanted + "."):
            return parse_date(release["published_at"])
    return None


def release_date(ecosystem, name, version, token):
    if not version:
        return None
    try:
        if ecosystem == "pip":
            return pypi_date(name, version)
        if ecosystem == "npm_and_yarn":
            return npm_date(name, version)
        if ecosystem in ("docker", "docker_compose"):
            return docker_date(name, version)
        if ecosystem == "github_actions":
            return action_date(name, version, token)
    except (urllib.error.URLError, ValueError, KeyError) as error:
        print(f"warning: could not get the date of {name} {version}: {error}", file=sys.stderr)
    return None


# --- What the PR updates ---------------------------------------------------------------------

def dependabot_commit_message(repo, number, token):
    commits = github(f"repos/{repo}/pulls/{number}/commits?per_page=100", token)
    messages = [c["commit"]["message"] for c in commits
                if "updated-dependencies:" in c["commit"]["message"]]
    return messages[-1] if messages else ""


def updated_dependencies(message):
    """Names and new versions from the YAML block Dependabot adds to its commits."""
    deps = []
    block = message.split("updated-dependencies:", 1)[-1].split("\n...", 1)[0]
    for item in re.split(r"\n- ", "\n" + block)[1:]:
        name = re.search(r"dependency-name:\s*(\S+)", item)
        version = re.search(r"dependency-version:\s*(\S+)", item)
        if name:
            deps.append({"name": name.group(1).strip("'\""),
                         "to": version.group(1).strip("'\"") if version else ""})
    return deps


def previous_version(message, name, new, title=""):
    """Old version, from the lines Dependabot writes for a single bump, a group or a range."""
    escaped = re.escape(name)
    patterns = [
        rf"Bumps \[?`?{escaped}`?\]?(?:\([^)]*\))? from `?([^\s`]+?)`? to `?{re.escape(new)}`?",
        rf"Updates `{escaped}` from ([^\s`]+) to",
        rf"\|\s*\[?`?{escaped}`?\]?(?:\([^)]*\))?\s*\|\s*`([^`]+)`\s*\|",
    ]
    for pattern in patterns:
        found = re.search(pattern, message)
        if found:
            return found.group(1).rstrip(".")
    # Requirement-range updates only carry a compare link: .../compare/8.0.0...9.2.0
    found = re.search(r"/compare/v?([^.\s/][^\s/]*?)\.\.\.v?" + re.escape(new.lstrip("v")) + r"\b", message)
    if found:
        return found.group(1)
    # Otherwise the PR title has the old range: "Update x requirement from <3.0,>=2.0 to >=2.1.8,<3.0".
    found = re.search(r"requirement from (\S+) to ", title)
    floor = re.search(r">=\s*([0-9][^,\s]*)", found.group(1)) if found else None
    return floor.group(1) if floor else ""


# --- Table -----------------------------------------------------------------------------------

def cell(text):
    return text.replace("|", "\\|") if text else "—"


def build_section(ecosystem, rows, now):
    label = ECOSYSTEM_NAMES.get(ecosystem, ecosystem)
    lines = [
        START,
        "### Release dates",
        "",
        f"| Package | From | To | `From` released | `To` released | Age of `To` |",
        "|---|---|---|---|---|---|",
    ]
    young, unknown = [], []
    for row in rows:
        age = (now - row["to_date"]).days if row["to_date"] else None
        if age is None:
            unknown.append(row["name"])
        elif age < COOLDOWN_DAYS and ecosystem not in ("docker", "docker_compose"):
            young.append(f"`{row['name']}` {row['to']} ({age} days)")
        lines.append("| {} | {} | {} | {} | {} | {} |".format(
            f"`{cell(row['name'])}`", cell(row["from"]), cell(row["to"]),
            row["from_date"].strftime("%Y-%m-%d") if row["from_date"] else "—",
            row["to_date"].strftime("%Y-%m-%d") if row["to_date"] else "—",
            f"{age} days" if age is not None else "—",
        ))
    lines.append("")
    lines.append(f"Ecosystem: {label}. Dates in UTC, checked on {now.strftime('%Y-%m-%d %H:%M')} UTC.")
    if ecosystem in ("docker", "docker_compose"):
        lines.append("For images, Docker Hub only keeps the date of the tag's **latest push**: official "
                     "images are rebuilt often, so these dates are not release dates and are not checked "
                     "against the cooldown.")
    lines.append("")
    if young:
        lines += [
            "> [!WARNING]",
            f"> **Released less than {COOLDOWN_DAYS} days ago:** " + ", ".join(young) + ".",
            f"> Dependabot waits {COOLDOWN_DAYS} days (`cooldown` in `.github/dependabot.yml`) before "
            "proposing a version, so a hijacked or malicious release has time to be found and pulled. "
            "This PR came earlier: it is either a **security update** (which skips the cooldown on "
            "purpose) or the version was released again. Check the package's release notes and "
            f"registry page before merging, or wait until it is {COOLDOWN_DAYS} days old.",
        ]
    elif unknown:
        lines += [
            "> [!NOTE]",
            "> Could not find the release date of: " + ", ".join(f"`{u}`" for u in unknown)
            + ". Check it in the package registry before merging.",
        ]
    elif ecosystem not in ("docker", "docker_compose"):
        lines += [
            "> [!NOTE]",
            f"> Every new version is at least {COOLDOWN_DAYS} days old.",
        ]
    lines.append(END)
    return "\n".join(lines)


def replace_section(body, section):
    body = body or ""
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if pattern.search(body):
        return pattern.sub(lambda _: section, body, count=1)
    return section + "\n\n" + body


def main():
    number = int(sys.argv[1])
    dry_run = "--dry-run" in sys.argv
    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]

    pr = github(f"repos/{repo}/pulls/{number}", token)
    ref = pr["head"]["ref"]
    if not ref.startswith("dependabot/"):
        print(f"#{number} is not a Dependabot PR ({ref}); nothing to do.")
        return
    ecosystem = ref.split("/")[1]
    message = dependabot_commit_message(repo, number, token)
    deps = updated_dependencies(message)
    if not deps:
        print(f"#{number}: no updated-dependencies block found; nothing to do.")
        return

    now = dt.datetime.now(dt.timezone.utc)
    rows = []
    for dep in deps:
        old = previous_version(message, dep["name"], dep["to"], pr["title"])
        rows.append({
            "name": dep["name"], "from": old, "to": dep["to"],
            "from_date": release_date(ecosystem, dep["name"], old, token),
            "to_date": release_date(ecosystem, dep["name"], dep["to"], token),
        })

    section = build_section(ecosystem, rows, now)
    if dry_run:
        print(section)
        return
    new_body = replace_section(pr["body"], section)
    if new_body != (pr["body"] or ""):
        github(f"repos/{repo}/pulls/{number}", token, method="PATCH", body={"body": new_body})
    print(section)


if __name__ == "__main__":
    main()
