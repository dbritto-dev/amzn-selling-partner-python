"""nox sessions: ``uv run nox -s lint|type_check|test|codegen|bench``."""

import nox

nox.options.default_venv_backend = "uv"
nox.options.sessions = ["lint", "type_check", "test"]


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
    session.run("pyright")


@nox.session
def codegen(session: nox.Session) -> None:
    """Regenerate src/amzn_selling_partner/sdk and tests/petstore_sdk with oagen (needs Node 22)."""
    session.install("-e", ".[dev]")
    session.chdir("codegen")
    session.run("npm", "ci", "--ignore-scripts", external=True, silent=True)
    session.run("npm", "run", "regenerate", external=True)


@nox.session
def bench(session: nox.Session) -> None:
    session.install("-e", ".[dev,aiohttp]")
    session.run("pytest", "benchmarks", *session.posargs)
