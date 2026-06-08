import asyncio
import argparse
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.adapters.elabftw import ElabftwAdapter
from app.config import Settings, get_settings
from app.http_errors import format_exception
from app.models import ElnValidationRequest
from app.services.eln_snapshot import build_eln_snapshot, validate_eln_snapshot


async def main() -> int:
    parser = argparse.ArgumentParser(description="Verify and optionally export a real eLabFTW data snapshot.")
    parser.add_argument("--env-file", type=Path, help="Read eLabFTW settings from this .env file instead of companion/.env.")
    parser.add_argument("--json", action="store_true", help="Print the full normalized ELN snapshot as JSON.")
    parser.add_argument("--output", type=Path, help="Write the full normalized ELN snapshot to this JSON file.")
    parser.add_argument("--require-core-data", action="store_true", help="Fail unless at least one project/team and one experiment are present.")
    parser.add_argument("--min-projects", type=int, default=0, help="Minimum required projects/teams.")
    parser.add_argument("--min-experiments", type=int, default=0, help="Minimum required experiments.")
    parser.add_argument("--min-attachments", type=int, default=0, help="Minimum required attachments.")
    parser.add_argument("--min-users", type=int, default=0, help="Minimum required users.")
    parser.add_argument("--min-audit-events", type=int, default=0, help="Minimum required audit/history events.")
    parser.add_argument("--require-attachment-download", action="store_true", help="Fail unless the first attachment can be downloaded.")
    args = parser.parse_args()

    settings = Settings(_env_file=args.env_file) if args.env_file else get_settings()
    if not settings.elabftw_base_url or not settings.elabftw_api_key:
        print("ELABFTW_BASE_URL and ELABFTW_API_KEY are required.")
        return 2

    adapter = ElabftwAdapter(
        settings.elabftw_base_url,
        settings.elabftw_api_key,
        scope=settings.elabftw_scope,
        page_size=settings.elabftw_page_size,
        timeout_seconds=settings.elabftw_timeout_seconds,
    )
    try:
        snapshot = await build_eln_snapshot(
            adapter,
            adapter_mode="elabftw",
            base_url=settings.elabftw_base_url,
            scope=settings.elabftw_scope,
        )
    except httpx.HTTPStatusError as exc:
        print(f"eLabFTW API returned HTTP {exc.response.status_code} for {exc.request.method} {exc.request.url}.")
        return 1
    except httpx.HTTPError as exc:
        print(f"Could not connect to eLabFTW: {format_exception(exc)}")
        return 1

    validation = validate_eln_snapshot(
        snapshot,
        ElnValidationRequest(
            require_core_data=args.require_core_data,
            min_projects=args.min_projects,
            min_experiments=args.min_experiments,
            min_attachments=args.min_attachments,
            min_users=args.min_users,
            min_audit_events=args.min_audit_events,
        ),
    )
    if not validation.passed:
        print("eLabFTW data validation failed:")
        for failure in validation.failures:
            print(f"- {failure}")
        return 3

    downloaded_attachment_id: str | None = None
    downloaded_attachment_size: int | None = None
    if args.require_attachment_download:
        if not snapshot.attachments:
            print("eLabFTW attachment validation failed:")
            print("- no attachments available to download")
            return 4
        try:
            attachment_content = await adapter.download_attachment(snapshot.attachments[0].id)
        except (KeyError, httpx.HTTPError) as exc:
            print("eLabFTW attachment validation failed:")
            print(f"- could not download attachment {snapshot.attachments[0].id}: {format_exception(exc)}")
            return 4
        downloaded_attachment_id = attachment_content.attachment.id
        downloaded_attachment_size = len(attachment_content.content)

    snapshot_json = snapshot.model_dump_json(indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(snapshot_json, encoding="utf-8")
    if args.json:
        print(snapshot_json)
        return 0

    print(f"Connected to eLabFTW: {settings.elabftw_base_url}")
    print(f"Projects/teams: {snapshot.counts['projects']}")
    print(f"Experiments: {snapshot.counts['experiments']}")
    print(f"Attachments: {snapshot.counts['attachments']}")
    print(f"Users: {snapshot.counts['users']}")
    print(f"Audit events: {snapshot.counts['audit_events']}")
    if snapshot.projects:
        print(f"First project/team: {snapshot.projects[0].id} - {snapshot.projects[0].name}")
    if snapshot.experiments:
        print(f"First experiment: {snapshot.experiments[0].id} - {snapshot.experiments[0].title}")
    if args.output:
        print(f"Snapshot written to: {args.output}")
    if downloaded_attachment_id is not None:
        print(f"Downloaded attachment: {downloaded_attachment_id} ({downloaded_attachment_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
