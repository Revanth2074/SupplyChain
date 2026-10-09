"""
Response Playbook (SOP) Routes.
Lists and serves the disruption-response playbooks in knowledge_base/sops (the same documents
ingested into Synapt's Procedure Store and returned by trident_get_procedures).
"""

import os

from fastapi import APIRouter, HTTPException

from config import get_sops_dir

router = APIRouter(tags=["Response Playbooks"])


@router.get("/sops")
def list_sops():
    """Returns all available disruption-response playbooks."""
    sops_dir = get_sops_dir()
    sops = []
    if os.path.exists(sops_dir):
        for fname in sorted(os.listdir(sops_dir)):
            if fname.endswith(".md"):
                with open(os.path.join(sops_dir, fname), "r", encoding="utf-8") as f:
                    lines = [line.strip() for line in f.readlines() if line.strip()]
                title = lines[0].replace("#", "").strip() if lines else fname
                sop_id = "_".join(fname.split("_")[:2]) if "_" in fname else fname
                sops.append({"filename": fname, "title": title, "sop_id": sop_id})
    return {"sops": sops}


@router.get("/sops/{sop_filename}")
def get_sop_content(sop_filename: str):
    """Fetches the full content of a playbook (by filename or SOP id prefix, e.g. SOP_003)."""
    sops_dir = get_sops_dir()
    name = os.path.basename(sop_filename)
    fpath = os.path.join(sops_dir, name)
    if not os.path.isfile(fpath):
        found = next((f for f in sorted(os.listdir(sops_dir)) if f.startswith(name)), None) \
            if os.path.exists(sops_dir) else None
        if not found:
            raise HTTPException(status_code=404, detail="SOP playbook not found.")
        fpath = os.path.join(sops_dir, found)
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()
    return {"filename": os.path.basename(fpath), "content": content}
