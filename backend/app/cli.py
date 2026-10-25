import argparse
import getpass
import os
import sys

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .config import get_settings
from .database import SessionLocal
from .demo_data import DemoDataCollision, reset_demo_data, seed_demo_data
from .models import Manager
from .security import hash_password


def _prompt(name: str, label: str) -> str:
    value = os.getenv(name)
    if value is not None:
        return value.strip()
    return input(f"{label}: ").strip()


def create_manager() -> int:
    try:
        email = str(
            TypeAdapter(EmailStr).validate_python(_prompt("MANAGER_EMAIL", "Email"))
        ).lower()
    except ValidationError as exc:
        print(f"Invalid email: {exc}", file=sys.stderr)
        return 2
    name = _prompt("MANAGER_NAME", "Name")
    password = os.getenv("MANAGER_PASSWORD") or getpass.getpass("Password: ")
    if not name:
        print("Name must not be blank", file=sys.stderr)
        return 2
    if len(password) < 12:
        print("Password must be at least 12 characters", file=sys.stderr)
        return 2

    with SessionLocal() as db:
        if db.scalar(select(Manager).where(Manager.email == email)) is not None:
            print("A manager with that email already exists", file=sys.stderr)
            return 1
        db.add(Manager(email=email, name=name, password_hash=hash_password(password)))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            print("A manager with that email already exists", file=sys.stderr)
            return 1
    print(f"Created manager {email}")
    return 0


def seed_demo() -> int:
    settings = get_settings()
    if settings.ai_enabled or settings.notifications_enabled:
        print(
            "Demo seed refused: run with AI_ENABLED=false and NOTIFICATIONS_ENABLED=false",
            file=sys.stderr,
        )
        return 2
    try:
        with SessionLocal() as db:
            result = seed_demo_data(db)
    except DemoDataCollision as exc:
        print(f"Demo seed collision: {exc}", file=sys.stderr)
        return 3
    except SQLAlchemyError:
        print("Demo seed failed: database operation failed", file=sys.stderr)
        return 1
    print(f"Demo seed complete: created={result.created} existing={result.existing}")
    return 0


def reset_demo(confirm: bool) -> int:
    if not confirm:
        print("Demo reset refused: pass --confirm", file=sys.stderr)
        return 2
    try:
        with SessionLocal() as db:
            deleted = reset_demo_data(db)
    except DemoDataCollision as exc:
        print(f"Demo reset collision: {exc}", file=sys.stderr)
        return 3
    except SQLAlchemyError:
        print("Demo reset failed: database operation failed", file=sys.stderr)
        return 1
    print(f"Demo reset complete: deleted={deleted}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="leadflow")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("create-manager", help="Create the initial manager")
    subparsers.add_parser("seed-demo", help="Add the fixed synthetic demo leads")
    reset_parser = subparsers.add_parser(
        "reset-demo", help="Delete only owned fixed demo leads"
    )
    reset_parser.add_argument(
        "--confirm", action="store_true", help="Confirm scoped deletion of demo leads"
    )
    args = parser.parse_args()
    if args.command == "create-manager":
        raise SystemExit(create_manager())
    if args.command == "seed-demo":
        raise SystemExit(seed_demo())
    if args.command == "reset-demo":
        raise SystemExit(reset_demo(args.confirm))


if __name__ == "__main__":
    main()
