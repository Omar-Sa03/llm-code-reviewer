from reviewer.diff_parser import parse_diff, should_skip, DiffChunk


SAMPLE_DIFF = """\
diff --git a/app/auth.py b/app/auth.py
index abc..def 100644
--- a/app/auth.py
+++ b/app/auth.py
@@ -10,6 +10,9 @@
 def existing_function():
     pass
+
+def login(user, password):
+    return db.query(f"SELECT * FROM users WHERE pass='{password}'")
diff --git a/app/utils.py b/app/utils.py
index 111..222 100644
--- a/app/utils.py
+++ b/app/utils.py
@@ -1,3 +1,5 @@
 import os
+
+SECRET_KEY = "hardcoded-secret-123"
"""


def test_parses_two_files():
    chunks = list(parse_diff(SAMPLE_DIFF))
    assert len(chunks) == 2


def test_correct_file_paths():
    chunks = list(parse_diff(SAMPLE_DIFF))
    paths = [c.file_path for c in chunks]
    assert "app/auth.py"   in paths
    assert "app/utils.py"  in paths


def test_correct_start_lines():
    chunks = list(parse_diff(SAMPLE_DIFF))
    auth_chunk = next(c for c in chunks if c.file_path == "app/auth.py")
    assert auth_chunk.start_line == 10


def test_content_contains_added_lines():
    chunks = list(parse_diff(SAMPLE_DIFF))
    auth_chunk = next(c for c in chunks if c.file_path == "app/auth.py")
    assert "SELECT" in auth_chunk.content


def test_skip_lock_files():
    assert should_skip("package-lock.json") is True
    assert should_skip("yarn.lock")          is True
    assert should_skip("app/auth.py")        is False


def test_skip_generated_files():
    assert should_skip("dist/bundle.js")     is True
    assert should_skip("app/utils.py")       is False


def test_empty_diff():
    chunks = list(parse_diff(""))
    assert chunks == []

# run tests
# pytest tests/test_diff_parser.py