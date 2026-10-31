import json
import shutil
from types import SimpleNamespace
import subprocess
import urllib.error

import pytest

from miningcat.infrastructure.speech import engine_install
from miningcat.infrastructure.system import updates

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git isn't installed")
IS_REPOSITORY = updates._is_repository


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def commit(repo, name, text="x"):
    (repo / name).write_text(text)
    git(repo, "add", name)
    git(repo, "commit", "--quiet", "-m", f"add {name}")
    return git(repo, "rev-parse", "HEAD")


class FakeGitHub:
    """GitHub's API: the newest commit of main whose CI passed (None: no run passed; an exception: unreachable)."""

    def __init__(self):
        self.passing = None
        self.error = None

    def get(self, url, params=None, timeout=8):
        assert url == updates.RUNS_URL and params["status"] == "success" and params["branch"] == "main"
        if self.error:
            raise self.error
        runs = [{"head_sha": self.passing}] if self.passing else []
        return json.dumps({"workflow_runs": runs}).encode()


@pytest.fixture
def github(monkeypatch):
    fake = FakeGitHub()
    monkeypatch.setattr(updates.http, "get", fake.get)
    return fake


@pytest.fixture
def repos(tmp_path, monkeypatch, github):
    """MiningCat's repository (origin) and the user's clone of it, the project's root."""
    for key, value in {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                       "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": str(tmp_path / "gitconfig")}.items():
        monkeypatch.setenv(key, value)
    origin, clone = tmp_path / "origin", tmp_path / "clone"
    origin.mkdir()
    git(origin, "init", "--quiet", "-b", "main")
    github.passing = commit(origin, "requirements.txt", "flask\n")
    git(tmp_path, "clone", "--quiet", str(origin), str(clone))
    monkeypatch.setattr(updates, "PROJECT_ROOT", clone)
    # The clone's origin is a folder, not GitHub
    monkeypatch.setattr(updates, "_is_repository", lambda url: True)
    return origin, clone


@pytest.fixture
def processes(monkeypatch):
    """The commands run besides git's (pip, the install process): recorded, with the exit code of `returncodes`."""
    run = subprocess.run
    calls, returncodes = [], []

    def fake_run(command, *args, **kwargs):
        if command[0] == "git":
            return run(command, *args, **kwargs)
        calls.append(command)
        return subprocess.CompletedProcess(command, returncodes.pop(0) if returncodes else 0)

    monkeypatch.setattr(updates.subprocess, "run", fake_run)
    return calls, returncodes


def test_up_to_date_when_the_clone_is_at_the_newest_passing_commit(repos):
    check = updates.check()
    assert not check.available and not check.off and check.current == check.target


def test_newer_passing_commits_are_offered_newest_first(repos, github):
    origin, _ = repos
    commit(origin, "a.txt")
    github.passing = commit(origin, "b.txt")
    check = updates.check()
    assert check.available and check.target == github.passing
    assert check.commits == 2 and check.changes == ["add b.txt", "add a.txt"]
    assert check.to_dict() == {"available": True, "current": check.current[:7], "target": github.passing[:7],
                               "commits": 2, "changes": ["add b.txt", "add a.txt"], "off": "", "error": ""}


def test_a_commit_whose_tests_did_not_pass_waits(repos, github):
    origin, _ = repos
    github.passing = commit(origin, "a.txt")
    commit(origin, "b.txt")  # its CI failed, or runs
    check = updates.check()
    assert check.target == github.passing and check.commits == 1 and check.changes == ["add a.txt"]


def test_a_clone_ahead_of_the_passing_commit_waits(repos):
    _, clone = repos
    commit(clone, "mine.txt")
    check = updates.check()
    assert not check.available and not check.off


def test_github_unreachable(repos, github):
    github.error = urllib.error.URLError("offline")
    check = updates.check()
    # Failed this time, not off
    assert not check.available and not check.off and "GitHub can't be reached" in check.error


def test_no_passing_commit(repos, github):
    github.passing = None
    assert "no commit of main whose tests passed" in updates.check().error


def test_off_without_git_clone(tmp_path, monkeypatch):
    monkeypatch.setattr(updates, "PROJECT_ROOT", tmp_path)
    assert "git clone" in updates.check().off


def test_off_on_another_branch(repos):
    _, clone = repos
    git(clone, "checkout", "--quiet", "-b", "mine")
    assert "branch mine" in updates.check().off


def test_off_with_local_changes_to_the_code(repos):
    _, clone = repos
    (clone / "requirements.txt").write_text("changed\n")
    assert "local changes" in updates.check().off


def test_untracked_files_do_not_count(repos):
    _, clone = repos
    (clone / "notes.txt").write_text("mine")
    assert updates.why_off() == ""


def test_off_with_another_origin(repos, monkeypatch):
    monkeypatch.setattr(updates, "_is_repository", IS_REPOSITORY)  # the origin is a folder
    assert "origin isn't" in updates.why_off()


@pytest.mark.parametrize("url, expected", [
    ("https://github.com/linlin56/mining-cat.git", True),
    ("https://github.com/linlin56/mining-cat", True),
    ("git@github.com:linlin56/mining-cat.git", True),
    ("https://github.com/someone/mining-cat.git", False),
    ("https://github.com/linlin56/mining-cat-fork.git", False),
    ("https://evilgithub.com/linlin56/mining-cat", False),
    ("https://example.com/github.com/linlin56/mining-cat", False),
])
def test_is_repository(url, expected):
    assert IS_REPOSITORY(url) is expected


def test_update_fast_forwards_then_installs_with_the_new_code(repos, github, processes):
    origin, clone = repos
    old = git(clone, "rev-parse", "HEAD")
    github.passing = commit(origin, "a.txt")
    result = updates.update(updates.check())
    assert git(clone, "rev-parse", "HEAD") == github.passing
    assert result == updates.UpdateResult(commits=1, returncode=0)
    # What to install: the new process decides, with the new code
    assert processes[0] == [[updates.PYTHON, "-m", "miningcat.infrastructure.system.updates", old]]


def test_update_moved_the_code_even_when_the_install_cannot_start(repos, github, monkeypatch):
    origin, clone = repos
    github.passing = commit(origin, "a.txt")
    check = updates.check()
    run = subprocess.run

    def no_python(command, *args, **kwargs):
        if command[0] == "git":
            return run(command, *args, **kwargs)
        raise FileNotFoundError(command[0])

    monkeypatch.setattr(updates.subprocess, "run", no_python)
    assert updates.update(check).returncode == 1
    assert git(clone, "rev-parse", "HEAD") == github.passing


def test_git_too_slow_or_missing_is_an_update_error(repos, monkeypatch):
    def slow(command, *args, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(updates.subprocess, "run", slow)
    with pytest.raises(updates.UpdateError, match="took more than"):
        updates._git_out("merge", "x", timeout=60)
    assert "took more than" in updates.check().error

    def missing(command, *args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(updates.subprocess, "run", missing)
    with pytest.raises(updates.UpdateError, match="can't run"):
        updates._git_out("status")


def test_install_since_an_unknown_commit(repos, processes):
    assert updates.install_since("0" * 40) == 1
    assert processes[0] == []


def test_update_tells_when_the_install_failed(repos, github, processes):
    origin, _ = repos
    github.passing = commit(origin, "requirements.txt", "flask\nnumpy\n")
    processes[1].append(1)
    assert updates.update(updates.check()).returncode == 1


def test_update_refuses_when_there_is_none(repos):
    with pytest.raises(updates.UpdateError, match="up to date"):
        updates.update(updates.check())


def test_update_refuses_when_the_code_changed_since_the_check(repos, github):
    origin, clone = repos
    github.passing = commit(origin, "a.txt")
    check = updates.check()
    commit(clone, "mine.txt")
    with pytest.raises(updates.UpdateError, match="changed since the check"):
        updates.update(check)
    assert (clone / "mine.txt").exists() and not (clone / "a.txt").exists()


def test_install_since_runs_the_commands_until_one_fails(repos, github, processes, monkeypatch):
    origin, clone = repos
    old = git(clone, "rev-parse", "HEAD")
    commit(origin, "requirements.txt", "flask\nnumpy\n")
    git(clone, "pull", "--quiet")
    calls, returncodes = processes
    assert updates.install_since(old) == 0
    assert calls == install_commands({"requirements.txt"})
    calls.clear()
    returncodes.append(2)
    assert updates.install_since(old) == 2 and len(calls) == 1


class Installed(set):
    """A set with the classes of the translation engines (`classes`)."""


@pytest.fixture
def engines(monkeypatch):
    """The optional engines installed: speech ones (engine_install's names), translation ones (their classes)."""
    from miningcat.infrastructure.translation.nllb import Nllb
    from miningcat.infrastructure.translation.qwen3 import Qwen3

    installed = Installed()
    monkeypatch.setattr(engine_install, "installed", lambda engines: engines in installed)
    for engine in (Nllb, Qwen3):
        monkeypatch.setattr(engine, "available", staticmethod(lambda engine=engine: engine in installed))
    installed.classes = SimpleNamespace(Nllb=Nllb, Qwen3=Qwen3)
    return installed


def install_commands(changed):
    return updates.miningcat_commands(changed) + updates.engine_commands(changed)


def pip_r(requirements):
    return [updates.PYTHON, "-m", "pip", "install", "-r", str(updates.PROJECT_ROOT / requirements)]


def test_install_commands_of_miningcat_with_pytorch_cpu(engines, monkeypatch):
    monkeypatch.setattr(updates.pip, "cpu_pytorch", lambda: True)  # Linux without an NVIDIA GPU, as make install
    assert install_commands({"requirements.txt"})[0] == [
        updates.PYTHON, "-m", "pip", "install", "torch", "torchaudio", "torchvision", "--index-url",
        updates.pip.PYTORCH_CPU_INDEX]


def test_install_commands_of_miningcat(engines, monkeypatch):
    monkeypatch.setattr(updates.pip, "cpu_pytorch", lambda: False)
    assert install_commands(set()) == []
    assert install_commands({"README.md", "src/miningcat/x.py"}) == []
    expected = [pip_r("requirements.txt"), [updates.PYTHON, "-m", "pip", "install", "--no-deps", "owocr>=1.26.8"]]
    assert install_commands({"requirements.txt"}) == expected
    assert install_commands({"Makefile"}) == expected


def test_install_commands_of_the_installed_engines_only(engines):
    qwen = engine_install.commands(engine_install.QWEN)
    assert install_commands({"requirements-qwen.txt", "requirements-omnivoice.txt"}) == []
    engines.add(engine_install.QWEN)
    assert install_commands({"requirements-qwen.txt"}) == qwen
    assert install_commands({updates.ENGINE_INSTALL}) == qwen
    assert install_commands({"requirements-taigi.txt"}) == []
    engines.add(engine_install.TAIGI)
    assert install_commands({"requirements-taigi.txt"}) == engine_install.commands(engine_install.TAIGI)
    engines.add(engine_install.OMNIVOICE)
    assert install_commands({"requirements-omnivoice.txt"}) == engine_install.commands(engine_install.OMNIVOICE)


def test_install_commands_of_the_translation_engines(engines):
    assert install_commands({"requirements-nllb.txt", "requirements-qwen.txt"}) == []
    engines.add(engines.classes.Nllb)
    assert install_commands({updates.TRANSLATION_INSTALL}) == [pip_r("requirements-nllb.txt")]  # how they install
    engines.discard(engines.classes.Nllb)
    engines.add(engines.classes.Nllb)
    assert install_commands({"requirements-nllb.txt", "requirements-qwen.txt"}) == [pip_r("requirements-nllb.txt")]
    # Qwen3 without Qwen3-ASR
    engines.add(engines.classes.Qwen3)
    assert install_commands({"requirements-qwen.txt"}) == [pip_r("requirements-qwen.txt")]
    # With it: its packages once
    engines.add(engine_install.QWEN)
    assert install_commands({"requirements-qwen.txt"}) == engine_install.commands(engine_install.QWEN)


def test_a_change_to_the_makefile_without_the_install_installs_nothing(repos, processes):
    origin, clone = repos
    old = git(clone, "rev-parse", "HEAD")
    commit(origin, "Makefile", "gui:\n\t$(WEB)\n")
    git(clone, "pull", "--quiet")
    assert updates._changed_since(old) == set()
    commit(origin, "Makefile", "gui:\n\t$(WEB)\ninstall:\n\t$(PYTHON) -m pip install -r requirements.txt\n")
    git(clone, "pull", "--quiet")
    assert updates._changed_since(old) == {"Makefile"}


def test_a_passing_commit_unknown_to_git_is_an_error(repos, github):
    github.passing = "f" * 40  # main rewritten since its CI ran
    check = updates.check()
    assert not check.available and "can't compare" in check.error


def test_update_without_install(repos, github, processes):
    origin, clone = repos
    github.passing = commit(origin, "requirements.txt", "flask\nnumpy\n")
    assert updates.update(updates.check(), install=False) == updates.UpdateResult(1, 0)
    assert git(clone, "rev-parse", "HEAD") == github.passing and processes[0] == []


def test_a_change_to_engine_install_without_its_requirements_installs_nothing(repos, processes, engines):
    origin, clone = repos
    engines.add(engine_install.QWEN)
    old = git(clone, "rev-parse", "HEAD")
    (origin / "src/miningcat/infrastructure/speech").mkdir(parents=True)
    commit(origin, updates.ENGINE_INSTALL, 'QWEN_ASR_REQUIREMENT = "qwen-asr==0.0.6"\n')
    git(clone, "pull", "--quiet")
    assert updates._changed_since(old) == {updates.ENGINE_INSTALL}  # a new requirement
    old = git(clone, "rev-parse", "HEAD")
    commit(origin, updates.ENGINE_INSTALL, '# The engines\nQWEN_ASR_REQUIREMENT = "qwen-asr==0.0.6"\n')
    git(clone, "pull", "--quiet")
    assert updates._changed_since(old) == set()  # a comment
    assert updates.install_since(old) == 0 and processes[0] == []


def test_miningcat_packages_are_installed_before_the_engines_are_imported(repos, processes, monkeypatch):
    origin, clone = repos
    old = git(clone, "rev-parse", "HEAD")
    commit(origin, "requirements.txt", "flask\nnumpy\n")
    git(clone, "pull", "--quiet")
    monkeypatch.setattr(updates.pip, "cpu_pytorch", lambda: False)  # not Linux without a GPU: 2 commands
    order = []
    monkeypatch.setattr(updates, "engine_commands", lambda changed: order.append("engines") or [])
    calls, _ = processes
    assert updates.install_since(old) == 0
    assert len(calls) == 2 and order == ["engines"]
    # Not when MiningCat's failed
    calls.clear(), order.clear()
    processes[1].append(1)
    assert updates.install_since(old) == 1 and order == []
