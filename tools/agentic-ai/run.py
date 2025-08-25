#!/usr/bin/env python3
import argparse, json, sys
from agent import Agent

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--propose-patches", action="store_true")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--verbose", action="store_true",
                    help="Print extra debug info")
    args = ap.parse_args()

    agent = Agent(args.config, verbose=args.verbose)
    result = agent.run_once(propose_patches=args.propose_patches)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    sys.exit(main())
