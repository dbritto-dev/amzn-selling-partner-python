"""nox sessions: ``uv run nox -s lint|type_check|test|security_test|codegen|bench``."""

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
    session.run("pyright")


@nox.session
def security_test(session: nox.Session) -> None:
    """bandit over the package (generated code included) and safety over the locked dependencies."""
    session.install(".[security-test]")
    session.run("bandit", "-q", "-r", "src/amzn_selling_partner/")
    # SFTY-20260721-58460 flags every setuptools release below 83.0.0, but 83+ removed
    # `pkg_resources`, which safety==2.3.4 itself still requires to run. setuptools is a
    # dev-only build tool here (not a runtime dependency of the published package), so the
    # finding is ignored until safety can run without pkg_resources.
    session.run("safety", "check", "--ignore", "SFTY-20260721-58460")


@nox.session
def codegen(session: nox.Session) -> None:
    """Regenerate src/amzn_selling_partner/sdk and tests/petstore_sdk with oagen (needs Node 24)."""
    session.install("-e", ".[dev]")
    session.chdir("codegen")
    session.run("npm", "ci", "--ignore-scripts", external=True, silent=True)
    session.run("npm", "run", "regenerate", external=True)


@nox.session
def bench(session: nox.Session) -> None:
    session.install("-e", ".[dev,aiohttp]")
    session.run("pytest", "benchmarks", *session.posargs)
