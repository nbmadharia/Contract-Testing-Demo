from pathlib import Path

def ensure_outdir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    (p / "patches").mkdir(parents=True, exist_ok=True)
    return p

def _read_file(p: Path, max_chars: int) -> str:
    try:
        s = p.read_text(encoding="utf-8", errors="ignore")
        return s[:max_chars]
    except Exception as e:
        return f"READ_ERROR({p}): {e}"

def snapshot_code(root: Path, rels: list[str], limits: dict) -> str:
    max_files = limits.get("files_per_section", 60)
    max_chars = limits.get("max_context_chars", 120000)
    chunks, count, used = [], 0, 0
    for r in rels:
        p = (root / r)
        if p.is_file():
            content = _read_file(p, max_chars - used)
            chunks.append(f"\n--- FILE: {p} ---\n{content}\n")
            used += len(content)
        elif p.is_dir():
            for f in p.rglob("*"):
                if f.suffix.lower() in {".java", ".yml", ".yaml", ".json"} or f.name == "pom.xml":
                    content = _read_file(f, max_chars - used)
                    chunks.append(f"\n--- FILE: {f} ---\n{content}\n")
                    used += len(content)
                    count += 1
                    if count >= max_files or used >= max_chars:
                        break
        if count >= max_files or used >= max_chars:
            break
    return "".join(chunks)

def read_specs(root: Path, keyword: str, limits: dict) -> str:
    max_files = limits.get("files_per_section", 60)
    max_chars = limits.get("max_context_chars", 120000)
    chunks, count, used = [], 0, 0
    for f in root.rglob("*"):
        if f.is_file() and f.suffix.lower() in {".yaml",".yml",".json"} and keyword.lower() in str(f).lower():
            content = _read_file(f, max_chars - used)
            chunks.append(f"\n--- FILE: {f} ---\n{content}\n")
            used += len(content)
            count += 1
            if count >= max_files or used >= max_chars:
                break
    return "".join(chunks)

def read_if_exists(root: Path, rel: str) -> str:
    p = root / rel
    return f"\n--- FILE: {p} ---\n{_read_file(p, 50000)}\n" if p.exists() else ""
