import urllib.request
import json

url = "https://api.github.com/repos/Omar-Sa03/llm-code-reviewer/pulls/2"
req = urllib.request.Request(url)
req.add_header('User-Agent', 'Mozilla/5.0')
try:
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        print(f"PR #2:")
        print(f"State: {data.get('state')}")
        print(f"Mergeable: {data.get('mergeable')}")
        print(f"Draft: {data.get('draft')}")
        print(f"Mergeable State: {data.get('mergeable_state')}")
        print(f"Commits: {data.get('commits')}")
        print(f"Changed Files: {data.get('changed_files')}")
        print(f"Additions: {data.get('additions')}")
        print(f"Deletions: {data.get('deletions')}")
except Exception as e:
    print("Error:", e)
