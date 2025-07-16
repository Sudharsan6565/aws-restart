import os
import json
import requests
import jwt
import base64

from functools import wraps
from flask import request, jsonify

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers

CLERK_ISSUER = os.getenv("CLERK_ISSUER")
CLERK_CLIENT_ID = os.getenv("CLERK_CLIENT_ID")
JWKS_URL = os.getenv("CLERK_JWKS_URL")
CLERK_WHITELIST = "whitelist.json"

# 🔁 Load JWKS at startup
jwks = requests.get(JWKS_URL).json()

def get_public_key(jwk):
    n = int.from_bytes(base64.urlsafe_b64decode(jwk["n"] + "=="), "big")
    e = int.from_bytes(base64.urlsafe_b64decode(jwk["e"] + "=="), "big")

    public_numbers = RSAPublicNumbers(e, n)
    public_key = public_numbers.public_key(default_backend())
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )


def verify_clerk_token(token):
    try:
        if isinstance(token, bytes):
            token = token.decode("utf-8")

        print(f"[DEBUG] Raw Token: {token[:60]}...")

        header = jwt.get_unverified_header(token)
        print(f"[DEBUG] Header: {header}")

        key_data = next(k for k in jwks["keys"] if k["kid"] == header["kid"])
        public_key_pem = get_public_key(key_data)
        print(f"[DEBUG] Public Key OK")

        payload = jwt.decode(
            token,
            public_key_pem,
            algorithms=["RS256"],
            audience="maveriq-backend",  # 🔒 Must match Clerk template
            issuer=CLERK_ISSUER
        )

        print(f"[DEBUG] Payload: {payload}")
        return payload

    except Exception as e:
        print(f"[AUTH ERROR] Invalid token: {e}")
        return None


def require_clerk_auth(view_func):
    @wraps(view_func)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        print("[DEBUG] Raw Authorization header:", auth_header)

        if not auth_header.startswith("Bearer "):
            print("[DEBUG] Missing Bearer prefix")
            return jsonify({"error": "Missing or invalid Authorization header"}), 401

        token = auth_header.removeprefix("Bearer").strip()
        print("[DEBUG] Extracted token:", token[:60], "...")

        payload = verify_clerk_token(token)
        if not payload:
            print("[DEBUG] JWT verification failed")
            return jsonify({"error": "Invalid token"}), 401

        email = payload.get("email")
        if not email:
            print("[DEBUG] Email missing in payload")
            return jsonify({"error": "Email not found in token"}), 401

        # ✅ Whitelist enforcement
        try:
            with open(CLERK_WHITELIST, "r") as whitelist_file:
                whitelist = json.load(whitelist_file)
        except Exception as e:
            print("[DEBUG] Failed to read whitelist:", e)
            return jsonify({"error": "Internal server error"}), 500

        if email not in whitelist.get("approved", []):
            print("[DEBUG] Email not in whitelist:", email)
            return jsonify({"error": "User not allowed"}), 403

        print("[DEBUG] ✅ Authorized user:", email)
        request.email = email
        return view_func(*args, **kwargs)

    return decorated
