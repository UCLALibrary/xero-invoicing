import requests
import webbrowser
from oauthlib.oauth2 import WebApplicationClient
from typing import TypeAlias
from urllib.parse import parse_qsl, urlparse

# For convenience
config_dict: TypeAlias = dict[str, str]


def _get_auth_request_url(xero_config: config_dict) -> str:
    oauth_client = WebApplicationClient(xero_config["client_id"])
    auth_request_url = oauth_client.prepare_request_uri(
        uri=xero_config["authorization_url"],
        redirect_uri=xero_config["redirect_url"],
        scope=[xero_config["scope"]],
        state=xero_config["state"],
    )
    return auth_request_url


def _get_auth_code(url: str) -> str:
    url_query = urlparse(url).query
    query_data = dict(parse_qsl(url_query))
    return query_data["code"]


def _get_refresh_token(xero_config: config_dict) -> str | None:
    try:
        with open(xero_config["refresh_token_file"], "r") as f:
            refresh_token = f.read()
    except FileNotFoundError:
        refresh_token = None
    return refresh_token


def _store_refresh_token(xero_config: config_dict, refresh_token: str) -> None:
    with open(xero_config["refresh_token_file"], "w") as f:
        f.write(refresh_token)


def _get_token_from_auth_code(auth_code: str, xero_config: config_dict) -> str:
    # requests basic auth: auth=(client_id, client_secret)
    # automatically does the same as this:
    # b64_id_secret = b64encode(bytes(client_id + ":" + client_secret, "utf-8")).decode("utf-8")
    # no need to include explicit Basic Authorization headers in request:
    # headers={"Authorization": "Basic " + b64_id_secret},

    response = requests.post(
        xero_config["token_url"],
        auth=(xero_config["client_id"], xero_config["client_secret"]),
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": xero_config["redirect_url"],
        },
    )
    json_response = response.json()
    _store_refresh_token(xero_config, json_response["refresh_token"])
    return json_response["access_token"]


def _get_token_from_refresh_token(refresh_token: str, xero_config: config_dict) -> str:
    response = requests.post(
        xero_config["token_url"],
        auth=(xero_config["client_id"], xero_config["client_secret"]),
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
    )
    json_response = response.json()
    _store_refresh_token(xero_config, json_response["refresh_token"])
    return json_response["access_token"]


def get_access_token(xero_config: config_dict) -> str:
    # If we have a refresh token stored, use it to get a new access token.
    # Otherwise, we have to use the web-based authorization flow to get
    # an access code and exchange it for an access token.
    refresh_token = _get_refresh_token(xero_config)
    if refresh_token:
        # use it
        access_token = _get_token_from_refresh_token(refresh_token, xero_config)
    else:
        # Use the web-based authorization flow
        auth_request_url = _get_auth_request_url(xero_config)
        print(auth_request_url)
        webbrowser.open_new(auth_request_url)

        auth_response_url = input("What URL did Xero return? ")
        auth_code = _get_auth_code(auth_response_url)
        access_token = _get_token_from_auth_code(auth_code, xero_config)

    return access_token


def get_tenant_id(access_token: str, xero_config: config_dict) -> str:
    response = requests.get(
        xero_config["tenant_url"],
        headers={
            "Authorization": "Bearer " + access_token,
            "Content-Type": "application/json",
        },
    )
    json_response = response.json()
    # Response is a list of dicts, one for each organization associated with our credentials.
    # We should have just one... probably could hard-code it, but for now, just return the
    # first "ORGANISATION" tenant id found.
    tenant_ids = [
        tenant["tenantId"]
        for tenant in json_response
        if tenant["tenantType"] == "ORGANISATION"
    ]
    return tenant_ids[0]
