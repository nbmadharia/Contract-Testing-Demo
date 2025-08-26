import re

BLOCK = re.compile(r"```diff\s+(.*?)```", re.DOTALL | re.IGNORECASE)
FILE  = re.compile(r"^\-\-\-\s+(a\/.+|\/dev\/null)$", re.MULTILINE)

JAVA_FILE_HEADER = re.compile(r"^\s*//\s*FILE:\s*(.+)$", re.MULTILINE)
JAVA_BLOCK = re.compile(r"```java\s+(.*?)```", re.DOTALL | re.IGNORECASE)

def extract_unified_diffs(text: str) -> dict[str,str]:
    out = {}
    for m in BLOCK.finditer(text or ""):
        diff = m.group(1).strip()
        # take the first --- header to infer path
        fm = FILE.search(diff)
        path = "patch.diff"
        if fm:
            # if it's /dev/null, try to read +++ header
            plus = re.search(r"^\+\+\+\s+b\/(.+)$", diff, re.MULTILINE)
            if plus:
                path = plus.group(1).strip()
        out[path] = diff
    return out

def extract_full_java_files(text: str) -> dict[str,str]:
    """
    Accepts blocks like:
      // FILE: src/main/java/com/foo/Bar.java
      <code...>
    wrapped inside ```java fences.
    """
    results = {}
    for block in JAVA_BLOCK.finditer(text or ""):
        snippet = block.group(1)
        header = JAVA_FILE_HEADER.search(snippet)
        if header:
            path = header.group(1).strip()
            # remove header line
            payload = JAVA_FILE_HEADER.sub("", snippet, count=1).lstrip()
            results[path] = payload
    return results

def has_any_code(text: str) -> bool:
    if BLOCK.search(text or ""): return True
    if JAVA_BLOCK.search(text or "") and JAVA_FILE_HEADER.search(text or ""): return True
    return False
