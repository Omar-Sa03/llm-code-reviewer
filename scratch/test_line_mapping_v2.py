
def map_to_local_line(hunk_content: str, relative_line: int, start_line: int) -> int:
    """Calculates the real file line number for a given hunk relative index."""
    lines = hunk_content.splitlines()
    new_file_line = start_line
    for i, line in enumerate(lines):
        if i + 1 == relative_line:
            return new_file_line
        if not line.startswith("-"):
            new_file_line += 1
    return new_file_line

hunk = """+import os
+import hashlib
+
+
+API_SECRET = "sk-super-secret-key-123456" # hardcoded secret
+
+
+def get_user(db, username):
+    query = f"SELECT * FROM users WHERE username = '{username}'"
+    return db.execute(query)"""

print(f"Index 1 -> Line {map_to_local_line(hunk, 1, 1)}")
print(f"Index 5 -> Line {map_to_local_line(hunk, 5, 1)}")

hunk_with_context = """ def foo():
-    old
+    new
  pass"""

print(f"Hunk with context starts at 10")
print(f"Index 1 (context) -> Line {map_to_local_line(hunk_with_context, 1, 10)}")
print(f"Index 3 (new)     -> Line {map_to_local_line(hunk_with_context, 3, 10)}")
print(f"Index 4 (context) -> Line {map_to_local_line(hunk_with_context, 4, 10)}")
