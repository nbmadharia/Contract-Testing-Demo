import os, sys, subprocess, json, pathlib, time
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
    Agent that:
      1) runs contract tests
      2) parses results
      3) asks LLM for summary + concrete fixes (API/spec/specmatic)
      4) optionally asks for unified diffs and writes them to .agentic/patches/
    """

    def __init__(self, config_path: str, verbose: bool = False, fast: bool = None):
        with open(config_path, "r") as f:
            self.cfg = yaml.safe_load(f) or {}
        self.repo_root = pathlib.Path(self.cfg.get("repo_root", "../../")).resolve()
        self.output_dir = ensure_outdir(self.repo_root / self.cfg.get("output_dir", ".agentic"))
        self.client = OllamaClient(self.cfg["ollama"])
        self.verbose = verbose

        # fast mode: prefer env var first, then config.yaml fast: true
        if fast is None:
            env_fast = os.getenv("AGENT_FAST", "").strip().lower() in {"1","true","yes","on"}
            cfg_fast = bool(self.cfg.get("fast", False))
            self.fast = env_fast or cfg_fast
        else:
            self.fast = bool(fast)

        # demo-friendly defaults for trimming if fast mode
        self.fast_limits = {
            "summary":   int(os.getenv("AGENT_FAST_SUMMARY", "3500")),
            "api":       int(os.getenv("AGENT_FAST_API", "6000")),
            "spec":      int(os.getenv("AGENT_FAST_SPEC", "4000")),
            "specmatic": int(os.getenv("AGENT_FAST_SPECMATIC", "3000")),
            "diffs":     int(os.getenv("AGENT_FAST_DIFFS", "5000")),
        }

    # ---------------- internal helpers ----------------

    def _llm_call(self, which: str, prompt: str, label: str) -> str:
        """
        Makes an LLM call with nice logs and streaming if available & verbose.
        'which' is "planner_model" or "coder_model".
        """
        if self.verbose:
            print(f"[DEBUG] {label} prompt size: {len(prompt)} (fast={self.fast})")

        t0 = time.time()
        text = ""

        # If the client has generate_stream and verbose is ON, stream tokens live
        if self.verbose and hasattr(self.client, "generate_stream"):
            try:
                print(f"[DEBUG] Streaming {label} tokens...")
                buf = []
                for chunk in self.client.generate_stream(which, prompt, fast=getattr(self, "fast", False)):
                    piece = (
                        (chunk.get("response") if isinstance(chunk, dict) else None) or
                        (chunk.get("message", {}) or {}).get("content", "") if isinstance(chunk, dict) else ""
                    )
                    if piece:
                        sys.stdout.write(piece)
                        sys.stdout.flush()
                        buf.append(piece)
                print()  # newline after stream
                text = "".join(buf)
            except Exception as e:
                print(f"[WARN] Streaming failed for {label}: {e}. Falling back to non-streaming.")
                text = self.client.complete(which, prompt, fast=getattr(self, "fast", False), verbose=self.verbose) \
                       if "fast" in self.client.complete.__code__.co_varnames else \
                       self.client.complete(which, prompt)
        else:
            # Non-streaming path (compat with your current client signature)
            try:
                if "fast" in self.client.complete.__code__.co_varnames:
                    text = self.client.complete(which, prompt, fast=getattr(self, "fast", False), verbose=self.verbose)
                else:
                    text = self.client.complete(which, prompt)
            except TypeError:
                # Older client signature: complete(which, prompt)
                text = self.client.complete(which, prompt)

        dur = time.time() - t0
        if self.verbose:
            print(f"[DEBUG] {label} took: {dur:.1f}s; output chars: {len(text)}")
        return text

    def _maybe_trim_for_fast(self, prompts: dict) -> dict:
        if not self.fast:
            return prompts
        return {
            "summary":   _trim(prompts["summary"],   self.fast_limits["summary"]),
            "api":       _trim(prompts["api"],       self.fast_limits["api"]),
            "spec":      _trim(prompts["spec"],      self.fast_limits["spec"]),
            "specmatic": _trim(prompts["specmatic"], self.fast_limits["specmatic"]),
            "diffs":     _trim(prompts["diffs"],     self.fast_limits["diffs"]),
        }

    # ---------------- public flow ----------------

    def run_once(self, propose_patches: bool = False):
        # 1) Run tests
        print(Fore.CYAN + ">> Running contract tests..." + Style.RESET_ALL)
        t0 = time.time()
        test_out = self._run_tests()
        if self.verbose:
            print(f"[DEBUG] Tests exit={test_out['exit']} in {time.time()-t0:.1f}s")

        # 2) Parse results
        print(Fore.CYAN + ">> Parsing test reports..." + Style.RESET_ALL)
        parsed = parse_surefire_and_specmatic(
            self.repo_root / self.cfg["surefire_dir"],
            (self.repo_root / self.cfg["surefire_dir"]).parent / self.cfg.get("specmatic_log", "specmatic.log")
        )
        if self.verbose:
            print("[DEBUG] Parsed summary chars:", len(parsed))

        # 3) Gather context
        print(Fore.CYAN + ">> Collecting context..." + Style.RESET_ALL)
        code_ctx = snapshot_code(self.repo_root, [
            "src/main/java", "src/main/resources", "pom.xml",
            self.cfg.get("specmatic_config", "specmatic.yaml")
        ], self.cfg["limits"])
        spec_ctx = read_specs(self.repo_root, self.cfg["spec_keyword"], self.cfg["limits"])
        cfg_ctx  = read_if_exists(self.repo_root, self.cfg.get("specmatic_config", "specmatic.yaml"))

        if self.verbose:
            print("[DEBUG] code_ctx chars:", len(code_ctx), "| spec_ctx chars:", len(spec_ctx), "| cfg_ctx chars:", len(cfg_ctx))

        # 4) LLM: summaries & suggestions
        prompts = build_prompts(parsed, code_ctx, spec_ctx, cfg_ctx)
        prompts = self._maybe_trim_for_fast(prompts)

        print(Fore.CYAN + ">> Summarizing failures..." + Style.RESET_ALL)
        llm_summary = self._llm_call("planner_model", prompts["summary"], label="Summary")

        print(Fore.CYAN + ">> Suggesting API changes (with concrete code)..." + Style.RESET_ALL)
        api_suggestions = self._llm_call("coder_model", prompts["api"], label="API suggestions")

        print(Fore.CYAN + ">> Suggesting Spec changes..." + Style.RESET_ALL)
        spec_suggestions = self._llm_call("coder_model", prompts["spec"], label="Spec suggestions")

        print(Fore.CYAN + ">> Suggesting Specmatic config..." + Style.RESET_ALL)
        specmatic_suggestions = self._llm_call("planner_model", prompts["specmatic"], label="Specmatic suggestions")

        # 5) Optional diffs
        proposed_patches = {}
        if propose_patches:
            print(Fore.CYAN + ">> Asking for unified diffs..." + Style.RESET_ALL)
            diff_text = self._llm_call("coder_model", prompts["diffs"], label="Diffs")
            # Persist raw (so you see exactly what the model returned)
            (self.output_dir / "raw_diffs_or_snippets.txt").write_text(diff_text or "", encoding="utf-8")

            proposed_patches = extract_unified_diffs(diff_text or "")
            patches_dir = self.output_dir / "patches"
            patches_dir.mkdir(parents=True, exist_ok=True)
            count = 0
            for i, (path, diff) in enumerate(proposed_patches.items(), 1):
                with open(patches_dir / f"patch_{i:02d}.diff", "w", encoding="utf-8") as f:
                    f.write(diff)
                count += 1
            if self.verbose:
                print(f"[DEBUG] Wrote {count} patch file(s) to {patches_dir}")

            if count == 0:
                print(Fore.YELLOW + ">> No unified diffs detected. Check .agentic/raw_diffs_or_snippets.txt for code blocks or messages." + Style.RESET_ALL)

        # 6) Persist artifacts (always)
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
        # Robust split: respect quoted args if any
        # If your test command is complex, switch to shell=True with care.
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
