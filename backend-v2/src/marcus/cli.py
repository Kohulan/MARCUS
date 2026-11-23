"""Admin CLI (`marcus ...`), run inside the api container:

    docker compose -p marcus-v2 exec api marcus apikey create --label "my lab"
    marcus apikey list [--json] | marcus apikey revoke ID
    marcus purge --paper ID | marcus purge --expired

Exit codes: 0 ok, 1 not found or invalid input, 2 usage error. A new key is printed once on
stdout; only its SHA-256 is stored, so it cannot be shown again, and `list` never shows it.
"""

import argparse
import json
import sys
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from marcus.core.enums import OwnerKind, PriorityClass
from marcus.core.models import Owner, Paper
from marcus.core.quota import pages_used_stmt
from marcus.core.tokens import hash_token, new_token

KEY_PREFIX = "mk_"
MAX_LABEL = 100
DEFAULT_DAILY_PAGES = 2000


class CliError(Exception):
    """Not found / invalid input: printed to stderr, exit code 1."""


def _uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise CliError(f"invalid {what} id: {value!r}") from None


def _api_key_owner(session: Session, value: str) -> Owner:
    owner = session.execute(
        select(Owner).where(Owner.id == _uuid(value, "key"), Owner.kind == OwnerKind.API_KEY.value)
    ).scalar_one_or_none()
    if owner is None:
        raise CliError(f"no API key with id {value}")
    return owner


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat(timespec="seconds") if value else None


def cmd_apikey_create(session: Session, args: argparse.Namespace) -> int:
    label = args.label.strip()
    if not label or len(label) > MAX_LABEL:
        raise CliError(f"--label must be 1 to {MAX_LABEL} characters")
    if args.daily_pages < 1:
        raise CliError("--daily-pages must be at least 1")
    key = KEY_PREFIX + new_token()
    owner = Owner(
        kind=OwnerKind.API_KEY.value,
        token_hash=hash_token(key),
        priority_class=int(PriorityClass.API),
        daily_page_quota=args.daily_pages,
        label=label,
    )
    session.add(owner)
    session.commit()
    print(f"id: {owner.id}")
    print(f"label: {label}")
    print(f"daily pages: {args.daily_pages}")
    print(f"key: {key}")
    print("Store this key now: it is shown only once.", file=sys.stderr)
    return 0


def cmd_apikey_revoke(session: Session, args: argparse.Namespace) -> int:
    owner = _api_key_owner(session, args.id)
    if owner.revoked_at is None:
        owner.revoked_at = datetime.now(UTC)
        session.commit()
        print(f"revoked {owner.id}")
    else:
        print(f"{owner.id} was already revoked at {_iso(owner.revoked_at)}")
    return 0


def cmd_apikey_list(session: Session, args: argparse.Namespace) -> int:
    owners = session.execute(
        select(Owner).where(Owner.kind == OwnerKind.API_KEY.value).order_by(Owner.created_at)
    ).scalars()
    rows = []
    for o in owners:
        used, reserved = session.execute(pages_used_stmt(o.id)).one()
        rows.append(
            {
                "id": str(o.id),
                "label": o.label,
                "created_at": _iso(o.created_at),
                "revoked_at": _iso(o.revoked_at),
                "daily_page_quota": o.daily_page_quota,
                "pages_today": used,
                "pages_reserved": reserved,  # held by papers still being checked
            }
        )
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    if not rows:
        print("no API keys")
    for r in rows:
        state = f"revoked {r['revoked_at']}" if r["revoked_at"] else "active"
        print(
            f"{r['id']}  {r['label']!r}  created {r['created_at']}  {state}  "
            f"pages today {r['pages_today']} (+{r['pages_reserved']} reserved)"
            f"/{r['daily_page_quota']}"
        )
    return 0


def cmd_purge(session: Session, args: argparse.Namespace) -> int:
    # Imported here: the retention module pulls in the celery app, which `apikey` never needs.
    from marcus.core import storage
    from marcus.core.pipeline import cancel_paper
    from marcus.workers import retention

    if args.expired:
        report = retention.purge_expired(session, datetime.now(UTC))
        for name, value in vars(report).items():
            print(f"{name}: {value}")
        return 1 if report.errors else 0

    paper_id = _uuid(args.paper, "paper")
    try:
        cancel_paper(session, paper_id)  # cancels active steps, marks deleted, removes files
    except ValueError:
        session.rollback()
        raise CliError(f"no paper with id {paper_id}") from None
    session.execute(
        delete(Paper).where(Paper.id == paper_id).execution_options(synchronize_session=False)
    )
    session.commit()
    # Anything cancel_paper could not remove inside the transaction goes after the commit,
    # as retention does.
    retention._remove(storage.paper_dir(paper_id), retention.PurgeReport())
    print(f"purged paper {paper_id}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="marcus", description="MARCUS v2 admin")
    sub = parser.add_subparsers(dest="group", required=True)

    apikey = sub.add_parser("apikey", help="manage API keys").add_subparsers(
        dest="action", required=True
    )
    create = apikey.add_parser("create", help="create a key (printed once)")
    create.add_argument("--label", required=True, help=f"who the key is for (max {MAX_LABEL})")
    create.add_argument("--daily-pages", type=int, default=DEFAULT_DAILY_PAGES)
    create.set_defaults(func=cmd_apikey_create)
    revoke = apikey.add_parser("revoke", help="revoke a key by id (idempotent)")
    revoke.add_argument("id")
    revoke.set_defaults(func=cmd_apikey_revoke)
    lst = apikey.add_parser("list", help="list keys (never their secrets)")
    lst.add_argument("--json", action="store_true")
    lst.set_defaults(func=cmd_apikey_list)

    purge = sub.add_parser("purge", help="delete a paper now, or run the retention purge once")
    target = purge.add_mutually_exclusive_group(required=True)
    target.add_argument("--paper", metavar="ID")
    target.add_argument("--expired", action="store_true")
    purge.set_defaults(func=cmd_purge)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse: 2 on a usage error, 0 for --help
        return int(exc.code or 0)
    from marcus.core.db import sync_session

    with sync_session() as session:
        try:
            return args.func(session, args)
        except CliError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    sys.exit(main())
