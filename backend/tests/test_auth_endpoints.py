"""PostgreSQL-backed security tests for OAuth callback and server sessions."""

from dataclasses import replace

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from fakes import FakeGoogleOIDCProvider
from tbd.app import create_app
from tbd.auth.security import AuthCrypto
from tbd.core.config import AppEnvironment, Settings
from tbd.db import create_database

pytestmark = pytest.mark.integration


def _settings(database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=database_url,
        auth_secret_key="test-auth-secret-that-is-longer-than-thirty-two-bytes",
        frontend_origin="http://localhost:5173",
        auth_allowed_origins="http://localhost:5173",
    )


def _sync_dsn(database_url: str) -> str:
    return make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)


def _client(database_url: str) -> tuple[TestClient, FakeGoogleOIDCProvider, Settings]:
    settings = _settings(database_url)
    provider = FakeGoogleOIDCProvider()
    app = create_app(
        settings=settings,
        database=create_database(settings),
        google_oidc_provider=provider,
    )
    return TestClient(app, base_url="https://testserver"), provider, settings


def _start(client: TestClient, provider: FakeGoogleOIDCProvider, return_to: str = "/") -> str:
    response = client.get(
        "/api/v1/auth/google/start",
        params={"return_to": return_to},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["location"].startswith("https://provider.test/authorize?")
    assert "goal_oauth=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "Secure" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    return provider.authorization_requests[-1]["state"]


def _complete(client: TestClient, state: str, code: str = "valid-code"):
    return client.get(
        "/api/v1/auth/google/callback",
        params={"state": state, "code": code},
        follow_redirects=False,
    )


def test_callback_issues_hashed_session_and_restores_route(
    migrated_database_url: str,
) -> None:
    """A verified identity becomes an opaque cookie and the requested frontend route."""

    client, provider, _ = _client(migrated_database_url)
    with client:
        state = _start(client, provider, "/account?tab=security")
        response = _complete(client, state)

        assert response.status_code == 302
        assert response.headers["location"] == "http://localhost:5173/account?tab=security"
        assert "goal_session=" in response.headers.get_list("set-cookie")[-1]
        token = client.cookies.get("goal_session")
        assert token is not None
        request = provider.authorization_requests[-1]
        exchange = provider.exchange_requests[-1]
        assert AuthCrypto.pkce_challenge(exchange["code_verifier"]) == request["code_challenge"]

        with psycopg.connect(_sync_dsn(migrated_database_url)) as connection:
            row = connection.execute("SELECT token_hash, revoked_at FROM auth_sessions").fetchone()
        assert row is not None
        assert row[0] != token.encode()
        assert row[1] is None


def test_second_login_rotates_existing_session(migrated_database_url: str) -> None:
    """A browser cannot carry a fixed pre-login session through a new callback."""

    client, provider, settings = _client(migrated_database_url)
    crypto = AuthCrypto(settings.auth_secret_key.get_secret_value())
    with client:
        first_state = _start(client, provider)
        assert _complete(client, first_state).status_code == 302
        first_token = client.cookies.get("goal_session")

        second_state = _start(client, provider)
        assert _complete(client, second_state).status_code == 302
        second_token = client.cookies.get("goal_session")

        assert first_token is not None
        assert second_token is not None
        assert second_token != first_token

        with psycopg.connect(_sync_dsn(migrated_database_url)) as connection:
            old_revoked_at = connection.execute(
                "SELECT revoked_at FROM auth_sessions WHERE token_hash = %s",
                (crypto.hash_token("session", first_token),),
            ).fetchone()
            new_revoked_at = connection.execute(
                "SELECT revoked_at FROM auth_sessions WHERE token_hash = %s",
                (crypto.hash_token("session", second_token),),
            ).fetchone()
        assert old_revoked_at is not None and old_revoked_at[0] is not None
        assert new_revoked_at is not None and new_revoked_at[0] is None


def test_logout_requires_exact_origin_and_is_idempotent(migrated_database_url: str) -> None:
    """CSRF-like logout requests fail while repeated trusted logout succeeds."""

    client, provider, _ = _client(migrated_database_url)
    with client:
        state = _start(client, provider)
        assert _complete(client, state).status_code == 302

        missing = client.post("/api/v1/auth/logout")
        wrong = client.post(
            "/api/v1/auth/logout",
            headers={"Origin": "http://localhost:5173.evil.example"},
        )
        first = client.post(
            "/api/v1/auth/logout",
            headers={"Origin": "http://localhost:5173"},
        )
        second = client.post(
            "/api/v1/auth/logout",
            headers={"Origin": "http://localhost:5173"},
        )

        assert missing.status_code == 403
        assert wrong.status_code == 403
        assert wrong.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"
        assert first.status_code == 204
        assert second.status_code == 204


def test_cancelled_consent_returns_safe_frontend_error(migrated_database_url: str) -> None:
    """Provider cancellation does not expose its raw error and preserves the route."""

    client, provider, _ = _client(migrated_database_url)
    with client:
        state = _start(client, provider, "/account")
        response = client.get(
            "/api/v1/auth/google/callback",
            params={"state": state, "error": "provider-private-error"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["location"] == (
            "http://localhost:5173/login?auth_error=cancelled&return_to=%2Faccount"
        )
        assert "provider-private-error" not in response.headers["location"]
        assert provider.exchange_requests == []


def test_provider_failure_is_sanitized_and_consumes_state(migrated_database_url: str) -> None:
    """A provider outage is safe to expose and cannot make the callback replayable."""

    client, provider, _ = _client(migrated_database_url)
    with client:
        state = _start(client, provider)
        provider.unavailable = True

        response = _complete(client, state, code="secret-provider-code")
        replay = _complete(client, state, code="secret-provider-code")

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
        assert "secret-provider-code" not in response.text
        assert replay.status_code == 400
        assert replay.json()["error"]["code"] == "INVALID_OAUTH_TRANSACTION"


def test_nonce_mismatch_rejects_session_issue(migrated_database_url: str) -> None:
    """A signed identity with a different nonce cannot create a GOAL session."""

    client, provider, _ = _client(migrated_database_url)
    with client:
        state = _start(client, provider)
        provider.identity = replace(provider.identity, nonce="wrong-nonce")

        response = _complete(client, state)

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_OAUTH_TRANSACTION"
        assert client.cookies.get("goal_session") is None


def test_expired_oauth_transaction_cannot_issue_session(
    migrated_database_url: str,
) -> None:
    """An expired browser transaction is rejected before provider exchange."""

    client, provider, _ = _client(migrated_database_url)
    with client:
        state = _start(client, provider)
        with psycopg.connect(_sync_dsn(migrated_database_url)) as connection:
            connection.execute(
                "UPDATE oauth_transactions "
                "SET created_at = now() - interval '11 minutes', "
                "expires_at = now() - interval '1 minute'"
            )
            connection.commit()

        response = _complete(client, state)

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_OAUTH_TRANSACTION"
        assert provider.exchange_requests == []
        assert client.cookies.get("goal_session") is None


def test_start_rejects_open_redirect(migrated_database_url: str) -> None:
    """An external return_to never reaches the provider."""

    client, provider, _ = _client(migrated_database_url)
    with client:
        response = client.get(
            "/api/v1/auth/google/start",
            params={"return_to": "https://evil.example/path"},
            follow_redirects=False,
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_RETURN_TO"
        assert provider.authorization_requests == []


def test_me_restores_current_user_and_distinguishes_missing_session(
    migrated_database_url: str,
) -> None:
    """The shared dependency returns a profile and stable missing-auth error."""

    client, provider, _ = _client(migrated_database_url)
    with client:
        missing = client.get("/api/v1/me")
        state = _start(client, provider)
        assert _complete(client, state).status_code == 302
        authenticated = client.get("/api/v1/me")

        assert missing.status_code == 401
        assert missing.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
        assert authenticated.status_code == 200
        assert authenticated.json() == {
            "id": authenticated.json()["id"],
            "display_name": "테스트 사용자",
            "email": "student@example.test",
            "avatar_url": "https://example.test/avatar.png",
        }


def test_rotated_session_cannot_authenticate(migrated_database_url: str) -> None:
    """The previous browser token becomes invalid immediately after callback rotation."""

    client, provider, _ = _client(migrated_database_url)
    with client:
        first_state = _start(client, provider)
        assert _complete(client, first_state).status_code == 302
        old_token = client.cookies.get("goal_session")
        second_state = _start(client, provider)
        assert _complete(client, second_state).status_code == 302

        assert old_token is not None
        client.cookies.set("goal_session", old_token, domain="testserver.local", path="/")
        response = client.get("/api/v1/me")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "INVALID_SESSION"


def test_expired_session_cannot_authenticate(migrated_database_url: str) -> None:
    """Absolute expiry invalidates the cookie even when the browser retains it."""

    client, provider, _ = _client(migrated_database_url)
    with client:
        state = _start(client, provider)
        assert _complete(client, state).status_code == 302

        with psycopg.connect(_sync_dsn(migrated_database_url)) as connection:
            connection.execute(
                "UPDATE auth_sessions "
                "SET created_at = now() - interval '8 days', "
                "expires_at = now() - interval '1 day'"
            )
            connection.commit()

        response = client.get("/api/v1/me")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "INVALID_SESSION"


def test_me_updates_last_seen_without_extending_expiry(migrated_database_url: str) -> None:
    """Activity tracking is throttled and cannot create a sliding session lifetime."""

    client, provider, settings = _client(migrated_database_url)
    crypto = AuthCrypto(settings.auth_secret_key.get_secret_value())
    with client:
        state = _start(client, provider)
        assert _complete(client, state).status_code == 302
        token = client.cookies.get("goal_session")
        assert token is not None
        token_hash = crypto.hash_token("session", token)

        with psycopg.connect(_sync_dsn(migrated_database_url)) as connection:
            before = connection.execute(
                "SELECT expires_at, last_seen_at FROM auth_sessions WHERE token_hash = %s",
                (token_hash,),
            ).fetchone()
            connection.execute(
                "UPDATE auth_sessions SET last_seen_at = now() - interval '10 minutes' "
                "WHERE token_hash = %s",
                (token_hash,),
            )
            connection.commit()

        assert client.get("/api/v1/me").status_code == 200

        with psycopg.connect(_sync_dsn(migrated_database_url)) as connection:
            after = connection.execute(
                "SELECT expires_at, last_seen_at FROM auth_sessions WHERE token_hash = %s",
                (token_hash,),
            ).fetchone()

        assert before is not None and after is not None
        assert after[0] == before[0]
        assert after[1] > before[1]


def test_email_registration_and_login_share_the_server_session_contract(
    migrated_database_url: str,
) -> None:
    """A local account can create Course-capable authentication without Google."""

    client, _, settings = _client(migrated_database_url)
    crypto = AuthCrypto(settings.auth_secret_key.get_secret_value())
    payload = {
        "display_name": "이메일 사용자",
        "email": "  STUDENT@Example.Test ",
        "password": "correct horse battery staple",
    }
    with client:
        forbidden = client.post("/api/v1/auth/email/register", json=payload)
        registered = client.post(
            "/api/v1/auth/email/register",
            json=payload,
            headers={"Origin": "http://localhost:5173"},
        )
        first_token = client.cookies.get("goal_session")

        assert forbidden.status_code == 403
        assert registered.status_code == 201
        assert registered.json()["user"] == {
            "id": registered.json()["user"]["id"],
            "display_name": "이메일 사용자",
            "email": "student@example.test",
            "avatar_url": None,
        }
        assert first_token is not None

        client.cookies.clear()
        failed = client.post(
            "/api/v1/auth/email/login",
            json={"email": "student@example.test", "password": "wrong password"},
            headers={"Origin": "http://localhost:5173"},
        )
        logged_in = client.post(
            "/api/v1/auth/email/login",
            json={"email": "STUDENT@example.test", "password": payload["password"]},
            headers={"Origin": "http://localhost:5173"},
        )
        second_token = client.cookies.get("goal_session")

        assert failed.status_code == 401
        assert failed.json()["error"]["code"] == "INVALID_CREDENTIALS"
        assert logged_in.status_code == 200
        assert second_token is not None and second_token != first_token
        assert client.get("/api/v1/me").status_code == 200

        with psycopg.connect(_sync_dsn(migrated_database_url)) as connection:
            password_hash = connection.execute(
                "SELECT password_hash FROM user_password_credentials"
            ).fetchone()
            token_hash = connection.execute(
                "SELECT token_hash FROM auth_sessions WHERE token_hash = %s",
                (crypto.hash_token("session", second_token),),
            ).fetchone()
        assert password_hash is not None
        assert payload["password"] not in password_hash[0]
        assert token_hash is not None


def test_email_registration_does_not_take_over_google_identity(
    migrated_database_url: str,
) -> None:
    """The same email cannot silently create a second login path or user account."""

    client, provider, _ = _client(migrated_database_url)
    payload = {
        "display_name": "이메일 사용자",
        "email": "student@example.test",
        "password": "correct horse battery staple",
    }
    with client:
        registered = client.post(
            "/api/v1/auth/email/register",
            json=payload,
            headers={"Origin": "http://localhost:5173"},
        )
        duplicate = client.post(
            "/api/v1/auth/email/register",
            json=payload,
            headers={"Origin": "http://localhost:5173"},
        )
        state = _start(client, provider)
        google_collision = _complete(client, state)

        assert registered.status_code == 201
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"
        assert google_collision.status_code == 409
        assert google_collision.json()["error"]["code"] == "IDENTITY_EMAIL_CONFLICT"
