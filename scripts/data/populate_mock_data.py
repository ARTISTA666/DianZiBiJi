"""Create safe demo domain data without fabricating AI results.

The historical script generated synthetic RAG answers, evaluations and agent
runs. Those records are not valid evidence for the thesis, so this entry point
now delegates only to the normal application seed process.
"""

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.database import SessionLocal  # noqa: E402
from app.services.seed import ensure_seed_data  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        ensure_seed_data(db)
        print("Demo notes and documents are ready.")
        print("No AI answers, evaluations or agent runs were generated.")
        print("Run real paired experiments from the project's RAG workspace.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
