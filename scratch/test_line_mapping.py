
from reviewer.main import map_to_local_line

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

# Line 1: import os
# Line 2: import hashlib
# Line 3: 
# Line 4: 
# Line 5: API_SECRET
# ...

print(f"Index 1 -> Line {map_to_local_line(hunk, 1, 1)}")
print(f"Index 5 -> Line {map_to_local_line(hunk, 5, 1)}")

hunk_with_context = """ def foo():
-    old
+    new
  pass"""
# Line 1:  def foo() (File Line 10)
# Line 2: -old       (File N/A)
# Line 3: +new       (File Line 11)
# Line 4:  pass      (File Line 12)

print(f"Hunk with context starts at 10")
print(f"Index 1 (context) -> Line {map_to_local_line(hunk_with_context, 1, 10)}")
print(f"Index 3 (new)     -> Line {map_to_local_line(hunk_with_context, 3, 10)}")
print(f"Index 4 (context) -> Line {map_to_local_line(hunk_with_context, 4, 10)}")
