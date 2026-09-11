"""nox sessions: ``uv run nox -s lint|type_check|test|stubs|bench``."""

import nox

nox.options.default_venv_backend = "uv"
nox.options.sessions = ["lint", "type_check", "test", "stubs"]


@nox.session
def test(session: nox.Session) -> None:
    session.install("-e", ".[dev,aiohttp]")
    session.run("pytest", *(session.posargs or ["-q"]))


@nox.session
def lint(session: nox.Session) -> None:
    session.install("ruff")
    session.run("ruff", "check", "src", "tests", "benchmarks", "scripts")
    session.run("ruff", "format", "--check", "src", "tests", "benchmarks", "scripts")


@nox.session
def type_check(session: nox.Session) -> None:
    session.install("-e", ".[dev,aiohttp]")
    session.run("pyright")


@nox.session
def stubs(session: nox.Session) -> None:
    session.install("-e", ".[dev]")
    session.run("python", "-m", "amzn_selling_partner.stubgen", "--check")


@nox.session
def bench(session: nox.Session) -> None:
    session.install("-e", ".[dev,aiohttp]")
    session.run("python", "benchmarks/bench.py", *session.posargs)
