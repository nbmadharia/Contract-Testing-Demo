import os, sys, subprocess, pathlib, time
from colorama import Fore, Style
from parser import parse_surefire_and_specmatic
from repo_utils import snapshot_code, read_specs, read_if_exists, ensure_outdir
from llm_client import OllamaClient
from prompts import build_prompts
from diff_utils import extract_unified_diffs
import yaml

def _trim(s: str, maxlen: int) -> str:
    if s is None:
        return ""
    return s if len(s) <= maxlen else s[:maxlen] + "\n...[trimmed for fast mode]..."

class Agent:
    """
    Runs contract tests, parses failures, asks LLM for concrete fixes (diffs/snippets),
    and writes artifacts under .agentic/
    """

    def __init__(self, config_path: str, verbose: bool = False, fast: bool = None, require_diffs: bool = None):
        with open(config_path, "r") as f:
            self.cfg = yaml.safe_load(f) or {}

        self.repo_root  = pathlib.Path(self.cfg.get("repo_root", "../../")).resolve()
        self.output_dir = ensure_outdir(self.repo_root / self.cfg.get("output_dir", ".agentic"))
        self.client     = OllamaClient(self.cfg["ollama"])
        self.verbose    = verbose

        if fast is None:
            env_fast = os.getenv("AGENT_FAST", "").strip().lower() in {"1","true","yes","on"}
            self.fast = env_fast or bool(self.cfg.get("fast", False))
        else:
            self.fast = bool(fast)

        if require_diffs is None:
            env_req = os.getenv("AGENT_REQUIRE_DIFFS", "").strip().lower() in {"1","true","yes","on"}
            self.require_diffs = env_req or bool(self.cfg.get("require_diffs", False))
        else:
            self.require_diffs = bool(require_diffs)

        # demo trimming limits for fast mode onlyy
        self.fast_limits = {
            "summary":   int(os.getenv("AGENT_FAST_SUMMARY",   "3500")),
            "api":       int(os.getenv("AGENT_FAST_API",       "6000")),
            "spec":      int(os.getenv("AGENT_FAST_SPEC",      "4000")),
            "specmatic": int(os.getenv("AGENT_FAST_SPECMATIC", "3000")),
            "diffs":     int(os.getenv("AGENT_FAST_DIFFS",     "5000")),
        }

    # ---------------- helpers ------------------------------

    def _llm_call(self, which: str, prompt: str, label: str) -> str:
        """
        LLM call with verbose logs & timing.
        Streams tokens live if client exposes generate_stream() and verbose is True.
        """
        if self.verbose:
            print(f"[DEBUG] {label}: prompt chars={len(prompt)} fast={self.fast}")

        t0 = time.time()
        text = ""

        if self.verbose and hasattr(self.client, "generate_stream"):
            try:
                print(f"[DEBUG] Streaming {label}...")
                buf = []
                for chunk in self.client.generate_stream(which, prompt, fast=self.fast):
                    piece = (
                        (chunk.get("response") if isinstance(chunk, dict) else None) or
                        (chunk.get("message", {}) or {}).get("content", "") if isinstance(chunk, dict) else ""
                    )
                    if piece:
                        sys.stdout.write(piece)
                        sys.stdout.flush()
                        buf.append(piece)
                print()
                text = "".join(buf)
            except Exception as e:
                print(f"[WARN] Stream failed for {label}: {e}. Falling back.")
                try:
                    text = self.client.complete(which, prompt, fast=self.fast, verbose=self.verbose)
                except TypeError:
                    text = self.client.complete(which, prompt)
        else:
            try:
                text = self.client.complete(which, prompt, fast=self.fast, verbose=self.verbose)
            except TypeError:
                text = self.client.complete(which, prompt)

        if self.verbose:
            print(f"[DEBUG] {label}: took {time.time()-t0:.1f}s; out chars={len(text)}")
        return text or ""

    def _maybe_trim_for_fast(self, prompts: dict) -> dict:
        """Trim prompts in fast mode for responsiveness."""
        if not self.fast:
            return prompts
        return {
            "summary":   _trim(prompts["summary"],   self.fast_limits["summary"]),
            "api":       _trim(prompts["api"],       self.fast_limits["api"]),
            "spec":      _trim(prompts["spec"],      self.fast_limits["spec"]),
            "specmatic": _trim(prompts["specmatic"], self.fast_limits["specmatic"]),
            "diffs":     _trim(prompts["diffs"],     self.fast_limits["diffs"]),
        }

    def _ask_for_diffs_with_retry(self, diffs_prompt: str) -> str:
        """
        Ask the LLM for diffs. If none are detected, retry once with stronger rules
        and 'ONLY code blocks' instruction. Returns raw model output (not just diffs).
        """
        # First attempt
        raw = self._llm_call("coder_model", diffs_prompt, label="Diffs (attempt 1)")
        if extract_unified_diffs(raw):
            return raw

        if self.verbose:
            print("[WARN] No unified diffs found on attempt 1. Retrying with stronger instruction...")

        stronger = diffs_prompt + """

            IMPORTANT:
            - You MUST output one or more unified diffs inside ```diff fences.
            - Use headers exactly:  --- a/<path>   +++ b/<path>
            - Include @@ hunks with correct line numbers.
            - If a new file is required, use:  --- /dev/null   +++ b/<path>
            - DO NOT include any prose or explanation, only code blocks.
            """
        # Second attempt
        try:
            raw2 = self.client.complete("coder_model", stronger, fast=True, verbose=self.verbose)
        except TypeError:
            raw2 = self.client.complete("coder_model", stronger)

        return raw2 or raw

    # ---------------- MAIN Flow -----------------------------------------

    def run_once(self, propose_patches: bool = False):

        print(Fore.CYAN + ">> Running contract tests..." + Style.RESET_ALL)
        t0 = time.time()
        test_out = self._run_tests()
        if self.verbose:
            print(f"[DEBUG] Tests exit={test_out['exit']} in {time.time()-t0:.1f}s")


        #Parsing the test reports ------------

        print(Fore.CYAN + ">> Parsing test reports..." + Style.RESET_ALL)
        parsed = parse_surefire_and_specmatic(
            self.repo_root / self.cfg["surefire_dir"],
            (self.repo_root / self.cfg["surefire_dir"]).parent / self.cfg.get("specmatic_log", "specmatic.log")
        )
        if self.verbose:
            print("[DEBUG] Parsed summary chars:", len(parsed))




        print(Fore.CYAN + ">> Collecting context..." + Style.RESET_ALL)
        code_ctx = snapshot_code(self.repo_root, [
            "src/main/java", "src/main/resources", "pom.xml",
            self.cfg.get("specmatic_config", "specmatic.yaml")
        ], self.cfg["limits"])
        spec_ctx = read_specs(self.repo_root, self.cfg["spec_keyword"], self.cfg["limits"])
        cfg_ctx  = read_if_exists(self.repo_root, self.cfg.get("specmatic_config", "specmatic.yaml"))

        if self.verbose:
            print("[DEBUG] code_ctx chars:", len(code_ctx), "| spec_ctx chars:", len(spec_ctx), "| cfg_ctx chars:", len(cfg_ctx))


        #LLM: summaries & suggestions ------------------

        prompts = build_prompts(parsed, code_ctx, spec_ctx, cfg_ctx)
        prompts = self._maybe_trim_for_fast(prompts)

        print(Fore.CYAN + ">> Summarizing failures..." + Style.RESET_ALL)
        llm_summary = self._llm_call("planner_model", prompts["summary"], label="Summary")

        print(Fore.CYAN + ">> Suggesting API changes (concrete code)..." + Style.RESET_ALL)
        api_suggestions = self._llm_call("coder_model", prompts["api"], label="API suggestions")

        print(Fore.CYAN + ">> Suggesting Spec changes..." + Style.RESET_ALL)
        spec_suggestions = self._llm_call("coder_model", prompts["spec"], label="Spec suggestions")

        print(Fore.CYAN + ">> Suggesting Specmatic config..." + Style.RESET_ALL)
        specmatic_suggestions = self._llm_call("planner_model", prompts["specmatic"], label="Specmatic suggestions")

        # diff part still needs work
        proposed_patches = {}
        if propose_patches:
            print(Fore.CYAN + ">> Asking for unified diffs..." + Style.RESET_ALL)
            diff_text = self._ask_for_diffs_with_retry(prompts["diffs"])

            # Always persist raw LLM output for inspection
            raw_path = self.output_dir / "raw_diffs_or_snippets.txt"
            raw_path.write_text(diff_text or "", encoding="utf-8")

            # Extract and write .diff files
            proposed_patches = extract_unified_diffs(diff_text or "")
            patches_dir = self.output_dir / "patches"
            patches_dir.mkdir(parents=True, exist_ok=True)
            count = 0
            for i, (path, diff) in enumerate(proposed_patches.items(), 1):
                (patches_dir / f"patch_{i:02d}.diff").write_text(diff, encoding="utf-8")
                count += 1

            if self.verbose:
                print(f"[DEBUG] Diff files written: {count} in {patches_dir}")

            if count == 0:
                print(Fore.YELLOW + ">> No unified diffs detected. See .agentic/raw_diffs_or_snippets.txt" + Style.RESET_ALL)
                if self.require_diffs:
                    raise RuntimeError("Require-diffs is enabled, but no diffs were produced by the model.")

        # Save outputs -------------------------

        (self.output_dir / "summary.txt").write_text(llm_summary or "", encoding="utf-8")
        (self.output_dir / "api_suggestions.txt").write_text(api_suggestions or "", encoding="utf-8")
        (self.output_dir / "spec_suggestions.txt").write_text(spec_suggestions or "", encoding="utf-8")
        (self.output_dir / "specmatic_suggestions.txt").write_text(specmatic_suggestions or "", encoding="utf-8")
        (self.output_dir / "parsed.txt").write_text(parsed or "", encoding="utf-8")
        (self.output_dir / "test_stdout.txt").write_text(test_out["stdout"] or "", encoding="utf-8")
        (self.output_dir / "test_stderr.txt").write_text(test_out["stderr"] or "", encoding="utf-8")

        return {
            "testsPassed": test_out["exit"] == 0,
            "parseSummary": parsed,
            "llmSummary": llm_summary,
            "apiSuggestions": api_suggestions,
            "specSuggestions": spec_suggestions,
            "specmaticSuggestions": specmatic_suggestions,
            "proposedPatchCount": len(proposed_patches),
            "patchesDir": str(self.output_dir / "patches") if propose_patches else None,
            "fastMode": self.fast
        }

    def _run_tests(self):
        cmd = self.cfg["test_command"]
        try:
            args = cmd if isinstance(cmd, list) else cmd.split()
            proc = subprocess.Popen(
                args,
                cwd=self.repo_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            out, err = proc.communicate()
            return {"exit": proc.returncode, "stdout": out, "stderr": err}
        except Exception as e:
            return {"exit": 1, "stdout": "", "stderr": f"SHELL_ERROR: {e}"}
