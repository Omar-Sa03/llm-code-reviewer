import re
from dataclasses import dataclass, field
from typing import Generator


SKIP_PATTERNS = [
    r".*\.lock$",
    r".*package-lock\.json$",
    r".*yarn\.lock$",
    r".*migrations/.*\.py$",
    r".*\.min\.js$",
    r".*\.min\.css$",
    r".*_pb2\.py$",
    r".*\.snap$",
    r".*dist/.*",
    r".*build/.*",
    r".*\.generated\.\w+$",
]


@dataclass
class DiffChunk:
    file_path: str
    content: str
    start_line: int


def should_skip(file_path: str) -> bool:
    return any(re.match(pattern, file_path) for pattern in SKIP_PATTERNS)


def parse_diff(raw_diff: str) -> Generator[DiffChunk, None, None]:
    current_file = None
    current_lines: list[str] = []
    current_start = 1

    def flush():
        nonlocal current_lines
        if current_file and current_lines:
            yield DiffChunk(
                file_path=current_file,
                content="\n".join(current_lines),
                start_line=current_start,
            )
            current_lines = []

    for line in raw_diff.splitlines():
        if line.startswith("+++ b/"):
            yield from flush()
            current_file = line[6:].strip()
            current_start = 1
        elif line.startswith("@@ "):
            yield from flush()
            match = re.search(r"\+(\d+)", line)
            if match:
                current_start = int(match.group(1))
        elif current_file:
            if line.startswith("--- ") or line.startswith("index "):
                continue
            current_lines.append(line)

    yield from flush()