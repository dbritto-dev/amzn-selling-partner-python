# Built-in packages
import typing as t

# Third-party packages
import nox

nox.options.sessions = ["lint", "test", "security_test"]


def get_test_files(session: nox.Session) -> t.List[str]:
    test_files = session.posargs or ["."]
    return test_files


def get_lint_files(session: nox.Session) -> t.List[str]:
    lint_files = session.posargs or ["."]
    return lint_files


def get_lint_staged_files(session: nox.Session) -> t.List[str]:
    git_command_output: str = session.run(
        "git",
        "diff",
        "--name-only",
        "--cached",
        "--",
        "*.py",
        "**/*.py",
        external=True,
        silent=True,
    ).strip()  # type: ignore
    lint_staged_files = git_command_output.split("\n") if git_command_output else []
    return lint_staged_files


@nox.session
def test(session: nox.Session) -> None:
    test_files = get_test_files(session)

    session.install(".[test]")
    session.run("pytest", *test_files)


@nox.session
def coverage(session: nox.Session) -> None:
    session.install(".[test]")
    session.run("pytest", "--cov", "--cov-report=html")


@nox.session
def lint(session: nox.Session) -> None:
    lint_files = get_lint_files(session)

    session.install(".[lint]")
    session.run("ruff", *lint_files)
    session.run("black", "--check", *lint_files)


@nox.session
def lint_staged(session: nox.Session) -> None:
    lint_staged_files = get_lint_staged_files(session)

    if lint_staged_files:
        session.install(".[lint]")
        session.run("ruff", *lint_staged_files)
        session.run("black", "--check", *lint_staged_files)


@nox.session
def security_test(session: nox.Session) -> None:
    session.install(".[security-test]")
    session.run("bandit", "-r", "app/")
    session.run("safety", "check")
