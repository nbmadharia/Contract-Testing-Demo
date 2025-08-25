import os, subprocess, json, pathlib, shutil
from colorama import Fore, Style
from parser import parse_surefire_and_specmatic
from repo_utils import snapshot_code, read_specs, read_if_exists, ensure_outdir
from llm_client import OllamaClient
from prompts import build_prompts
from diff_utils import extract_unified_diffs
import yaml

class Agent:
    def __init__(self, config_path: str, verbose: bool = False):
        with open(config_path, "r") as f:
            self.cfg = yaml.safe_load(f)
        self.repo_root = pathlib.Path(self.cfg["repo_root"]).resolve()
        self.output_dir = ensure_outdir(self.repo_root / self.cfg.get("output_dir", ".agentic"))
        self.client = OllamaClient(self.cfg["ollama"])
        self.verbose = verbose

    def run_once(self, propose_patches: bool = False):
        # 1) Run tests
        print(Fore.CYAN + ">> Running contract tests..." + Style.RESET_ALL)
        test_out = self._run_tests()

        # 2) Parse results
        print(Fore.CYAN + ">> Parsing test reports..." + Style.RESET_ALL)
        parsed = parse_surefire_and_specmatic(
            self.repo_root / self.cfg["surefire_dir"],
            (self.repo_root / self.cfg["surefire_dir"]).parent / self.cfg.get("specmatic_log", "specmatic.log")
        )

        # 3) Gather context
        print(Fore.CYAN + ">> Collecting context..." + Style.RESET_ALL)
        code_ctx = snapshot_code(self.repo_root, [
            "src/main/java", "src/main/resources", "pom.xml",
            self.cfg.get("specmatic_config", "specmatic.yaml")
        ], self.cfg["limits"])
        spec_ctx = read_specs(self.repo_root, self.cfg["spec_keyword"], self.cfg["limits"])
        cfg_ctx  = read_if_exists(self.repo_root, self.cfg.get("specmatic_config", "specmatic.yaml"))

        # 4) LLM: summaries & suggestions
        prompts = build_prompts(parsed, code_ctx, spec_ctx, cfg_ctx)
        print(Fore.CYAN + ">> Summarizing failures..." + Style.RESET_ALL)

        if self.verbose: print("[DEBUG] Summarizing failures prompt size 1:", len(prompts["summary"]))

        llm_summary = self.client.complete("planner_model", prompts["summary"])
        print(Fore.CYAN + ">> Suggesting API changes..." + Style.RESET_ALL)

        if self.verbose: print("[DEBUG] API prompt size: 2", len(prompts["api"]))
        api_suggestions = self.client.complete("coder_model", prompts["api"])
        print(Fore.CYAN + ">> Suggesting Spec changes..." + Style.RESET_ALL)

        if self.verbose:
            print("[DEBUG] Summarizing failures prompt size 3:", len(prompts["summary"]))

        spec_suggestions = self.client.complete("coder_model", prompts["spec"])
        print(Fore.CYAN + ">> Suggesting Specmatic config..." + Style.RESET_ALL)

        if self.verbose:
            print("[DEBUG] Summarizing failures prompt size 4:", len(prompts["summary"]))

        specmatic_suggestions = self.client.complete("planner_model", prompts["specmatic"])

        # 5) Optional diffs
        proposed_patches = {}
        if propose_patches:
            print(Fore.CYAN + ">> Asking for unified diffs..." + Style.RESET_ALL)

            if self.verbose:
                print("[DEBUG] Summarizing failures prompt size 5:", len(prompts["summary"]))

            diff_text = self.client.complete("coder_model", prompts["diffs"])
            proposed_patches = extract_unified_diffs(diff_text)
            patches_dir = self.output_dir / "patches"
            patches_dir.mkdir(parents=True, exist_ok=True)
            for i, (path, diff) in enumerate(proposed_patches.items(), 1):
                with open(patches_dir / f"patch_{i:02d}.diff", "w") as f:
                    f.write(diff)

        # 6) Persist artifacts
        (self.output_dir / "summary.txt").write_text(llm_summary, encoding="utf-8")
        (self.output_dir / "api_suggestions.txt").write_text(api_suggestions, encoding="utf-8")
        (self.output_dir / "spec_suggestions.txt").write_text(spec_suggestions, encoding="utf-8")
        (self.output_dir / "specmatic_suggestions.txt").write_text(specmatic_suggestions, encoding="utf-8")
        (self.output_dir / "parsed.txt").write_text(parsed, encoding="utf-8")
        (self.output_dir / "test_stdout.txt").write_text(test_out["stdout"], encoding="utf-8")
        (self.output_dir / "test_stderr.txt").write_text(test_out["stderr"], encoding="utf-8")

        return {
            "testsPassed": test_out["exit"] == 0,
            "parseSummary": parsed,
            "llmSummary": llm_summary,
            "apiSuggestions": api_suggestions,
            "specSuggestions": spec_suggestions,
            "specmaticSuggestions": specmatic_suggestions,
            "proposedPatchCount": len(proposed_patches),
            "patchesDir": str(self.output_dir / "patches") if propose_patches else None
        }

    def _run_tests(self):
        cmd = self.cfg["test_command"]
        proc = subprocess.Popen(
            cmd.split(),
            cwd=self.repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        out, err = proc.communicate()
        return {"exit": proc.returncode, "stdout": out, "stderr": err}
