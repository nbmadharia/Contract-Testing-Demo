#!/usr/bin/env python3
import argparse, json, os, sys
from agent import Agent

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--propose-patches", action="store_true",
                    help="Ask LLM to emit unified diffs")
    ap.add_argument("--config", default="config.yaml")
    args = ap.parse_args()

    agent = Agent(args.config)
    result = agent.run_once(propose_patches=args.propose_patches)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    sys.exit(main())
