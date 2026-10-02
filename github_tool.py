"""
github_tool.py — GitHub API access for JOI2.0

Requires a GitHub Personal Access Token (fine-grained, scoped to only the
repos JOI needs) stored in an environment variable — never hardcode it.

    export GITHUB_TOKEN="ghp_..."

Uses raw `requests` against the REST API so there's no extra dependency
beyond what you likely already have.
"""

import os
import base64
import requests

GITHUB_API = "https://api.github.com"


class GitHubTool:
    def __init__(self, token: str | None = None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise RuntimeError(
                "No GitHub token found. Set GITHUB_TOKEN in your environment."
            )
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    # ---------- read ----------

    def get_file(self, owner: str, repo: str, path: str, ref: str = "main") -> str:
        """Fetch a file's decoded text content from a repo."""
        url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
        r = requests.get(url, headers=self.headers, params={"ref": ref})
        r.raise_for_status()
        data = r.json()
        return base64.b64decode(data["content"]).decode("utf-8")

    def list_repo_files(self, owner: str, repo: str, path: str = "", ref: str = "main") -> list:
        """List files/dirs at a given path in the repo."""
        url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
        r = requests.get(url, headers=self.headers, params={"ref": ref})
        r.raise_for_status()
        return [item["path"] for item in r.json()]

    def search_code(self, query: str, owner: str = None, repo: str = None) -> list:
        """Search code across GitHub (or scoped to one repo)."""
        q = query
        if owner and repo:
            q += f" repo:{owner}/{repo}"
        r = requests.get(
            f"{GITHUB_API}/search/code",
            headers=self.headers,
            params={"q": q},
        )
        r.raise_for_status()
        return [item["path"] for item in r.json().get("items", [])]

    def list_issues(self, owner: str, repo: str, state: str = "open") -> list:
        r = requests.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/issues",
            headers=self.headers,
            params={"state": state},
        )
        r.raise_for_status()
        return [{"number": i["number"], "title": i["title"]} for i in r.json()]

    # ---------- write ----------

    def create_or_update_file(
        self, owner: str, repo: str, path: str, content: str,
        message: str, branch: str = "main"
    ) -> dict:
        """Commit a new or updated file. Fetches current sha if the file exists."""
        url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
        sha = None
        existing = requests.get(url, headers=self.headers, params={"ref": branch})
        if existing.status_code == 200:
            sha = existing.json()["sha"]

        payload = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha

        r = requests.put(url, headers=self.headers, json=payload)
        r.raise_for_status()
        return r.json()

    def create_issue(self, owner: str, repo: str, title: str, body: str = "") -> dict:
        r = requests.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/issues",
            headers=self.headers,
            json={"title": title, "body": body},
        )
        r.raise_for_status()
        return r.json()

    def create_branch(self, owner: str, repo: str, new_branch: str, from_branch: str = "main") -> dict:
        ref = requests.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/git/ref/heads/{from_branch}",
            headers=self.headers,
        )
        ref.raise_for_status()
        sha = ref.json()["object"]["sha"]
        r = requests.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/git/refs",
            headers=self.headers,
            json={"ref": f"refs/heads/{new_branch}", "sha": sha},
        )
        r.raise_for_status()
        return r.json()

    def create_pull_request(
        self, owner: str, repo: str, title: str, head: str, base: str = "main", body: str = ""
    ) -> dict:
        r = requests.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
            headers=self.headers,
            json={"title": title, "head": head, "base": base, "body": body},
        )
        r.raise_for_status()
        return r.json()


if __name__ == "__main__":
    gh = GitHubTool()
    print(gh.list_issues("octocat", "Hello-World"))