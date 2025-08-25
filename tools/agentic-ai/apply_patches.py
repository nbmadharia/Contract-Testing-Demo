#!/usr/bin/env python3
import argparse, subprocess, pathlib, shutil, sys

def run(cmd, cwd):
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = p.communicate()
    if p.returncode != 0:
        print(err)
    return p.returncode, out, err

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("patch_dir", help="Directory containing *.diff")
    ap.add_argument("--branch", default="agentic-patches")
    ap.add_argument("--repo", default="../../")
    args = ap.parse_args()

    repo = pathlib.Path(args.repo).resolve()
    ret, _, _ = run(["git", "rev-parse", "--is-inside-work-tree"], repo)
    if ret != 0:
        print("Not a git repo. Aborting.")
        return 1

    # create new branch
    run(["git", "checkout", "-b", args.branch], repo)

    for diff_file in sorted(pathlib.Path(args.patch_dir).glob("*.diff")):
        ret, _, err = run(["git", "apply", "--index", str(diff_file)], repo)
        if ret != 0:
            print(f"Failed to apply {diff_file.name}:\n{err}")

    run(["git", "commit", "-m", "Apply agentic patches"], repo)
    print(f"Done. Branch: {args.branch}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
