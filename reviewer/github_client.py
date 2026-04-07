import os, requests

class GithubClient:
    def __init__(self):
        self.token = os.environ("GITHUB_TOKEN")
        self.repo = os.environ["GITHUB_REPOSITORY"]
        self.pr_number = int(os.environ["PR_NUMBER"])
        self.base = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }

    def get_pr_diff(self):
        url = f"{self.base}/repos/{self.repo}/pulls/{self.pr_number}"
        r = requests.get(url, headers={**self.headers, "Accept": "application/vnd.github.v3.diff"})
        r.raise_for_status()
        return r.text

    def post_review_comment(self, commit_sha: str, path: str, line: int, body: str):
        url = f"{self.base}/repos/{self.repo}/pulls/{self.pr_number}/comments"
        payload = {
            body: body,
            commit_id: commit_sha,
            path: path,
            line: line,
            side: "right"
        }
        r = requests.post(url, headers=self.headers, json=payload)
        r.raise_for_status()

    def post_pr_summary(self, body: str):
        url = f"{self.base}/repos/{self.repo}/issues/{self.pr_number}/comments"
        r = requests.post(url, json={"body": body}, headers=self.headers)
        r.raise_for_status()