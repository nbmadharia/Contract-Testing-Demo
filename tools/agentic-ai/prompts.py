DIFF_RULES = """
REQUIREMENTS (very important):
- Prefer UNIFIED DIFFS inside ```diff fences:
  - Existing file: headers MUST be '--- a/<path>' and '+++ b/<path>'.
  - New file: use '--- /dev/null' then '+++ b/<path>'.
  - Include @@ hunks with exact line numbers.
- If (and only if) you cannot reliably produce a diff, emit a FULL FILE inside ```java fences with a header line:
  // FILE: <relative/path/from/repo/root>
  followed by the entire updated file.
- Do NOT output prose around diffs/snippets, only the code/diff blocks.
- Keep changes minimal and compilable.
"""

def build_prompts(parsed: str, code_ctx: str, spec_ctx: str, cfg_ctx: str, file_index: str = ""):
    return {
        "summary": f"""
You are a senior QA+Backend agent.
Summarize Specmatic/JUnit failures by endpoint and cause. Classify each failure as:
(a) API behavior bug, (b) wrong OpenAPI spec, (c) Specmatic config, (d) test data.
Return a short actionable list.

PARSED_RESULTS:
{parsed}
""",
        "api": f"""
You are a senior Java engineer. Generate ACTUAL CHANGES to pass Specmatic tests.

{DIFF_RULES}

CONTEXT:
- Important code files and bits:
{code_ctx}

- File index (paths you may edit or create under repo root):
{file_index}

FAILURES (root cause to fix in code first unless spec is wrong):
{parsed}
""",
        "spec": f"""
You are an OpenAPI expert. If the failures indicate SPEC mismatch, produce minimal OpenAPI edits.

{DIFF_RULES}

OPENAPI CONTEXT:
{spec_ctx}

FILE INDEX (so you know candidate spec file paths):
{file_index}

FAILURES:
{parsed}
""",
        "specmatic": f"""
You are a Specmatic power user. If config is the issue, emit minimal config edits (json/yaml).

{DIFF_RULES}

CURRENT CONFIG:
{cfg_ctx}

FILE INDEX:
{file_index}

FAILURES:
{parsed}
""",
        "diffs": f"""
You are a code-mod agent. Emit ONLY minimal unified diffs (or full-file code blocks if necessary) to fix the failures.

{DIFF_RULES}

PRIORITY ORDER:
1) API Java code (controllers, services, DTOs) to meet the contract
2) Then spec edits if the contract is wrong
3) Then Specmatic config tweaks

CODE CONTEXT:
{code_ctx}

OPENAPI CONTEXT:
{spec_ctx}

SPECMATIC CONFIG:
{cfg_ctx}

FILE INDEX:
{file_index}

FAILURES:
{parsed}
"""
    }
