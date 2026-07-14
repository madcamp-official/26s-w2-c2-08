"""Reusable external-provider fakes for backend tests."""

from urllib.parse import urlencode

from tbd.providers.google_oidc import GoogleIdentity, OIDCProviderUnavailable


class FakeGoogleOIDCProvider:
    """Network-free Google provider with observable PKCE inputs."""

    def __init__(self) -> None:
        self.identity = GoogleIdentity(
            subject="google-subject-1",
            nonce="",
            display_name="테스트 사용자",
            email="student@example.test",
            avatar_url="https://example.test/avatar.png",
        )
        self.authorization_requests: list[dict[str, str]] = []
        self.exchange_requests: list[dict[str, str]] = []
        self.unavailable = False

    def authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str:
        request = {"state": state, "nonce": nonce, "code_challenge": code_challenge}
        self.authorization_requests.append(request)
        self.identity = GoogleIdentity(
            subject=self.identity.subject,
            nonce=nonce,
            display_name=self.identity.display_name,
            email=self.identity.email,
            avatar_url=self.identity.avatar_url,
        )
        return f"https://provider.test/authorize?{urlencode(request)}"

    async def exchange_code(self, *, code: str, code_verifier: str) -> GoogleIdentity:
        self.exchange_requests.append({"code": code, "code_verifier": code_verifier})
        if self.unavailable:
            raise OIDCProviderUnavailable
        return self.identity
