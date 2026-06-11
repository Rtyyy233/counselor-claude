#!/usr/bin/env python3
"""
counselor-claude database bridge.

Single CLI for Chroma retrieval, profile/plan reading, and PAIP storage.
No LangChain Agents, no LangGraph planners — just direct Chroma access.

Usage:
  python tools/db.py search --source diary|conv|material|all --query "..." [--k 10]
  python tools/db.py profile-view [--user default] [--domain 1,4,5]
  python tools/db.py plan-view [--user default]
  python tools/db.py store-paip --text "..." [--user default] [--session-id ...]
  python tools/db.py store-diary --file PATH
  python tools/db.py store-material --file PATH
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# ---- Path setup — point to old project's src for Chroma collections ----
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OLD_PROJECT_SRC = PROJECT_ROOT.parent / "Counselor-Agent-main" / "src"
sys.path.insert(0, str(OLD_PROJECT_SRC))

# ---- Config ----


def _data_dir() -> Path:
    from config import DATA_DIR
    return DATA_DIR


def _profile_dir() -> Path:
    return _data_dir() / "profiles"


def _plan_dir() -> Path:
    return _data_dir() / "treatment_plans"


# ---- Chroma collections (imported once) ----

def _get_collections():
    from mem_integration import (
        original_diary, diary_annotation,
        material_store, parent_store,
        conv_store, profile_store,
    )
    return {
        "original_diary": original_diary,
        "diary_annotation": diary_annotation,
        "material_store": material_store,
        "parent_store": parent_store,
        "conv_store": conv_store,
        "profile_store": profile_store,
    }


# ---- Search: Diary ----

async def search_diary(query: str, k: int = 20) -> str:
    """Semantic search original_diary, return top results."""
    cols = _get_collections()
    store = cols["original_diary"]

    raw = await asyncio.get_running_loop().run_in_executor(
        None, lambda: store.similarity_search_with_score(query, k=k)
    )

    if not raw:
        return ""

    lines = []
    for doc, score in raw[:8]:
        content = doc.page_content[:400]
        meta = doc.metadata or {}
        date = meta.get("date", "")
        tag = f"[{date}]" if date else ""
        if content.strip():
            lines.append(f"{tag} {content}")
    return "\n---\n".join(lines) if lines else ""


# ---- Search: Conversation outlines (with PAIP recombination) ----

async def search_conv_outline(query: str, k: int = 10) -> str:
    """Search conv_store, then fetch full PAIP for matched base_ids."""
    cols = _get_collections()
    store = cols["conv_store"]

    raw = await asyncio.get_running_loop().run_in_executor(
        None, lambda: store.similarity_search_with_score(query, k=k)
    )

    if not raw:
        return ""

    # Collect unique base_ids
    base_ids = []
    seen = set()
    for doc, _score in raw:
        bid = doc.metadata.get("base_id", "") if doc.metadata else ""
        if bid and bid not in seen:
            seen.add(bid)
            base_ids.append(bid)

    # Fetch full PAIP for each base_id
    parts = []
    for bid in base_ids[:5]:
        try:
            raw_paip = await asyncio.get_running_loop().run_in_executor(
                None, lambda bid=bid: store.get(where={"base_id": bid})
            )
        except Exception:
            continue

        docs = raw_paip.get("documents") or []
        metas = raw_paip.get("metadatas") or []
        if not docs:
            continue

        # Sort PAIP sections: problem → assessment → intervention → plan
        section_order = {"problem": 0, "assessment": 1, "intervention": 2, "plan": 3}
        paired = sorted(
            zip(metas, docs),
            key=lambda x: section_order.get((x[0] or {}).get("section", ""), 99),
        )

        date = (metas[0] or {}).get("date", "") if metas else ""
        section_texts = []
        for meta, text in paired:
            sec = (meta or {}).get("section", "")
            section_texts.append(f"[{sec}] {text[:500]}")
        parts.append(f"=== {bid} [{date}] ===\n" + "\n".join(section_texts))

    return "\n\n".join(parts) if parts else ""


# ---- Search: Materials (with parent expansion) ----

async def search_materials(query: str, k: int = 10) -> str:
    """Search material_store, then fetch parent chunks for matched children."""
    cols = _get_collections()
    child_store = cols["material_store"]
    parent_st = cols["parent_store"]

    raw = await asyncio.get_running_loop().run_in_executor(
        None, lambda: child_store.similarity_search_with_score(query, k=k)
    )

    if not raw:
        return ""

    lines = []
    seen_parents = set()
    for doc, score in raw[:5]:
        content = doc.page_content[:300]
        parent_id = (doc.metadata or {}).get("parent_id", "")
        parent_text = ""
        if parent_id and parent_id not in seen_parents:
            seen_parents.add(parent_id)
            try:
                p = await asyncio.get_running_loop().run_in_executor(
                    None, lambda pid=parent_id: parent_st.get(ids=[pid])
                )
                p_docs = p.get("documents") or []
                if p_docs:
                    parent_text = p_docs[0][:400]
            except Exception:
                pass
        lines.append(f"子块: {content}")
        if parent_text:
            lines.append(f"原文: {parent_text}")
    return "\n---\n".join(lines) if lines else ""


# ---- Profile view ----

async def profile_view(user_id: str = "default", domain_numbers: list[int] | None = None) -> str:
    """Read user profile (file-first, Chroma fallback)."""
    from mem_retrieve_user_profile import retrieve_user_profile

    result = await retrieve_user_profile(user_id, domain_numbers)
    if result is None:
        return "(No profile found)"

    if domain_numbers and len(domain_numbers) == 1 and result.domains:
        d = result.domains[0]
        return f"Domain {d.domain_number} — {d.domain_name}\n\n{d.details_text[:3000]}"

    lines = []
    for d in result.domains:
        lines.append(f"#{d.domain_number} {d.domain_name}: {d.summary[:120]}")
    return "\n".join(lines) if lines else result.full_text[:5000]


# ---- Plan view ----

def plan_view(user_id: str = "default") -> str:
    """Read treatment plan JSON."""
    path = _plan_dir() / user_id / "plan.json"
    if not path.exists():
        return "(No treatment plan found)"

    data = json.loads(path.read_text(encoding="utf-8"))
    stage = data.get("stage", "?")
    stage_labels = {
        "engagement": "建立期", "cognitive_behavioral": "工作期-认知行为",
        "emotional_deepening": "工作期-情感深化", "consolidation": "整合/收尾期",
    }
    lines = [
        f"Stage: {stage_labels.get(stage, stage)}",
        f"Primary: {data.get('primary_approach', '?')}",
    ]
    sec = data.get("secondary_approaches", [])
    if sec:
        lines.append(f"Secondary: {', '.join(sec)}")
    cau = data.get("cautionary_approaches", [])
    if cau:
        lines.append(f"Caution: {', '.join(cau)}")

    if data.get("last_session_plan"):
        lines.append(f"\nLast plan: {data['last_session_plan'][:300]}")
    if data.get("pending_items"):
        lines.append(f"Pending: {', '.join(data['pending_items'][:5])}")

    goals = data.get("goals", [])
    if goals:
        lines.append("\nGoals:")
        for g in goals:
            icon = {"green": "O", "yellow": "~", "red": "!", "white": "+"}.get(g.get("progress_status", ""), "?")
            lines.append(f"  [{icon}] [{g.get('priority',1)}] {g.get('description','')[:100]} ({g.get('progress',0):.0%})")

    sup_notes = data.get("supervisor_notes", "")
    if sup_notes:
        lines.append(f"\nSupervisor notes: {sup_notes[:300]}")

    return "\n".join(lines)


# ---- PAIP storage ----

async def store_paip(text: str, user_id: str = "default", session_id: str = "") -> str:
    """Store a PAIP summary to conv_store. Uses the old project's store module if available."""
    # Try the old project's full storage pipeline
    try:
        from langchain_core.documents import Document
        from mem_store_conv_outline import store_conversation_outline

        doc = Document(
            page_content=text,
            metadata={
                "source": f"session_{session_id or 'cli'}",
                "user_id": user_id,
                "date": __import__("datetime").datetime.now().strftime("%y.%m.%d"),
            }
        )
        storage_id = await store_conversation_outline(doc)
        return f"PAIP stored: {storage_id}"
    except Exception as e:
        return f"PAIP storage failed: {e}"


# ---- Diary storage ----

async def store_diary(file_path: str) -> str:
    """Store a diary file."""
    try:
        from mem_store_diary import store_diary
        path = Path(file_path)
        if not path.exists():
            return f"File not found: {file_path}"
        result = await store_diary(str(path.resolve()))
        return f"Diary stored: {result}"
    except Exception as e:
        return f"Diary storage failed: {e}"


# ---- Material storage ----

async def store_material(file_path: str) -> str:
    """Store a material file."""
    try:
        from mem_store_material import store_material
        path = Path(file_path)
        if not path.exists():
            return f"File not found: {file_path}"
        result = await store_material(str(path.resolve()))
        return f"Material stored: {result}"
    except Exception as e:
        return f"Material storage failed: {e}"


# ---- CLI dispatch ----

async def main():
    parser = argparse.ArgumentParser(description="counselor-claude database bridge")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # search
    p_search = sub.add_parser("search")
    p_search.add_argument("--source", choices=["diary", "conv", "material", "all"], required=True)
    p_search.add_argument("--query", required=True)
    p_search.add_argument("--k", type=int, default=10)

    # profile-view
    p_prof = sub.add_parser("profile-view")
    p_prof.add_argument("--user", default="default")
    p_prof.add_argument("--domain")

    # plan-view
    p_plan = sub.add_parser("plan-view")
    p_plan.add_argument("--user", default="default")

    # store-paip
    p_paip = sub.add_parser("store-paip")
    p_paip.add_argument("--text", required=True)
    p_paip.add_argument("--user", default="default")
    p_paip.add_argument("--session-id", default="")

    # store-diary
    p_diary = sub.add_parser("store-diary")
    p_diary.add_argument("--file", required=True)

    # store-material
    p_mat = sub.add_parser("store-material")
    p_mat.add_argument("--file", required=True)

    args = parser.parse_args()

    if args.cmd == "search":
        if args.source == "all":
            diary, conv, mat = await asyncio.gather(
                search_diary(args.query, args.k),
                search_conv_outline(args.query, args.k),
                search_materials(args.query, args.k),
            )
            for label, text in [("DIARY", diary), ("CONV", conv), ("MATERIAL", mat)]:
                if text:
                    print(f"=== {label} ===\n{text}\n")
        elif args.source == "diary":
            result = await search_diary(args.query, args.k)
            if result:
                print(result)
        elif args.source == "conv":
            result = await search_conv_outline(args.query, args.k)
            if result:
                print(result)
        elif args.source == "material":
            result = await search_materials(args.query, args.k)
            if result:
                print(result)

    elif args.cmd == "profile-view":
        domains = None
        if args.domain:
            domains = [int(x.strip()) for x in args.domain.split(",") if x.strip().isdigit()]
        print(await profile_view(args.user, domains))

    elif args.cmd == "plan-view":
        print(plan_view(args.user))

    elif args.cmd == "store-paip":
        print(await store_paip(args.text, args.user, args.session_id))

    elif args.cmd == "store-diary":
        print(await store_diary(args.file))

    elif args.cmd == "store-material":
        print(await store_material(args.file))


if __name__ == "__main__":
    asyncio.run(main())
