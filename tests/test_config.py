"""Configuration tests.

The database URL rewrite is the one piece of config that can only fail in production -
locally everything is SQLite - so it is worth pinning down with tests rather than
discovering it in a deploy log.
"""

import pytest

from mastery.common.config import Settings


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        # What managed Postgres providers actually hand out.
        (
            "postgres://user:pw@host:5432/db",
            "postgresql+asyncpg://user:pw@host:5432/db",
        ),
        (
            "postgresql://user:pw@host:5432/db",
            "postgresql+asyncpg://user:pw@host:5432/db",
        ),
        # Already async, or not Postgres at all: left alone.
        (
            "postgresql+asyncpg://user:pw@host:5432/db",
            "postgresql+asyncpg://user:pw@host:5432/db",
        ),
        ("sqlite+aiosqlite:///./mastery.db", "sqlite+aiosqlite:///./mastery.db"),
    ],
)
def test_database_url_is_normalised_to_an_async_driver(given: str, expected: str) -> None:
    assert Settings(database_url=given).database_url == expected


def test_password_in_the_url_survives_the_rewrite() -> None:
    """Only the scheme is replaced - credentials and query string must be untouched."""
    url = "postgres://u:p%40ss@host:5432/db?sslmode=require"
    assert (
        Settings(database_url=url).database_url
        == "postgresql+asyncpg://u:p%40ss@host:5432/db?sslmode=require"
    )


def test_cors_origins_are_split_and_trimmed() -> None:
    settings = Settings(cors_origins=" https://a.example , https://b.example ,, ")
    assert settings.cors_origin_list == ["https://a.example", "https://b.example"]


def test_is_production_recognises_both_spellings() -> None:
    assert Settings(app_env="production").is_production
    assert Settings(app_env="PROD").is_production
    assert not Settings(app_env="development").is_production
