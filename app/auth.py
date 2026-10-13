from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import jwt
from agno.os import AgentOS
from agno.os.middleware.jwt import AuthMiddleware, JWTValidator
from agno.os.scopes import AgentOSScope
from agno.os.service_accounts import DEFAULT_SERVICE_ACCOUNT_SCOPES
from agno.utils.log import log_warning
from fastapi import FastAPI
from fastmcp.server.auth import AccessToken
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.auth.providers.workos import AuthKitProvider

# The claim AuthMiddleware reads as the user id. A WorkOS `sub` is "user_01...", never the
# email, so the validator writes the email here and the middleware is pointed at this claim.
UID_CLAIM = "uid"

# Routes AgentOS leaves public; repeated here because our middleware replaces its exclusion list.
PUBLIC_ROUTES = ["/", "/health", "/info", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"]


@dataclass(frozen=True)
class WorkOSConfig:
    client_id: str
    authkit_domain: str | None = None  # https://<name>.authkit.app, needed for MCP only
    org_id: str | None = None  # when set, only tokens for this organization are accepted
    allowed_email_domains: tuple[str, ...] = ()  # when set, only these email domains are accepted
    issuers: tuple[str, ...] = ("https://api.workos.com",)  # add your custom auth domain if you have one

    @property
    def jwks_url(self) -> str:
        return f"https://api.workos.com/sso/jwks/{self.client_id}"


@dataclass(frozen=True)
class Identity:
    user_id: str
    scopes: list[str]


def identity_from_claims(claims: dict[str, Any], config: WorkOSConfig) -> Identity:
    """Map verified WorkOS claims to (email, scopes). Raises InvalidTokenError to reject.

    Never falls back to `sub`: a token without an email would silently fork the user's history.
    """
    email = claims.get("email")
    local, _, domain = email.strip().lower().rpartition("@") if isinstance(email, str) else ("", "", "")
    if not local or not domain:
        raise jwt.InvalidTokenError("token has no email claim; add it to the WorkOS JWT template")
    if claims.get("email_verified") is False:
        raise jwt.InvalidTokenError("email is not verified")
    if config.org_id and claims.get("org_id") != config.org_id:
        raise jwt.InvalidTokenError("token is not for the allowed organization")
    allowed = {d.lower().lstrip("@") for d in config.allowed_email_domains}
    if allowed and domain not in allowed:
        raise jwt.InvalidTokenError("email domain is not allowed")

    # Same scopes a service-account token gets by default; WorkOS admins also get agno admin.
    scopes = list(DEFAULT_SERVICE_ACCOUNT_SCOPES)
    if claims.get("role") == "admin":
        scopes.append(AgentOSScope.ADMIN.value)
    return Identity(user_id=f"{local}@{domain}", scopes=scopes)


def _normalize_issuer(value: Any) -> str:
    return value.rstrip("/") if isinstance(value, str) else ""


class WorkOSJWTValidator(JWTValidator):
    """Verifies WorkOS session tokens against WorkOS's JWKS; every other token goes to the wrapped validator.

    Built from the validator AuthMiddleware already created, so the keys you configure for AgentOS
    (JWT_VERIFICATION_KEY / JWT_JWKS_FILE, e.g. os.agno.com tokens) keep working unchanged.
    """

    def __init__(self, config: WorkOSConfig, base: JWTValidator) -> None:
        # No super().__init__: it would demand a key source again. Share the base validator's keys and claim names.
        self.__dict__.update(base.__dict__)
        self.user_id_claim = UID_CLAIM
        self._config = config
        self._issuers = {_normalize_issuer(issuer) for issuer in config.issuers}
        # cache_keys avoids re-reading the JWKS per request; the timeout stops a WorkOS outage hanging requests.
        self._jwks = jwt.PyJWKClient(config.jwks_url, cache_keys=True, timeout=5)

    def validate_token(self, token: str, expected_audience: str | Iterable[str] | None = None) -> dict[str, Any]:
        # `iss` is read unverified only to pick which keys check the token; the signature is verified either way.
        issuer = _normalize_issuer(jwt.decode(token, options={"verify_signature": False}).get("iss"))
        if issuer not in self._issuers:
            payload = super().validate_token(token, expected_audience)
            payload[UID_CLAIM] = payload.get("sub")  # non-WorkOS tokens keep their own identity
            return payload

        try:
            key = self._jwks.get_signing_key_from_jwt(token).key
        except jwt.PyJWKClientError as e:
            raise jwt.InvalidTokenError(f"cannot load the WorkOS signing key: {e}") from e
        # Session tokens carry no `aud`, so audience is not checked here.
        payload = jwt.decode(
            token,
            key,
            algorithms=[self.algorithm],
            leeway=self.leeway,
            options={"require": ["exp", "sub"], "verify_aud": False},
        )
        identity: Identity = identity_from_claims(payload, self._config)
        payload[UID_CLAIM] = identity.user_id
        payload[self.scopes_claim] = identity.scopes
        return payload


class WorkOSAuthMiddleware(AuthMiddleware):
    """AuthMiddleware that takes the user id from the WorkOS token's email."""

    def __init__(self, app: Any, *, workos: WorkOSConfig, **kwargs: Any) -> None:
        kwargs["user_id_claim"] = UID_CLAIM
        super().__init__(app, **kwargs)
        if self.validator is None or not self.validate:
            raise ValueError("WorkOS auth needs signature validation: set JWT_VERIFICATION_KEY or JWT_JWKS_FILE")
        self.validator = WorkOSJWTValidator(workos, self.validator)


def install_workos_auth(app: FastAPI, agent_os: AgentOS, config: WorkOSConfig) -> None:
    """Add WorkOS token auth as the outermost layer for REST, AG-UI and A2A.

    Call right after `app = agent_os.get_app()`, and only when auth is on (not RUNTIME_ENV=dev).
    AgentOS's own layer stays behind it as the fail-closed backstop.
    """
    # Chat interfaces that verify their own requests (Slack signing secret, ...) must bypass this
    # layer, or their webhooks would 401 for lack of a Bearer token. Same rule AgentOS applies.
    own_auth = [
        f"{interface.prefix}/*"
        for interface in agent_os.interfaces
        if getattr(interface, "authenticates_own_requests", False) and getattr(interface, "prefix", None)
    ]
    middleware_kwargs: dict[str, Any] = {
        "workos": config,
        "authorization": True,
        "user_isolation": True,
        "service_account_verifier": getattr(app.state, "service_account_verifier", None),
        "excluded_route_paths": [*PUBLIC_ROUTES, *own_auth, *agent_os.mcp_auth_exempt_paths()],
    }
    # Starlette's add_middleware typing rejects any subclass that adds a constructor parameter.
    app.add_middleware(WorkOSAuthMiddleware, **middleware_kwargs)  # type: ignore[arg-type]


class EmailJWTVerifier(JWTVerifier):
    """Verifies AuthKit OAuth tokens for /mcp and makes the email the user id."""

    def __init__(self, config: WorkOSConfig, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._config = config

    async def verify_token(self, token: str) -> AccessToken | None:
        access_token = await super().verify_token(token)
        if access_token is None:
            return None
        try:
            identity = identity_from_claims(access_token.claims, self._config)
        except jwt.InvalidTokenError as e:
            log_warning(f"Rejected AuthKit MCP token: {e}")
            return None
        return access_token.model_copy(
            update={"scopes": identity.scopes, "claims": {**access_token.claims, "sub": identity.user_id}}
        )


def workos_mcp_auth(config: WorkOSConfig, public_url: str) -> AuthKitProvider:
    """The `mcp_auth` provider: WorkOS AuthKit does the login, this app only verifies the token.

    `public_url` must be the exact public origin and match the Resource Indicator in WorkOS
    (`<public_url>/mcp`), or the audience check fails.
    """
    if not config.authkit_domain:
        raise ValueError("authkit_domain is required for MCP auth")
    domain = config.authkit_domain.rstrip("/")
    origin = public_url.rstrip("/")
    verifier = EmailJWTVerifier(
        config,
        jwks_uri=f"{domain}/oauth2/jwks",
        issuer=domain,
        audience=f"{origin}/mcp",
        algorithm="RS256",
    )
    return AuthKitProvider(authkit_domain=domain, base_url=origin, token_verifier=verifier)
