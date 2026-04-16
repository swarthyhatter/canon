import argparse
import os
import sys

from bonfires import BonfiresClient
from dotenv import load_dotenv

from agent import ResultsIngestor, SurveyDesigner
from harmonica.client import HarmonicaClient


def _build_clients():
    load_dotenv()
    bonfire = BonfiresClient(
        api_key=os.environ["BONFIRE_API_KEY"],
        bonfire_id=os.environ["BONFIRE_ID"],
        agent_id=os.environ["BONFIRE_AGENT_ID"],
    )
    harmonica = HarmonicaClient()
    return bonfire, harmonica


def cmd_design(topic: str, bonfire: BonfiresClient, harmonica: HarmonicaClient):
    print(f"Searching KG for: {topic!r}")
    designer = SurveyDesigner(bonfire, harmonica)
    session = designer.create_session(topic)
    session_id = session.get("id") or session.get("session_id", "unknown")
    url = (
        session.get("url")
        or session.get("participant_url")
        or session.get("link", "")
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
    print(f"Entities added: {result['entities_added']}")
    print(f"Edges added:    {result['edges_added']}")
    print(f"Kengram:        {result['kengram_id']}")


def main():
    parser = argparse.ArgumentParser(
        prog="canon",
        description="Autonomous Bonfires ↔ Harmonica survey agent",
    )
    parser.add_argument(
        "--topic", metavar="QUERY",
        help="Design and create a survey from this KG topic query",
    )
    parser.add_argument(
        "--session", metavar="SESSION_ID",
        help="Session ID to poll or ingest",
    )
    parser.add_argument(
        "--ingest", metavar="KENGRAM_ID",
        help="Ingest completed session into this kengram ID",
    )
    args = parser.parse_args()

    if args.session and args.ingest:
        bonfire, harmonica = _build_clients()
        cmd_ingest(args.session, args.ingest, bonfire, harmonica)
        return

    if args.session:
        _, harmonica = _build_clients()
        cmd_poll(args.session, harmonica)
        return

    if args.topic:
        bonfire, harmonica = _build_clients()
        cmd_design(args.topic, bonfire, harmonica)
        return

    try:
        topic = input("Enter topic query: ").strip()
    except (EOFError, KeyboardInterrupt):
        sys.exit(0)

    if not topic:
        print("No topic provided.", file=sys.stderr)
        sys.exit(1)

    bonfire, harmonica = _build_clients()
    cmd_design(topic, bonfire, harmonica)


if __name__ == "__main__":
    main()
