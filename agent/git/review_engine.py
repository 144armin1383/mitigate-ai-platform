from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple, TypedDict, Union, Literal


# Types
StatusLiteral = Literal[
    "A",  # added
    "M",  # modified
    "D",  # deleted
    "R",  # renamed
    "C",  # copied (unlikely in our usage but included for completeness)
    "T",  # type change
    "U",  # unmerged
    "X",  # unknown
    "B",  # broken pairing
    "?",  # untracked (should not appear in committed diffs)
]


@dataclass(frozen=True)
class FileChange:
    path: str
    status: StatusLiteral
    old_path: Optional[str] = None
    insertions: int = 0
    deletions: int = 0


class FileChangeDict(TypedDict, total=False):
    path: str
    status: str
    old_path: str
    insertions: int
    deletions: int


class FileCategoryFinding(TypedDict):
    path: str
    reason: str


class ReviewReport(TypedDict, total=False):
    base_ref: str
    target_ref: str
    validation: Dict[str, Union[bool, List[str]]]
    files: Dict[str, List[FileChangeDict]]
    stats: Dict[str, int]
    categories: Dict[str, Union[List[str], List[FileCategoryFinding]]]
    summary: str
    risk_level: Literal["low", "medium", "high", "critical"]
    merge_recommendation: Literal["approve", "manual_review", "reject"]
    recommendations: List[str]
    logs: List[str]


class GitReviewEngine:
    """
    Production-grade Git Review Engine.

    - Operates repository-relative only (no remote/network operations).
    - Uses fixed-argument subprocess calls (no shells) and never mutates Git state.
    - Validates refs strictly prior to use.
    - Detects high-risk categories and secret-like files (critical on any detection).
    - Produces a deterministic, structured review report.
    """

    def __init__(self, repo_path: str = ".") -> None:
        self.repo_path = os.path.abspath(repo_path)

    # -----------------
    # Public API
    # -----------------
    def review(self, base_ref: str, target_ref: str) -> ReviewReport:
        logs: List[str] = []
        validation_errors: List[str] = []

        # Validate refs
        if not self.validate_git_ref(base_ref):
            validation_errors.append(f"Invalid base ref: {base_ref!r}")
        if not self.validate_git_ref(target_ref):
            validation_errors.append(f"Invalid target ref: {target_ref!r}")

        report: ReviewReport = {
            "base_ref": base_ref,
            "target_ref": target_ref,
            "validation": {"ok": len(validation_errors) == 0, "errors": validation_errors},
            "files": {"added": [], "modified": [], "deleted": [], "renamed": []},
            "stats": {
                "total_files_changed": 0,
                "insertions": 0,
                "deletions": 0,
                "renames": 0,
            },
            "categories": {"findings": [], "high_risk_files": []},
            "summary": "",
            "risk_level": "low",
            "merge_recommendation": "approve",
            "recommendations": [],
            "logs": logs,
        }

        if validation_errors:
            logs.append("Ref validation failed; aborting diff operations.")
            # Return conservative recommendation
            report["risk_level"] = "high"
            report["merge_recommendation"] = "manual_review"
            report["summary"] = "Ref validation failed. Manual review required."
            return report

        # Gather diffs
        try:
            name_status = self._git_diff_name_status(base_ref, target_ref, logs)
            numstats = self._git_diff_numstat(base_ref, target_ref, logs)
            perm_changes = self._git_diff_permission_changes(base_ref, target_ref, logs)
        except GitCommandError as e:
            validation_errors.append(str(e))
            report["validation"] = {"ok": False, "errors": validation_errors}
            report["risk_level"] = "high"
            report["merge_recommendation"] = "manual_review"
            report["summary"] = "Git diff inspection failed. Manual review required."
            logs.append(f"Git command error: {e}")
            return report

        # Merge per-file stats with status data
        file_changes: List[FileChange] = self._merge_changes(name_status, numstats)

        # Build report files breakdown
        for ch in file_changes:
            entry: FileChangeDict = {
                "path": ch.path,
                "status": ch.status,
                "insertions": ch.insertions,
                "deletions": ch.deletions,
            }
            if ch.old_path:
                entry["old_path"] = ch.old_path

            if ch.status == "A":
                report["files"]["added"].append(entry)
            elif ch.status == "M":
                report["files"]["modified"].append(entry)
            elif ch.status == "D":
                report["files"]["deleted"].append(entry)
            elif ch.status == "R":
                report["files"]["renamed"].append(entry)
            else:
                # Ignore other statuses for the high-level buckets but they are counted in totals.
                pass

        # Stats
        total_insertions = sum(ch.insertions for ch in file_changes)
        total_deletions = sum(ch.deletions for ch in file_changes)
        total_changed = len(file_changes)
        rename_count = sum(1 for ch in file_changes if ch.status == "R")

        report["stats"]["total_files_changed"] = total_changed
        report["stats"]["insertions"] = total_insertions
        report["stats"]["deletions"] = total_deletions
        report["stats"]["renames"] = rename_count

        logs.append(
            f"Aggregated stats: files={total_changed}, +{total_insertions}, -{total_deletions}, renames={rename_count}"
        )

        # Risk detection and categorization
        findings, high_risk_files, risk_level = self._analyze_risks(file_changes, perm_changes, logs)
        report["categories"]["findings"] = findings
        report["categories"]["high_risk_files"] = high_risk_files
        report["risk_level"] = risk_level

        # Merge recommendation
        report["merge_recommendation"] = self._merge_recommendation_for_risk(risk_level)

        # Summary and recommendations
        report["summary"] = self._build_summary(report)
        report["recommendations"] = self._recommendations(report)

        return report

    # -----------------
    # Validation
    # -----------------
    @staticmethod
    def validate_git_ref(ref: str) -> bool:
        """
        Validate a Git ref name according to Git's rules while allowing common branch/tag patterns.

        Acceptance Criteria:
        - Allow: main, feature/login, release/1.0, v1.0.0, hotfix-123, refs/heads/main
        - Reject: empty, whitespace/control chars, backslashes, shell metacharacters, '@{', '..',
          consecutive slashes, leading slash, trailing slash, trailing dot, '.lock' suffix, starting with '-'.
        """
        if not isinstance(ref, str):
            return False
        if ref == "":
            return False

        # Disallowed characters
        # Based on git-check-ref-format; we reject a conservative superset per requirements
        if any(c.isspace() for c in ref):
            return False
        if any(ord(c) < 32 or ord(c) == 127 for c in ref):
            return False
        if ref.startswith("-"):
            return False
        if ref.startswith("/"):
            return False
        if ref.endswith("/"):
            return False
        if ref.endswith("."):
            return False
        if ref.endswith(".lock"):
            return False
        if "\\" in ref:
            return False
        if "@{" in ref:
            return False
        if ".." in ref:
            return False
        if "//" in ref:
            return False
        # Shell metacharacters and other forbidden chars for refs
        if any(ch in ref for ch in ["~", "^", ":", "?", "*", "[", "]", "\\", "\n"]):
            return False

        # No dot-lock suffix in any path component and no component may be empty
        parts = ref.split("/")
        for p in parts:
            if p == "":
                return False
            if p.endswith(".lock"):
                return False
            if p.startswith(".") and p in {".", ".."}:
                return False
            if p.endswith("."):
                return False

        return True

    # -----------------
    # Secret-like detection
    # -----------------
    @staticmethod
    def is_secret_like(path: str) -> bool:
        """
        Detect secret-like filenames using basename and full path, case-insensitive, without reading file contents.

        Matches:
        - .env, .env.*
        - *.pem, *.key
        - id_rsa, id_ed25519
        - credentials.*, secrets.*
        - Any filename or path containing: token, secret, password, credential
        """
        p = path.strip()
        if p == "":
            return False
        lower_path = p.casefold()
        name = os.path.basename(p).casefold()

        # Exact and prefix matches for .env
        if name == ".env" or name.startswith(".env."):
            return True

        # Private key/cert files
        if name.endswith(".pem") or name.endswith(".key"):
            return True

        # Common SSH key names
        if name in {"id_rsa", "id_ed25519"}:
            return True

        # credentials.* or secrets.*
        if name.startswith("credentials.") or name.startswith("secrets."):
            return True

        # Token-like or password-like keywords in basename or full path
        keywords = ("token", "secret", "password", "credential")
        if any(k in name for k in keywords):
            return True
        if any(k in lower_path for k in keywords):
            return True

        return False

    # -----------------
    # Git helpers
    # -----------------
    def _git(self, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
        """
        Internal: Call git with fixed arguments, repository-relative only.
        Never uses shell, never mutates state.
        """
        cmd = ["git", "-C", self.repo_path, *args]
        # No shell, fixed arguments only.
        try:
            return subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            stdout = e.stdout or ""
            stderr = e.stderr or ""
            raise GitCommandError(
                f"Git command failed: {shlex.join(cmd)} | stdout: {stdout.strip()} | stderr: {stderr.strip()}"
            )

    def _git_diff_name_status(self, base: str, target: str, logs: List[str]) -> List[Tuple[StatusLiteral, str, Optional[str]]]:
        # --find-renames to detect renames, no rename limits.
        args = ["diff", "--name-status", "--find-renames", f"{base}..{target}"]
        logs.append(f"Running: git {' '.join(args)}")
        cp = self._git(args)
        output = cp.stdout
        lines = [ln for ln in output.splitlines() if ln.strip()]
        result: List[Tuple[StatusLiteral, str, Optional[str]]] = []
        for ln in lines:
            parts = ln.split("\t")
            if not parts:
                continue
            status = parts[0]
            if status.startswith("R") or status.startswith("C"):
                # R100 or Rxx: rename with score. Expect 3 columns: status, old, new
                if len(parts) >= 3:
                    old_path = parts[1]
                    new_path = parts[2]
                    result.append(("R", new_path, old_path))
                continue
            if len(status) >= 1:
                st = status[0]
            else:
                continue
            if st not in {"A", "M", "D", "T", "U", "X", "B", "?"}:
                continue
            path = parts[1] if len(parts) > 1 else ""
            if not path:
                continue
            result.append((st, path, None))
        logs.append(f"Parsed name-status entries: {len(result)}")
        return result

    def _git_diff_numstat(self, base: str, target: str, logs: List[str]) -> Dict[str, Tuple[int, int, Optional[str]]]:
        # Map new_path -> (insertions, deletions, old_path_if_rename)
        args = ["diff", "--numstat", f"{base}..{target}"]
        logs.append(f"Running: git {' '.join(args)}")
        cp = self._git(args)
        output = cp.stdout
        numstats: Dict[str, Tuple[int, int, Optional[str]]] = {}
        for ln in output.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            # format: <ins>\t<del>\t<path or 'old => new'>
            parts = ln.split("\t")
            if len(parts) < 3:
                continue
            try:
                ins = int(parts[0]) if parts[0] != "-" else 0
            except ValueError:
                ins = 0
            try:
                dels = int(parts[1]) if parts[1] != "-" else 0
            except ValueError:
                dels = 0
            path_field = parts[2]
            old_path: Optional[str] = None
            new_path = path_field
            # Handle rename representation: "old/path => new/path"
            if " => " in path_field:
                # It may include braces around the changed component in some git outputs, but for simplicity we split by ' => '
                old_path, new_path = [seg.strip() for seg in path_field.split(" => ", 1)]
                # Remove potential surrounding braces if present
                old_path = old_path.strip("{}")
                new_path = new_path.strip("{}")
            numstats[new_path] = (ins, dels, old_path)
        logs.append(f"Parsed numstat entries: {len(numstats)}")
        return numstats

    def _git_diff_permission_changes(self, base: str, target: str, logs: List[str]) -> List[str]:
        # Parse git diff --summary for mode changes
        args = ["diff", "--summary", f"{base}..{target}"]
        logs.append(f"Running: git {' '.join(args)}")
        cp = self._git(args)
        output = cp.stdout
        changed_paths: List[str] = []
        for ln in output.splitlines():
            s = ln.strip()
            # Example: "mode change 100644 => 100755 path/to/file"
            if s.startswith("mode change "):
                # Try to extract the trailing path after the modes
                # Pattern: mode change <old> => <new> <path>
                m = re.match(r"mode change \d+ => \d+\s+(.+)", s)
                if m:
                    changed_paths.append(m.group(1).strip())
                else:
                    # Fallback: last token(s) likely path
                    tokens = s.split()
                    if len(tokens) >= 5:
                        changed_paths.append(" ".join(tokens[4:]))
        logs.append(f"Detected permission changes: {len(changed_paths)}")
        return changed_paths

    # -----------------
    # Aggregation and risk analysis
    # -----------------
    def _merge_changes(
        self,
        name_status: List[Tuple[StatusLiteral, str, Optional[str]]],
        numstats: Dict[str, Tuple[int, int, Optional[str]]],
    ) -> List[FileChange]:
        by_new_path: Dict[str, FileChange] = {}

        for st, path, old in name_status:
            ins = 0
            dels = 0
            ns_old: Optional[str] = old
            if path in numstats:
                ins, dels, nm_old = numstats.get(path, (0, 0, None))
                if nm_old and not ns_old:
                    ns_old = nm_old
            if st == "R" and not ns_old:
                # If rename without old path in either source, keep as is
                ns_old = None
            ch = FileChange(path=path, status=st, old_path=ns_old, insertions=ins, deletions=dels)
            by_new_path[path] = ch

        # Edge: files present in numstats but not in name_status (rare). Include as modified entries.
        for path, (ins, dels, old) in numstats.items():
            if path not in by_new_path:
                st: StatusLiteral = "M"
                by_new_path[path] = FileChange(path=path, status=st, old_path=old, insertions=ins, deletions=dels)

        return list(by_new_path.values())

    def _analyze_risks(
        self, file_changes: List[FileChange], perm_changes: List[str], logs: List[str]
    ) -> Tuple[List[str], List[FileCategoryFinding], Literal["low", "medium", "high", "critical"]]:
        findings: List[str] = []
        high_risk_files: List[FileCategoryFinding] = []

        any_secret_like = False
        any_permission_change = len(perm_changes) > 0
        any_deployment_change = False
        any_db_migration_change = False
        any_dependency_manifest_change = False
        any_sensitive_deletion = False

        for ch in file_changes:
            p = ch.path

            # Secret-like detection (critical regardless of status)
            if self.is_secret_like(p) or (ch.old_path and self.is_secret_like(ch.old_path)):
                any_secret_like = True
                high_risk_files.append({"path": p, "reason": "secret-like filename detected"})

            # Deployment related
            if self._is_deployment_file(p):
                any_deployment_change = True
                if ch.status == "D":
                    any_sensitive_deletion = True
                if not self.is_secret_like(p):
                    findings.append(f"Deployment-related file changed: {p}")

            # Database migrations
            if self._is_db_migration_file(p):
                any_db_migration_change = True
                if ch.status == "D":
                    any_sensitive_deletion = True
                findings.append(f"Database migration or SQL file changed: {p}")

            # Dependency manifests
            if self._is_dependency_manifest(p):
                any_dependency_manifest_change = True
                findings.append(f"Dependency manifest changed: {p}")

            # Authentication/Security/Payment sensitive deletions
            if ch.status == "D" and self._is_auth_security_payment_file(p):
                any_sensitive_deletion = True
                findings.append(f"Sensitive file deleted: {p}")

        # Permission changes
        if any_permission_change:
            for p in perm_changes:
                findings.append(f"File permissions changed: {p}")

        # Determine risk level deterministically
        risk: Literal["low", "medium", "high", "critical"] = "low"
        if any_secret_like:
            risk = "critical"
        else:
            if any_permission_change or any_deployment_change or any_db_migration_change or any_dependency_manifest_change or any_sensitive_deletion:
                risk = "high"
            else:
                # Size-based heuristic
                total_lines = sum(ch.insertions + ch.deletions for ch in file_changes)
                if total_lines > 1000 or len(file_changes) > 200:
                    risk = "high"
                elif total_lines > 200 or len(file_changes) > 50:
                    risk = "medium"
                else:
                    risk = "low"

        if any_sensitive_deletion and risk != "critical":
            # Ensure at least high when sensitive deletions present
            risk = "high"

        logs.append(
            "Risk assessment: "
            + ", ".join(
                [
                    f"secret_like={any_secret_like}",
                    f"perm_change={any_permission_change}",
                    f"deploy_change={any_deployment_change}",
                    f"db_migration={any_db_migration_change}",
                    f"deps_changed={any_dependency_manifest_change}",
                    f"sensitive_deletion={any_sensitive_deletion}",
                    f"risk={risk}",
                ]
            )
        )

        return findings, high_risk_files, risk

    # -----------------
    # Categorization helpers
    # -----------------
    @staticmethod
    def _is_deployment_file(path: str) -> bool:
        p = path.casefold()
        name = os.path.basename(p)
        if name in {"dockerfile", "jenkinsfile"}:
            return True
        if p.endswith("docker-compose.yml") or p.endswith("docker-compose.yaml"):
            return True
        if "/.github/workflows/" in p or p.startswith(".github/workflows/"):
            return True
        if "/.circleci/" in p or p.startswith(".circleci/"):
            return True
        if name in {".gitlab-ci.yml", ".gitlab-ci.yaml"}:
            return True
        # Kubernetes/Helm indicators
        if any(seg in p for seg in ["/k8s/", "/kubernetes/", "/helm/", "/charts/"]):
            return True
        if name in {"kustomization.yaml", "kustomization.yml"}:
            return True
        if name in {"deployment.yaml", "deployment.yml", "service.yaml", "service.yml"}:
            return True
        return False

    @staticmethod
    def _is_db_migration_file(path: str) -> bool:
        p = path.casefold()
        if p.endswith(".sql"):
            return True
        if "/migrations/" in p or "/migration/" in p or "/db/migrate/" in p:
            return True
        if "/alembic/versions/" in p:
            return True
        # Django style: app/migrations/0001_initial.py
        if re.search(r"/migrations/\d+_", p):
            return True
        return False

    @staticmethod
    def _is_dependency_manifest(path: str) -> bool:
        name = os.path.basename(path.casefold())
        if name.startswith("requirements") and name.endswith(".txt"):
            return True
        if name in {"pipfile", "pyproject.toml", "poetry.lock", "package.json", "package-lock.json", "yarn.lock", "composer.json", "composer.lock"}:
            return True
        return False

    @staticmethod
    def _is_auth_security_payment_file(path: str) -> bool:
        p = path.casefold()
        keywords = ["auth", "oauth", "saml", "jwt", "security", "payment", "stripe", "paypal"]
        return any(k in p for k in keywords)

    # -----------------
    # Presentation helpers
    # -----------------
    @staticmethod
    def _merge_recommendation_for_risk(risk: Literal["low", "medium", "high", "critical"]) -> Literal[
        "approve", "manual_review", "reject"
    ]:
        if risk == "low":
            return "approve"
        if risk in ("medium", "high"):
            return "manual_review"
        return "reject"

    @staticmethod
    def _build_summary(report: ReviewReport) -> str:
        stats = report.get("stats", {})
        files = report.get("files", {})
        added = len(files.get("added", []))
        modified = len(files.get("modified", []))
        deleted = len(files.get("deleted", []))
        renamed = len(files.get("renamed", []))
        return (
            f"Changes from {report.get('base_ref')} to {report.get('target_ref')}: "
            f"{stats.get('total_files_changed', 0)} files changed, "
            f"{stats.get('insertions', 0)} insertions(+), {stats.get('deletions', 0)} deletions(-); "
            f"added={added}, modified={modified}, deleted={deleted}, renamed={renamed}."
        )

    @staticmethod
    def _recommendations(report: ReviewReport) -> List[str]:
        recs: List[str] = []
        findings = report.get("categories", {}).get("findings", [])
        risk = report.get("risk_level", "low")
        if findings:
            recs.append("Review the listed high-impact areas.")
        if risk in ("medium", "high", "critical"):
            recs.append("Run full test suite and security checks.")
        if any("permissions changed" in f.lower() for f in findings):
            recs.append("Manually verify file permission changes are intentional and minimal.")
        if any("dependency manifest" in f.lower() for f in findings):
            recs.append("Rebuild dependencies in a clean environment and scan for supply-chain risks.")
        if any("database migration" in f.lower() for f in findings):
            recs.append("Apply migrations in a staging environment and verify rollback procedures.")
        if risk == "critical":
            recs.append("Do not merge. Escalate for security review.")
        if not recs:
            recs.append("No special actions required. Proceed with standard code review.")
        return recs


class GitCommandError(RuntimeError):
    pass


__all__ = [
    "GitReviewEngine",
    "FileChange",
    "ReviewReport",
]
