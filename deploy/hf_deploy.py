"""Deploy to a free Hugging Face Space (Docker).

Usage (from the repo root, with the backend venv):
    pip install huggingface_hub
    python deploy/hf_deploy.py <hf-username>/<space-name> [--private]

You need a Hugging Face account and a *write* access token (huggingface.co/settings/tokens).
The token is read from $HF_TOKEN or asked for interactively; it is never written to disk.

What it does:
  1. creates the Space (Docker SDK) if it does not exist,
  2. uploads only what the Docker build needs (no .env, no venv, no local database),
  3. sets the Synapt / LLM settings from backend/.env as Space *secrets* (not files),
  4. sets APP_PASSWORD, the password people type to open the app.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

try:
    from huggingface_hub import HfApi
except ImportError:
    sys.exit("Install the client first:  pip install huggingface_hub")

ROOT = Path(__file__).resolve().parent.parent
SECRET_KEYS = ["SYNAPT_MCP_URL", "SYNAPT_AUTH_BASE", "SYNAPT_USERNAME", "SYNAPT_PASSWORD", "SYNAPT_PROVIDER_ID",
               "SYNAPT_TOP_K", "SYNAPT_GRAPH_HOPS", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "JUDGE_MODEL"]
UPLOAD = ["Dockerfile", ".dockerignore", "supply_chain_disruption_recovery.csv", "backend/**", "frontend/**"]
SKIP = ["**/.env", "**/.env.*", "backend/.venv/**", "**/__pycache__/**", "backend/artifacts/*.db",
        "backend/artifacts/*.joblib", "backend/artifacts/eval_results.json", "**/.deepeval/**",
        "frontend/node_modules/**", "frontend/dist/**"]


def read_env(path: Path) -> dict:
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("space", help="<hf-username>/<space-name>")
    ap.add_argument("--private", action="store_true", help="only you (signed in to Hugging Face) can open it")
    args = ap.parse_args()

    token = os.getenv("HF_TOKEN") or getpass.getpass("Hugging Face write token: ")
    api = HfApi(token=token)
    print(f"Signed in as {api.whoami()['name']}")

    env = read_env(ROOT / "backend" / ".env")
    missing = [k for k in ("SYNAPT_USERNAME", "SYNAPT_PASSWORD", "SYNAPT_PROVIDER_ID", "LLM_API_KEY") if not env.get(k)]
    if missing:
        sys.exit(f"backend/.env is missing {missing}; fill it in first.")
    app_pw = os.getenv("APP_PASSWORD") or getpass.getpass("Choose the app access password (people will type this): ")
    if len(app_pw) < 8:
        sys.exit("Use an access password of at least 8 characters.")

    print(f"\nAbout to deploy to https://huggingface.co/spaces/{args.space} "
          f"({'private' if args.private else 'public page, app behind your password'}).")
    print("Secrets that will be stored in the Space settings:", ", ".join(k for k in SECRET_KEYS if env.get(k)) + ", APP_PASSWORD")
    if input("Continue? [y/N] ").strip().lower() != "y":
        sys.exit("Cancelled.")

    api.create_repo(args.space, repo_type="space", space_sdk="docker", private=args.private, exist_ok=True)
    for k in SECRET_KEYS:
        if env.get(k):
            api.add_space_secret(args.space, k, env[k])
    api.add_space_secret(args.space, "APP_PASSWORD", app_pw)
    print("Secrets set.")

    api.upload_folder(repo_id=args.space, repo_type="space", folder_path=str(ROOT),
                      allow_patterns=UPLOAD, ignore_patterns=SKIP, commit_message="Deploy disruption assistant")
    api.upload_file(repo_id=args.space, repo_type="space", path_or_fileobj=str(ROOT / "deploy" / "SPACE_README.md"),
                    path_in_repo="README.md", commit_message="Space card")
    sub = args.space.replace("/", "-").replace("_", "-").lower()
    print(f"\nUploaded. The Space is now building (about 8-12 minutes the first time).")
    print(f"  Build logs : https://huggingface.co/spaces/{args.space}?logs=build")
    print(f"  App        : https://{sub}.hf.space   (open this direct link; sign in with your access password)")


if __name__ == "__main__":
    main()
