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

    for line in raw_diff.splitlines():
        if line.startswith("+++ b/"):
            # Flush previous file
            if current_file and current_lines:
                yield DiffChunk(
                    file_path=current_file,
                    content="\n".join(current_lines),
                    start_line=current_start,
                )
            current_file = line[6:].strip()
            current_lines = []
            current_start = 1

        elif line.startswith("@@ "):
            match = re.search(r"\+(\d+)", line)
            if match:
                current_start = int(match.group(1))
            current_lines = []

        elif current_file:
            current_lines.append(line)

    if current_file and current_lines:
        yield DiffChunk(
            file_path=current_file,
            content="\n".join(current_lines),
            start_line=current_start,
        )