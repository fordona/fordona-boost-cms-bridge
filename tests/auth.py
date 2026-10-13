"""RSA key pairs, a JWKS document, and a token factory for auth tests."""

import json
import time
from functools import cached_property
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

ISSUER = "https://fordona-test.kinde.com"
AUDIENCE = "https://api.fordona.test"
JWKS_URI = f"{ISSUER}/.well-known/jwks"


class SigningKey:
    def __init__(self, kid: str) -> None:
        self.kid = kid
        self.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    @cached_property
    def jwk(self) -> dict[str, Any]:
        jwk: dict[str, Any] = json.loads(RSAAlgorithm.to_jwk(self.private.public_key()))
        jwk.update({"kid": self.kid, "use": "sig", "alg": "RS256"})
        return jwk

    def token(self, **overrides: Any) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "sub": "kp_learner123",
            "iss": ISSUER,
            "aud": [AUDIENCE],
            "iat": now,
            "exp": now + 3600,
        }
        headers = {"kid": self.kid}
        headers.update(overrides.pop("headers", {}))
        for name, value in overrides.items():
            if value is None:
                claims.pop(name, None)
            else:
                claims[name] = value
        return jwt.encode(claims, self.private, algorithm="RS256", headers=headers)


def jwks(*keys: SigningKey) -> dict[str, Any]:
    return {"keys": [key.jwk for key in keys]}
