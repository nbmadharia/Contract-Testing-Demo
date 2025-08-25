import re

BLOCK = re.compile(r"```diff\s+(.*?)```", re.DOTALL | re.IGNORECASE)
FILE  = re.compile(r"^\-\-\-\s+a\/(.+)$", re.MULTILINE)

def extract_unified_diffs(text: str) -> dict[str,str]:
    out = {}
    for m in BLOCK.finditer(text or ""):
        diff = m.group(1).strip()
        fm = FILE.search(diff)
        path = fm.group(1).strip() if fm else "patch.diff"
        out[path] = diff
    return out
