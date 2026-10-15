
"""Sprint 11A.2: controlled role-permission migration.

From the project root:

    python scripts/enforce_remaining_rbac.py
    python scripts/enforce_remaining_rbac.py --apply

The first command checks changes without writing files.
The second creates backups and updates the seven services.
"""

import argparse
import ast
import shutil
from pathlib import Path


# ==========================================================
# PERMISSIONS FOR EACH PUBLIC SERVICE FUNCTION
# ==========================================================

RULES = {
    "admin_tenancy_service.py": {
        "get_active_tenancies": "leases.read",
        "get_archive_candidates": "tenants.read",
        "terminate_lease_and_move_out": "leases.terminate",
        "archive_resident": "tenants.archive",
        "get_tenancy_history": "history.read",
    },

    "admin_lease_renewal_service.py": {
        "get_renewable_leases": "leases.read",
        "renew_lease": "leases.renew",
        "get_lease_renewal_history": "history.read",
    },

    "admin_apartment_transfer_service.py": {
        "get_transfer_candidates": "leases.read",
        "get_transfer_destinations": "apartments.read",
        "transfer_resident": "transfers.execute",
        "get_apartment_transfer_history": "history.read",
    },

    "admin_moveout_inspection_service.py": {
        # Tenant assignment forms need these blocked unit IDs.
        "get_blocked_apartment_ids": "apartments.read",
        "get_open_inspections": "inspections.read",
        "record_inspection": "inspections.record",
        "approve_inspection": "inspections.approve",
        "get_inspection_history": "inspections.read",
    },

    "admin_deposit_settlement_service.py": {
        "get_eligible_deposit_leases": "deposits.read",
        "create_deposit_settlement": "deposits.edit",
        "add_deposit_deduction": "deposits.edit",
        "remove_deposit_deduction": "deposits.edit",
        "approve_deposit_settlement": "deposits.approve",
        "record_external_refund": "refunds.record",
        "close_zero_refund_settlement": "deposits.approve",
        "get_deposit_settlements": "deposits.read",
    },

    "admin_operations_service.py": {
        "get_admin_payments": "payments.read",
        "get_admin_maintenance": "maintenance.read",
        "get_maintenance_history": "maintenance.read",
        "update_maintenance_request": "maintenance.update",
    },

    "admin_content_service.py": {
        "get_admin_announcements": "announcements.read",
        "create_admin_announcement": "announcements.manage",
        "update_admin_announcement": "announcements.manage",
        "get_admin_community_news": "news.read",
        "create_admin_community_news": "news.manage",
        "update_admin_community_news": "news.manage",
    },
}


# ==========================================================
# UNIFY INDEPENDENT ADMIN CHECKS
# ==========================================================

SHARED_CHECK = '''def _require_admin(
    db,
    admin_user_id: int,
    permission: str,
) -> None:
    """Use the central database-backed role check."""
    from services.admin_management_service import (
        _require_admin as shared_admin_check,
    )
    shared_admin_check(
        db,
        admin_user_id,
        permission=permission,
    )'''


# ==========================================================
# SOURCE POSITIONS
# ==========================================================

def _offsets(source: str):
    lines = source.splitlines(keepends=True)

    starts = [0]

    for line in lines:
        starts.append(
            starts[-1] + len(line)
        )

    return starts


def _span(node, starts):
    return (
        starts[node.lineno - 1] + node.col_offset,
        starts[node.end_lineno - 1] + node.end_col_offset,
    )


# ==========================================================
# REWRITE ONE VERIFIED SERVICE FILE
# ==========================================================

def _rewrite(source: str, filename: str):

    tree = ast.parse(
        source,
        filename=filename,
    )

    starts = _offsets(source)

    replacements = []
    found = set()

    for fn in tree.body:

        if not isinstance(
            fn,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            continue

        if fn.name not in RULES[filename]:
            continue

        # Locate the exact authorization call
        # belonging to this public function.

        calls = [
            node
            for node in ast.walk(fn)
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_require_admin"
            )
        ]

        if len(calls) != 1:
            raise RuntimeError(
                f"{filename}: {fn.name} requires exactly "
                f"one authorization call. "
                f"Found {len(calls)}. No changes made."
            )

        call = calls[0]

        if any(
            keyword.arg == "permission"
            for keyword in call.keywords
        ):
            raise RuntimeError(
                f"{filename}: {fn.name} is already patched."
            )

        start, end = _span(
            call,
            starts,
        )

        original = source[start:end]

        permission = RULES[
            filename
        ][fn.name]

        # --------------------------------------
        # MULTILINE CALLS
        # --------------------------------------

        if "\n" in original:

            linebreak = original.rfind(
                "\n"
            )

            last = original[
                linebreak + 1:
            ]

            if last.strip() != ")":
                raise RuntimeError(
                    f"Unexpected authorization format "
                    f"in {filename}: {fn.name}"
                )

            close_indent = last[
                :last.index(")")
            ]

            updated = (
                original[:linebreak + 1]
                + close_indent
                + '    permission="'
                + permission
                + '",\n'
                + close_indent
                + ")"
            )

        # --------------------------------------
        # SINGLE-LINE CALLS
        # --------------------------------------

        else:

            if not original.endswith(")"):
                raise RuntimeError(
                    f"Unexpected authorization call "
                    f"in {filename}: {fn.name}"
                )

            updated = (
                original[:-1]
                + f', permission="{permission}")'
            )

        replacements.append(
            (start, end, updated)
        )

        found.add(
            fn.name
        )

    # ------------------------------------------
    # ENSURE NO FUNCTIONS WERE MISSED
    # ------------------------------------------

    if found != set(RULES[filename]):

        missing = (
            set(RULES[filename]) - found
        )

        raise RuntimeError(
            f"{filename}: Missing functions: "
            f"{sorted(missing)}"
        )

    # ==================================================
    # REPLACE THE TWO LEGACY ADMIN CHECKS
    # ==================================================

    if filename in {
        "admin_operations_service.py",
        "admin_content_service.py",
    }:

        local_checks = [
            node
            for node in tree.body
            if (
                isinstance(node, ast.FunctionDef)
                and node.name == "_require_admin"
            )
        ]

        if len(local_checks) != 1:
            raise RuntimeError(
                f"{filename}: Expected one local "
                "administrator authorization function."
            )

        start, end = _span(
            local_checks[0],
            starts,
        )

        replacements.append(
            (start, end, SHARED_CHECK)
        )

    # ==================================================
    # APPLY CHANGES IN REVERSE SOURCE ORDER
    # ==================================================

    for start, end, replacement in sorted(
        replacements,
        reverse=True,
    ):
        source = (
            source[:start]
            + replacement
            + source[end:]
        )

    # ------------------------------------------
    # VALIDATE PYTHON SYNTAX
    # ------------------------------------------

    compile(
        source,
        filename,
        "exec",
    )

    # ------------------------------------------
    # VALIDATE ALL AUTHORIZATION KEYWORDS
    # ------------------------------------------

    updated_tree = ast.parse(
        source,
        filename=filename,
    )

    for fn in updated_tree.body:

        if not (
            isinstance(fn, ast.FunctionDef)
            and fn.name in RULES[filename]
        ):
            continue

        calls = [
            node
            for node in ast.walk(fn)
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_require_admin"
            )
        ]

        assert len(calls) == 1

        assert len(
            calls[0].keywords
        ) == 1

        keyword = calls[0].keywords[0]

        assert keyword.arg == "permission"

        assert isinstance(
            keyword.value,
            ast.Constant,
        )

        assert (
            keyword.value.value
            == RULES[filename][fn.name]
        )

    return source


# ==========================================================
# MAIN
# ==========================================================

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Back up and apply validated changes.",
    )

    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]

    services = root / "services"

    transformed = {}

    # ------------------------------------------
    # FIRST VALIDATE EVERY SERVICE
    # ------------------------------------------

    for filename in RULES:

        path = services / filename

        if not path.is_file():
            raise SystemExit(
                f"Missing file: {path}. "
                "Nothing has been modified."
            )

        original = path.read_text(
            encoding="utf-8"
        )

        transformed[path] = _rewrite(
            original,
            filename,
        )

        print(
            f"Validated {filename}: "
            f"{len(RULES[filename])} permission checks"
        )

    # ------------------------------------------
    # DRY RUN BY DEFAULT
    # ------------------------------------------

    if not args.apply:

        print(
            "\nDry run completed. "
            "No files changed."
        )

        print(
            "Run again with --apply "
            "to save the updates."
        )

        return

    # ------------------------------------------
    # BACK UP ORIGINAL FILES
    # ------------------------------------------

    backups = (
        root.parent
        / f"{root.name}_rbac_backup"
    )

    backups.mkdir(
        parents=True,
        exist_ok=True,
    )

    for path in transformed:

        backup = backups / path.name

        if backup.exists():
            raise SystemExit(
                f"Backup already exists: {backup}. "
                "No files changed."
            )

    for path in transformed:

        shutil.copy2(
            path,
            backups / path.name,
        )

    # ------------------------------------------
    # SAVE VERIFIED CHANGES
    # ------------------------------------------

    for path, content in transformed.items():

        path.write_text(
            content,
            encoding="utf-8",
        )

    total = sum(
        len(items)
        for items in RULES.values()
    )

    print(
        f"\nApplied {total} permission checks "
        "across seven services."
    )

    print(
        f"Original files backed up at: {backups}"
    )


if __name__ == "__main__":
    main()
