# pylint: disable=missing-module-docstring,missing-function-docstring,unused-argument,redefined-outer-name

import os
from pathlib import Path
from typing import Callable, Dict, Generator, List, cast
from uuid import uuid4 as uuid

import pytest
from _pytest.fixtures import FixtureRequest
from _pytest.monkeypatch import MonkeyPatch
from pytest_git import GitRepo

from release import changelog, check_commit_messages, version

CommitFactory = Callable[[List[str]], List[str]]
TagFactory = Callable[[Dict[str, str]], None]


@pytest.fixture(autouse=True)
def in_git_repo(
    request: FixtureRequest, git_repo: GitRepo
) -> Generator[GitRepo, None, None]:
    os.chdir(git_repo.workspace)
    yield git_repo
    os.chdir(request.config.invocation_dir)


@pytest.fixture(autouse=True)
def setup_git_repo(in_git_repo: GitRepo) -> None:
    in_git_repo.run("git config user.name pytest")
    in_git_repo.run("git config user.email pytest@example.com")


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_REF", raising=False)


@pytest.fixture
def commit_factory(git_repo: GitRepo) -> CommitFactory:
    def _commit_factory(commits: List[str]) -> List[str]:
        for commit in commits:
            new_file_name = uuid().hex
            Path(git_repo.workspace, new_file_name).write_text("")
            git_repo.run(f"git add {new_file_name}", capture=True)
            git_repo.run(f'git commit -m"{commit}"', capture=True)
        return list(
            reversed(
                cast(
                    str,
                    git_repo.run(
                        f'git log --pretty="%H" -n{len(commits)}', capture=True
                    ),
                )
                .strip()
                .split("\n")
            )
        )

    return _commit_factory


@pytest.fixture
def tag_factory(git_repo: GitRepo) -> TagFactory:
    def _tag_factory(tags: Dict[str, str]) -> None:
        for tag, commit in tags.items():
            git_repo.run(f"git tag {tag} {commit}", capture=True)

    return _tag_factory


@pytest.mark.parametrize(
    "allowed_keyword", ["internal", "bugfix", "feature", "internal", "tooling"]
)
def test_check_valid_commit_message(
    allowed_keyword: str, commit_factory: CommitFactory
) -> None:
    commit_factory([f"[{allowed_keyword}] message"])
    assert list(check_commit_messages()) == []


@pytest.mark.parametrize("message", ["no prefix"])
def test_check_invalid_commit_message(
    message: str, commit_factory: CommitFactory
) -> None:
    commit_factory([message])
    error_messages = check_commit_messages()
    assert next(error_messages) == f"Invalid commit message: {message}"
    with pytest.raises(SystemExit):
        next(error_messages)


def test_changelog(commit_factory: CommitFactory) -> None:
    commit_factory(
        [
            "[internal] internal",
            "[bugfix] bugfix",
            "[feature] feature",
            "[tooling] hidden",
        ]
    )
    assert list(changelog()) == [
        "* Features",
        "  * feature",
        "* Bugfixes",
        "  * bugfix",
        "* Internal",
        "  * internal",
    ]


def test_changelog_in_commit_order(commit_factory: CommitFactory) -> None:
    commit_factory(
        [
            "[feature] feature0",
            "[feature] feature1",
        ]
    )
    assert list(changelog()) == [
        "* Features",
        "  * feature0",
        "  * feature1",
    ]


def test_changelog_omit_empty_categories(commit_factory: CommitFactory) -> None:
    commit_factory(["[feature] feature"])
    assert list(changelog()) == [
        "* Features",
        "  * feature",
    ]


def test_changelog_since_last_version_by_default(
    commit_factory: CommitFactory, tag_factory: TagFactory
) -> None:
    commit_hashes = commit_factory(["[feature] feature0", "[feature] feature1"])
    tag_factory({"v0.1.0": commit_hashes[0]})

    assert list(changelog()) == [
        "* Features",
        "  * feature1",
    ]


def test_version_initial(commit_factory: CommitFactory) -> None:
    commit_hashes = commit_factory(["[feature] first"])
    last_commit_hash_short = commit_hashes[-1][:7]
    assert version() == f"0.1.0+{last_commit_hash_short}"


def test_version_next_release(
    commit_factory: CommitFactory, tag_factory: TagFactory, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_REF", "refs/tags/release-candidate")
    commit_factory(["[feature] first"])
    assert version() == "0.1.0"


def test_version_next_minor(
    commit_factory: CommitFactory, tag_factory: TagFactory
) -> None:
    commit_hashes = commit_factory(["[feature] initial", "[feature] next"])
    tag_factory({"v0.1.0": commit_hashes[0]})
    assert version() == f"0.2.0+{commit_hashes[-1][:7]}"


def test_version_next_patch(
    commit_factory: CommitFactory, tag_factory: TagFactory
) -> None:
    commit_hashes = commit_factory(["[feature] initial", "[bugfix] next"])
    tag_factory({"v0.1.0": commit_hashes[0]})
    assert version() == f"0.1.1+{commit_hashes[-1][:7]}"
