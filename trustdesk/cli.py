from __future__ import annotations

import argparse
import sys
from pathlib import Path

from trustdesk.core.database import get_db_session
from trustdesk.core.exceptions import IngestionError
from trustdesk.core.logging import configure_logging, get_logger
from trustdesk.services.ingestion import ingest_dataset
from trustdesk.services.knowledge_service import derive_and_index_sections
from trustdesk.services.retrieval.postgres_fts import PostgresFtsRetrievalAdapter

logger = get_logger(__name__)


def main() -> None:
    """CLI entrypoint for TrustDesk administrative commands."""
    configure_logging()

    parser = argparse.ArgumentParser(
        prog="python -m trustdesk.cli",
        description="TrustDesk Management & Operations CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Ingest subcommand
    ingest_parser = subparsers.add_parser("ingest", help="Ingest source dataset files into database")
    ingest_parser.add_argument(
        "--data-dir",
        type=str,
        default="./data",
        help="Path to dataset directory containing JSON source files (default: ./data)",
    )

    # Chunk policies subcommand (Phase 3)
    chunk_parser = subparsers.add_parser(
        "chunk-policies",
        help="Derive and index structured sections from knowledge base documents",
    )
    chunk_parser.add_argument(
        "--kb-id",
        type=str,
        default=None,
        help="Optional specific knowledge document ID to re-chunk (default: chunk all)",
    )

    # Search policies subcommand (Phase 3)
    search_parser = subparsers.add_parser(
        "search-policies",
        help="Search knowledge base policies using PostgreSQL full-text search",
    )
    search_parser.add_argument(
        "query",
        type=str,
        nargs="+",
        help="Search query term(s)",
    )
    search_parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of policy sections to return (default: 5)",
    )

    args = parser.parse_args()

    if args.command == "ingest":
        data_path = Path(args.data_dir)
        try:
            with get_db_session() as session:
                summary = ingest_dataset(session=session, data_dir=data_path)
            print("\nDataset ingestion completed successfully:")
            for entity, count in summary.items():
                print(f"  - {entity}: {count}")
            sys.exit(0)
        except IngestionError as exc:
            print(f"\n[INGESTION ERROR] {exc.message}", file=sys.stderr)
            sys.exit(1)
        except Exception as exc:
            print(f"\n[UNEXPECTED ERROR] {exc}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "chunk-policies":
        try:
            with get_db_session() as session:
                count = derive_and_index_sections(session=session, kb_id=args.kb_id)
                session.commit()
            target_str = f"document '{args.kb_id}'" if args.kb_id else "all documents"
            print(f"\nPolicy section chunking completed successfully for {target_str}:")
            print(f"  - Derived and indexed {count} section(s).")
            sys.exit(0)
        except Exception as exc:
            print(f"\n[CHUNKING ERROR] {exc}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "search-policies":
        queries = args.query if len(args.query) > 1 else args.query[0]
        try:
            with get_db_session() as session:
                adapter = PostgresFtsRetrievalAdapter(session)
                matches = adapter.search_policies(query=queries, limit=args.limit)

            query_str = " | ".join(args.query) if isinstance(args.query, list) else args.query
            print(f"\nPolicy search results for query: '{query_str}' (limit: {args.limit})")
            if not matches:
                print("  No matching policy sections found.")
            else:
                for idx, match in enumerate(matches, start=1):
                    print(f"\n  [{idx}] Section ID: {match.section_id} (Score: {match.relevance_score:.4f})")
                    print(f"      Document ID: {match.kb_id}")
                    print(f"      Title: {match.section_title}")
                    content_preview = match.content.replace("\n", " ")[:120]
                    print(f"      Content: {content_preview}...")
            sys.exit(0)
        except Exception as exc:
            print(f"\n[SEARCH ERROR] {exc}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
