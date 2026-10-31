import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

from miningcat.config.app_info import GITHUB_URL
from miningcat.config.paths import PROJECT_ROOT
from miningcat.config.runtime import PYTHON, SRC_DIR, module_command
from miningcat.infrastructure import http
from miningcat.infrastructure.system import pip

REPOSITORY = GITHUB_URL.removeprefix("https://github.com/")
BRANCH = "main"
WORKFLOW = "actions.yml"  # .github/workflows/: the tests, on every push
# The newest run of the CI that passed, on a commit pushed to main.
RUNS_URL = f"https://api.github.com/repos/{REPOSITORY}/actions/workflows/{WORKFLOW}/runs"
RUNS_PARAMS = {"branch": BRANCH, "event": "push", "status": "success", "per_page": "1"}
API_TIMEOUT_S = 5
FETCH_TIMEOUT_S = 30
# The changes shown by the home page, newest first.
MAX_CHANGES = 20
# Installed apart, with --no-deps: same as the Makefile's.
OWOCR_REQUIREMENT = "owocr>=1.26.8"
ENGINE_INSTALL = "src/miningcat/infrastructure/speech/engine_install.py"
TRANSLATION_INSTALL = "src/miningcat/infrastructure/translation/install.py"
# The files telling how the packages are installed, besides the requirements: only the lines telling what they install
# count (a new target of the Makefile, a comment... install nothing again).
INSTALL_FILES = {"Makefile", ENGINE_INSTALL, TRANSLATION_INSTALL}
_INSTALL_LINE = re.compile(r"^[+-](?![+-]).*(REQUIREMENT|requirements|pip|torch|owocr)", re.M)


class UpdateError(Exception):
    pass


@dataclass(frozen=True)
class UpdateCheck:
    """Where the clone stands: its commit, the commit to update to, and the subjects of the commits between them.
    `off`: why the clone can't update on its own; `error`: why the look for an update failed this time (offline...).
    No update with either."""

    current: str = ""
    target: str = ""
    changes: list[str] = field(default_factory=list)
    commits: int = 0
    off: str = ""
    error: str = ""

    @property
    def available(self) -> bool:
        return not self.off and not self.error and self.commits > 0

    def to_dict(self) -> dict:
        return {"available": self.available, "current": self.current[:7], "target": self.target[:7],
                "commits": self.commits, "changes": self.changes, "off": self.off, "error": self.error}


@dataclass(frozen=True)
class UpdateResult:
    """`returncode`: the install of the packages' (0 when it went well, or had nothing to install)."""

    commits: int
    returncode: int = 0


def _git(*args: str, timeout: float | None = 10) -> subprocess.CompletedProcess:
    """Raises UpdateError when git can't run or takes too long."""
    try:
        # GIT_TERMINAL_PROMPT=0: a remote asking for a password fails instead of waiting for it.
        return subprocess.run(["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=timeout,
                              check=False, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    except subprocess.TimeoutExpired:
        raise UpdateError(f"git {args[0]} took more than {timeout:g} s.")
    except OSError as exc:
        raise UpdateError(f"git can't run: {exc}")


def _git_out(*args: str, timeout: float | None = 10) -> str:
    done = _git(*args, timeout=timeout)
    if done.returncode != 0:
        raise UpdateError(f"git {args[0]} failed: {(done.stderr or done.stdout).strip()}")
    return done.stdout.strip()


def _is_repository(url: str) -> bool:
    """Whether a remote's URL is MiningCat's GitHub repository (https or ssh, with or without .git)."""
    return re.search(rf"^(https://|ssh://git@|git@)github\.com[:/]{re.escape(REPOSITORY)}(\.git)?/?$", url.strip(),
                     re.I) is not None


def _local_changes() -> bool:
    """Changes to the files git follows (the code). Untracked files don't count: a fast-forward keeps them."""
    return bool(_git_out("status", "--porcelain", "--untracked-files=no"))


def why_off() -> str:
    """Why the clone can't update on its own, "" when it can. Raises UpdateError when git fails."""
    if not (PROJECT_ROOT / ".git").exists():
        return "MiningCat wasn't installed with git clone: download the new version again to update."
    if shutil.which("git") is None:
        return "git isn't installed (or not in the PATH)."
    try:
        branch = _git_out("rev-parse", "--abbrev-ref", "HEAD")
        if branch != BRANCH:
            return f"The clone is on the branch {branch}, not {BRANCH}: update it with git."
        if not _is_repository(_git_out("remote", "get-url", "origin")):
            return f"The clone's origin isn't {GITHUB_URL}: update it with git."
        if _local_changes():
            return "The code has local changes (git status): update it with git."
    except UpdateError as exc:  # not why it's off: what failed this time
        raise UpdateError(f"git doesn't answer: {exc}")
    return ""


def latest_passing_commit() -> str:
    """The newest commit of main whose CI passed, from GitHub."""
    try:
        runs = json.loads(http.get(RUNS_URL, RUNS_PARAMS, timeout=API_TIMEOUT_S)).get("workflow_runs") or []
    except (OSError, ValueError) as exc:  # URLError and HTTPError are OSErrors; ValueError: not JSON
        raise UpdateError(f"GitHub can't be reached: {exc}")
    if not runs or not runs[0].get("head_sha"):
        raise UpdateError("GitHub knows no commit of main whose tests passed.")
    return runs[0]["head_sha"]


def check() -> UpdateCheck:
    """Whether a newer commit of main passed the CI. Only a fast-forward counts: a clone ahead of it (local commits,
    or a commit pulled before its tests were done) waits for the next one."""
    try:
        off = why_off()
        if off:
            return UpdateCheck(off=off)
        current = _git_out("rev-parse", "HEAD")
        target = latest_passing_commit()
        if target == current:
            return UpdateCheck(current, target)
        _git_out("fetch", "--quiet", "origin", BRANCH, timeout=FETCH_TIMEOUT_S)
        ancestor = _git("merge-base", "--is-ancestor", current, target).returncode
        if ancestor == 1:
            return UpdateCheck(current, target)
        if ancestor != 0:  # the commit is unknown (main rewritten?), or git failed
            raise UpdateError(f"git can't compare the code with {target[:7]}.")
        commits = int(_git_out("rev-list", "--count", f"{current}..{target}"))
        changes = _git_out("log", f"--max-count={MAX_CHANGES}", "--format=%s", f"{current}..{target}").splitlines()
    except (UpdateError, ValueError) as exc:
        return UpdateCheck(error=str(exc))
    return UpdateCheck(current, target, changes, commits)


def miningcat_commands(changed: set[str]) -> list[list[str]]:
    """The commands installing again MiningCat's packages (`make install`: PyTorch's CPU build first, on Linux without
    an NVIDIA GPU) when their requirements changed (`changed`: the files the update changed)."""
    if not changed & {"requirements.txt", "Makefile"}:
        return []
    pytorch = [pip.install("torch", "torchaudio", "torchvision", "--index-url", pip.PYTORCH_CPU_INDEX)]
    return [*(pytorch if pip.cpu_pytorch() else []), pip.install("-r", str(PROJECT_ROOT / "requirements.txt")),
            pip.install("--no-deps", OWOCR_REQUIREMENT)]


def engine_commands(changed: set[str]) -> list[list[str]]:
    """The commands installing again the packages of the optional engines already installed whose requirements
    changed: speech (engine_install.py) and translation (translation/install.py)."""
    # Imported here: the install of MiningCat's packages goes first (see install_since).
    from miningcat.infrastructure.speech import engine_install
    from miningcat.infrastructure.translation import install as translation_install

    engines = ENGINE_INSTALL in changed
    commands = []
    # Taigi's engines are Qwen3-ASR's and more.
    if engine_install.installed(engine_install.TAIGI):
        if engines or changed & {"requirements-qwen.txt", "requirements-taigi.txt"}:
            commands += engine_install.commands(engine_install.TAIGI)
    elif engine_install.installed(engine_install.QWEN):
        if engines or "requirements-qwen.txt" in changed:
            commands += engine_install.commands(engine_install.QWEN)
    if engine_install.installed(engine_install.OMNIVOICE) and (engines or "requirements-omnivoice.txt" in changed):
        commands += engine_install.commands(engine_install.OMNIVOICE)
    # The translation models' engines (Qwen3 shares Qwen3-ASR's packages: not twice)
    for engine, requirements in translation_install.ENGINES.items():
        if changed & {requirements, TRANSLATION_INSTALL} and engine.available():
            commands += [c for c in translation_install.commands(next(iter(engine.MODELS))) if c not in commands]
    return commands


def _changed_since(old: str) -> set[str]:
    """The files changed since the commit `old`; INSTALL_FILES only when what they install changed."""
    changed = set(_git_out("diff", "--name-only", old, "HEAD").splitlines())
    for path in INSTALL_FILES & changed:
        if not _INSTALL_LINE.search(_git_out("diff", "--unified=0", old, "HEAD", "--", path)):
            changed.discard(path)
    return changed


def install_since(old: str) -> int:
    """Installs again the packages whose requirements changed since the commit `old`, pip's output going to this
    process's: MiningCat's, then the engines'. Returns the exit code of the first command that fails, else 0."""
    try:
        changed = _changed_since(old)
    except UpdateError as exc:
        print(f"{exc}: run make install.")
        return 1
    return pip.run(miningcat_commands(changed)) or pip.run(engine_commands(changed))


def install_packages(old: str) -> int:
    """install_since(old) in a new process, with the code there is now. Returns its exit code."""
    try:
        return subprocess.run(module_command("miningcat.infrastructure.system.updates", old), cwd=SRC_DIR,
                              check=False).returncode
    except OSError as exc:
        print(f"The install of the packages can't start: {exc}")
        return 1


def head() -> str:
    """The commit of the clone. Raises UpdateError when git can't tell it."""
    return _git_out("rev-parse", "HEAD")


def update(check_: UpdateCheck, install: bool = True) -> UpdateResult:
    """Moves the clone forward to `check_.target` (a fast-forward), then installs the packages that changed (unless
    not `install`: the caller does it, with install_packages). Raises UpdateError when the code didn't move; once it
    moved, an install that fails is a returncode."""
    if not check_.available:
        raise UpdateError(check_.off or check_.error or "MiningCat is up to date.")
    off = why_off()
    if off:
        raise UpdateError(off)
    current = head()
    if current != check_.current:
        raise UpdateError("The code changed since the check: check again.")
    # No timeout: a merge killed halfway would leave the code half updated.
    try:
        _git_out("merge", "--ff-only", "--quiet", check_.target, timeout=None)
    except UpdateError:
        if head() == current:
            raise
    return UpdateResult(check_.commits, install_packages(current) if install else 0)


if __name__ == "__main__":
    sys.exit(install_since(sys.argv[1]))
