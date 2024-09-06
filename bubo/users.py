import json
from typing import List, Dict, Optional

import requests

# noinspection PyPackageRequirements
from keycloak import KeycloakAdmin

from bubo.config import Config
from bubo.emails import send_plain_email
from bubo.email_strings import INVITE_LINK_EMAIL
from bubo.errors import ConfigError


def get_admin_client(config: Config) -> KeycloakAdmin:
    params = {
        "server_url": config.keycloak["url"],
        "realm_name": config.keycloak["realm_name"],
        "client_secret_key": config.keycloak["client_secret_key"],
        "verify": True,
    }
    return KeycloakAdmin(**params)


def create_signup_link(
    config: Config, creator: str, max_signups: int, days_valid: int
) -> str:
    if not config.keycloak_signup.get("enabled"):
        raise ConfigError("Keycloak-Signup not configured")
    response = requests.post(
        f"{config.keycloak_signup.get('url')}/api/pages",
        json={
            "creator": creator,
            "maxSignups": max_signups,
            "validDays": days_valid,
            "token": config.keycloak_signup.get("token"),
        },
        headers={
            "Content-Type": "application/json",
        },
    )
    response.raise_for_status()
    signup_token = response.json().get("signup_token")
    return f"{config.keycloak_signup.get('url')}/{signup_token}"


def create_user(config: Config, username: str, email: str) -> Optional[str]:
    if not config.keycloak.get("enabled"):
        return
    keycloak_admin = get_admin_client(config)
    return keycloak_admin.create_user(
        {
            "email": email,
            "emailVerified": True,
            "enabled": True,
            "username": username,
        }
    )


def invite_user(config: Config, email: str, creator: str):
    if not config.keycloak_signup.get("enabled"):
        return
    # Create page
    response = requests.post(
        f"{config.keycloak_signup.get('url')}/api/pages",
        json={
            "creator": creator,
            "maxSignups": 1,
            "validDays": config.keycloak_signup.get("page_valid_days"),
            "token": config.keycloak_signup.get("token"),
        },
        headers={
            "Content-Type": "application/json",
        },
    )
    response.raise_for_status()
    # Send invite link
    signup_token = response.json().get("signup_token")
    message = (
        INVITE_LINK_EMAIL.replace(
            "%%organisation%%", config.keycloak_signup.get("organisation")
        )
        .replace("%%link%%", f"{config.keycloak_signup.get('url')}/{signup_token}")
        .replace("%%days%%", str(config.keycloak_signup.get("page_days_valid")))
    )
    send_plain_email(config, email, message)


def send_password_reset(config: Config, user_id: str) -> Dict:
    if not config.keycloak.get("enabled"):
        return {}
    keycloak_admin = get_admin_client(config)
    keycloak_admin.send_update_account(
        user_id=user_id,
        payload=json.dumps(["UPDATE_PASSWORD"]),
    )


def get_user_by_attr(config: Config, attr: str, value: str) -> Optional[Dict]:
    if not config.keycloak.get("enabled"):
        return
    keycloak_admin = get_admin_client(config)
    users = keycloak_admin.get_users(
        {
            attr: value,
        }
    )
    if len(users) == 1:
        return users[0]
    elif len(users) > 1:
        raise Exception(f"More than one user found with the same {attr} = {value}")


def list_users(config: Config) -> List[Dict]:
    if not config.keycloak.get("enabled"):
        return []
    keycloak_admin = get_admin_client(config)
    users = keycloak_admin.get_users({})
    return users
