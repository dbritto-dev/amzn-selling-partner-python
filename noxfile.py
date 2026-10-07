"""nox sessions: ``uv run nox -s lint|type_check|test|security_test``."""

import nox

nox.options.default_venv_backend = "uv"
nox.options.sessions = ["lint", "type_check", "test", "security_test"]


@nox.session
def test(session: nox.Session) -> None:
    session.install("-e", ".[dev,aiohttp]")
    session.run("pytest", *(session.posargs or ["-q"]))


@nox.session
def lint(session: nox.Session) -> None:
    session.install("ruff")
    session.run("ruff", "check", "src", "tests", "benchmarks")
    session.run("ruff", "format", "--check", "src", "tests", "benchmarks")


@nox.session
def type_check(session: nox.Session) -> None:
    session.install("-e", ".[dev,aiohttp]")
    session.run("ty", "check")


@nox.session
def security_test(session: nox.Session) -> None:
    """bandit over the package (generated code included) and uv audit over locked dependencies."""
    session.install(".[security-test]")
    session.run("bandit", "-q", "-r", "src/amzn_selling_partner/")
    session.run("uv", "audit", "--locked")
