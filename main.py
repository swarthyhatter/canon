import argparse
import os
import sys

from bonfires import BonfiresClient
from dotenv import load_dotenv

from agent import ResultsIngestor, SurveyDesigner, TopicAdvisor
from harmonica.client import HarmonicaClient
import store.db as db
from store.vault import export_vault


# _build_clients loads .env so credentials stay out of source; all three Bonfires
# args are required — a missing key raises KeyError before any network call is made.
# → next: main.py:32
def _build_clients():
    load_dotenv()
    db.init()
    bonfire = BonfiresClient(
        api_key=os.environ["BONFIRE_API_KEY"],
        bonfire_id=os.environ["BONFIRE_ID"],
        agent_id=os.environ["BONFIRE_AGENT_ID"],
    )
    harmonica = HarmonicaClient()
    return bonfire, harmonica


def _print_table(rows: list[dict], columns: list[tuple]):
    """Print a simple fixed-column table. columns = [(key, header), ...]"""
    headers = [h for _, h in columns]
    widths = [
        max(len(h), max((len(str(r.get(k, ""))) for r in rows), default=0))
        for k, h in columns
    ]
    sep = "  "
    print(sep.join(h.ljust(w) for h, w in zip(headers, widths)))
    print(sep.join("-" * w for w in widths))
    for row in rows:
        print(sep.join(str(row.get(k, "")).ljust(w) for (k, _), w in zip(columns, widths)))


# cmd_discover is the first step: TopicAdvisor queries the KG and returns
# n topic suggestions stored to DB + .md files for human review.
# → next: main.py:56
def cmd_discover(
    query: str | None,
    batch: int,
    bonfire: BonfiresClient,
):
    label = f"{query!r}" if query else "full KG scan"
    print(f"Discovering topics ({label}, n={batch}) ...")
    advisor = TopicAdvisor(bonfire)
    topics = advisor.discover_batch(query=query, n=batch)
    print(f"\n{len(topics)} topic(s) stored.\n")
    _print_table(topics, [
        ("id", "ID"),
        ("topic", "Topic"),
        ("format_suggestion", "Format"),
        ("batch_run_id", "Batch"),
    ])
    vault_path = export_vault()
    print(f"\nVault updated: {vault_path}")


# cmd_design reads a stored topic by ID, generates n session design variations,
# stores each, and prompts the user to select one if batch > 1.
def cmd_design(
    topic_id: int,
    batch: int,
    bonfire: BonfiresClient,
    harmonica: HarmonicaClient,
):
    topic = db.get_topic(topic_id)
    print(f"Designing session for topic #{topic_id}: {topic['topic']!r} (n={batch}) ...")
    designer = SurveyDesigner(bonfire, harmonica)
    designs = designer.build_survey_params_from_topic(topic_id, n=batch)
    print(f"\n{len(designs)} design(s) stored.\n")
    _print_table(designs, [
        ("id", "ID"),
        ("topic", "Topic"),
        ("goal", "Goal"),
        ("batch_run_id", "Batch"),
    ])
    if batch > 1:
        _prompt_select_design(designs)
    vault_path = export_vault()
    print(f"\nVault updated: {vault_path}")


def _prompt_select_design(designs: list[dict]):
    ids = [str(d["id"]) for d in designs]
    print()
    try:
        choice = input(
            f"Select design ID to mark as preferred [{'/'.join(ids)}] (Enter to skip): "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nSkipped.")
        return
    if choice in ids:
        db.mark_selected(int(choice))
        print(f"Design #{choice} marked as selected.")


def cmd_create(
    design_id: int,
    template_id: str | None,
    bonfire: BonfiresClient,
    harmonica: HarmonicaClient,
):
    design = db.get_design(design_id)
    topic = db.get_topic(design["topic_id"])
    print(f"Creating session from design #{design_id} (topic: {topic['topic']!r}) ...")
    designer = SurveyDesigner(bonfire, harmonica)
    session = designer.create_session_from_design(design_id, template_id=template_id)
    session_id = session.get("id") or session.get("session_id", "unknown")
    url = (
        session.get("join_url") or session.get("url")
        or session.get("participant_url", "")
    )
    print(f"\nSession created: {session_id}")
    if url:
        print(f"Participant URL:  {url}")
    else:
        print("Session data:", session)


def cmd_poll(session_id: str, harmonica: HarmonicaClient):
    session = harmonica.get_session(session_id)
    status = session.get("status", "unknown")
    responses = harmonica.get_responses(session_id)
    print(f"Session:   {session_id}")
    print(f"Status:    {status}")
    print(f"Responses: {len(responses)}")


def cmd_ingest(
    session_id: str,
    kengram_id: str,
    bonfire: BonfiresClient,
    harmonica: HarmonicaClient,
):
    print(f"Ingesting session {session_id!r} into kengram {kengram_id!r} ...")
    ingestor = ResultsIngestor(bonfire, harmonica)
    result = ingestor.ingest(session_id, kengram_id)
    print(f"Entities pinned: {result['entities_pinned']}")
    print(f"Kengram:         {result['kengram_id']}")


def cmd_list_topics():
    topics = db.list_topics()
    if not topics:
        print("No topics stored yet. Run --discover first.")
        return
    _print_table(topics, [
        ("id", "ID"),
        ("created_at", "Created"),
        ("topic", "Topic"),
        ("format_suggestion", "Format"),
        ("query", "Query"),
    ])


def cmd_list_designs(topic_id: int | None):
    designs = db.list_designs(topic_id=topic_id)
    if not designs:
        print("No designs stored yet. Run --design first.")
        return
    _print_table(designs, [
        ("id", "ID"),
        ("created_at", "Created"),
        ("topic_id", "Topic ID"),
        ("template_id", "Template"),
        ("selected", "Selected"),
    ])


def main():
    parser = argparse.ArgumentParser(
        prog="canon",
        description="Autonomous Bonfires ↔ Harmonica survey agent",
    )

    # Discovery
    parser.add_argument(
        "--discover", metavar="QUERY", nargs="?", const="",
        help="Discover deliberation topics from KG (omit value for full scan)",
    )
    # Design
    parser.add_argument(
        "--design", metavar="TOPIC_ID", type=int,
        help="Generate session design(s) from a stored topic ID",
    )
    # Create
    parser.add_argument(
        "--create", metavar="DESIGN_ID", type=int,
        help="Create a Harmonica session from a stored design ID",
    )
    # Legacy single-shot
    parser.add_argument(
        "--topic", metavar="QUERY",
        help="(Legacy) Design + create a session in one step",
    )
    # Poll / ingest
    parser.add_argument(
        "--session", metavar="SESSION_ID",
        help="Harmonica session ID to poll or ingest",
    )
    parser.add_argument(
        "--ingest", metavar="KENGRAM_ID",
        help="Ingest completed session into this kengram ID",
    )
    # Shared options
    parser.add_argument(
        "--batch", metavar="N", type=int, default=1,
        help="Number of variations to generate (default: 1)",
    )
    parser.add_argument(
        "--template-id", metavar="ID",
        help="Harmonica template ID (used with --create)",
    )
    # List / export commands
    parser.add_argument("--list-topics", action="store_true")
    parser.add_argument(
        "--list-designs", metavar="TOPIC_ID", nargs="?", const=0, type=int,
    )
    parser.add_argument(
        "--export-vault", action="store_true",
        help="Regenerate Obsidian vault from DB",
    )

    args = parser.parse_args()

    # Read-only commands — no clients needed
    if args.export_vault:
        db.init()
        path = export_vault()
        print(f"Vault exported to: {path}")
        return
    if args.list_topics:
        db.init()
        cmd_list_topics()
        return
    if args.list_designs is not None:
        db.init()
        topic_id = args.list_designs if args.list_designs else None
        cmd_list_designs(topic_id)
        return

    bonfire, harmonica = _build_clients()

    if args.session and args.ingest:
        cmd_ingest(args.session, args.ingest, bonfire, harmonica)
        return

    if args.session:
        cmd_poll(args.session, harmonica)
        return

    if args.discover is not None:
        query = args.discover if args.discover else None
        cmd_discover(query, args.batch, bonfire)
        return

    if args.design is not None:
        cmd_design(args.design, args.batch, bonfire, harmonica)
        return

    if args.create is not None:
        cmd_create(args.create, args.template_id, bonfire, harmonica)
        return

    if args.topic:
        # Legacy single-shot path
        print(f"Searching KG for: {args.topic!r}")
        designer = SurveyDesigner(bonfire, harmonica)
        session = designer.create_session(args.topic)
        session_id = session.get("id") or session.get("session_id", "unknown")
        url = (
            session.get("join_url") or session.get("url")
            or session.get("participant_url", "")
        )
        print(f"\nSession created: {session_id}")
        if url:
            print(f"Participant URL:  {url}")
        else:
            print("Session data:", session)
        return

    # Interactive fallback
    try:
        topic = input("Enter topic query: ").strip()
    except (EOFError, KeyboardInterrupt):
        sys.exit(0)
    if not topic:
        print("No topic provided.", file=sys.stderr)
        sys.exit(1)
    designer = SurveyDesigner(bonfire, harmonica)
    session = designer.create_session(topic)
    session_id = session.get("id") or session.get("session_id", "unknown")
    url = (
        session.get("join_url") or session.get("url")
        or session.get("participant_url", "")
    )
    print(f"\nSession created: {session_id}")
    if url:
        print(f"Participant URL:  {url}")


if __name__ == "__main__":
    main()
