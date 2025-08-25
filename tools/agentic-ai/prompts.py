def build_prompts(parsed: str, code_ctx: str, spec_ctx: str, cfg_ctx: str):
    return {
        "summary": f"""
You are a senior QA+Backend agent.
Summarize Specmatic/JUnit failures by endpoint and cause. Classify each as:
(a) API behavior bug, (b) wrong OpenAPI spec, (c) Specmatic config, (d) test data.
Keep it concise and actionable.

PARSED_RESULTS:
{parsed}
""",
        "api": f"""
You are a senior Java engineer. Propose minimal code changes to pass Specmatic tests.
Rules:
- Only changes required by failures.
- Point exact classes/methods from context.
- Prefer small unified diffs, else precise snippets.

CODE CONTEXT:
{code_ctx}

FAILURES:
{parsed}
""",
        "spec": f"""
You are an OpenAPI expert. Propose minimal OpenAPI YAML changes if spec is the cause.
Ensure status codes, required fields, and examples match behavior.

OPENAPI CONTEXT:
{spec_ctx}

FAILURES:
{parsed}
""",
        "specmatic": f"""
You are a Specmatic power user. Suggest config tweaks (matchers, optional fields,
examples directory, base URL, headers, timeouts). Return a tiny JSON/YAML snippet.

CURRENT CONFIG:
{cfg_ctx}

FAILURES:
{parsed}
""",
        "diffs": f"""
Emit minimal unified diffs to fix failures.
Priority: (1) API code if spec is correct, else (2) spec changes, (3) specmatic config.
Constraints:
- Keep diffs small and consistent.
- Use ```diff fenced blocks with headers: --- a/<path>  +++ b/<path>

CODE CONTEXT:
{code_ctx}

OPENAPI CONTEXT:
{spec_ctx}

SPECMATIC CONFIG:
{cfg_ctx}

FAILURES:
{parsed}
"""
    }
