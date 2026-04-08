import re
from dataclasses import dataclass
from typing import Generator

@dataclass
class DiffChunk:
    file: str
    content: str
    start_line: int
    
def parse_diff(raw_diff: str) -> Generator[DiffChunk, None, None]:
    current_file = None
    current_lines = []
    current_start = 1

    for line in raw_diff.splitlines():
        if line.startswith("+++ b/"):
            if current_file and current_lines:
                yield DiffChunk(current_file, "\n".join(current_lines), current_start)
            current_file = line[6:]
            current_lines = []
        elif line.startswith("@@ "):
            match = re.search(r"\+(\d+)", line)
            current_start = int(match.group(1)) if match else 1
        elif current_file:
            current_lines.append(line)
    
    if current_file and current_lines:
        yield DiffChunk(current_file, "\n".join(current_lines), current_start)
