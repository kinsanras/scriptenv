"""Implementation of scriptenv.requires"""
import hashlib
import io
import json
import re
import sys
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from typing import Callable, Generator

import appdirs
from pip._internal.commands import create_command


def requires(*requirements: str) -> None:
    """Makes each requirements available to import.

    Installs each requirement and dependency to a seperate directory
    and adds each directory to the front of sys.path

    Arguments:
        requirements: List of pip requirements required to be installed.
    """
    base_path = Path(appdirs.user_cache_dir(__name__)).absolute()
    download_path = base_path / "download"
    install_path = base_path / "install"
    dependencies_path = base_path / "dependencies"
    dependencies_path.mkdir(parents=True, exist_ok=True)

    requirements_hash = hashlib.md5(
        "\n".join(sorted(requirements)).encode("utf-8")
    ).hexdigest()
    requirements_list_path = dependencies_path / requirements_hash

    if not requirements_list_path.exists():
        stdout = _pip("download", "--dest", str(download_path), *requirements)
        packages = {
            match.group("pkg")
            for match in re.finditer(
                r"(/|\\)(?P<pkg>[^(/|\\)]+?(\.tar\.gz|\.whl))", stdout
            )
        }
        requirements_list_path.write_text(json.dumps(list(packages)))
    else:
        packages = set(json.loads(requirements_list_path.read_text()))

    for package in packages:
        package_install_path = install_path / package
        if not package_install_path.exists():
            _pip(
                "install",
                "--no-deps",
                "--no-user",
                "--target",
                str(package_install_path),
                str(download_path / package),
            )
        sys.path[0:0] = [str(package_install_path)]


def _pip(command: str, *args: str) -> str:
    with _redirect_stdout() as get_stdout:
        create_command(command).main(list(args))
    return get_stdout()


@contextmanager
def _redirect_stdout() -> Generator[Callable[[], str], None, None]:
    """Redirects stdout with a workaround for https://bugs.python.org/issue44666"""
    stdout = io.BytesIO()
    encoding = sys.stdout.encoding
    wrapper = io.TextIOWrapper(
        stdout,
        encoding=encoding,
    )
    with redirect_stdout(wrapper):
        yield lambda: stdout.getvalue().decode(encoding)