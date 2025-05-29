import argparse
import requests
import tomllib
import webbrowser
from oauthlib.oauth2 import WebApplicationClient
from typing import TypeAlias
from urllib.parse import parse_qsl, urlparse
from pprint import pprint

# from xero_python.accounting import AccountingApi
# from xero_python.api_client import ApiClient
# from xero_python.api_client.configuration import Configuration
# from xero_python.api_client.oauth2 import OAuth2Token

# For convenience
config_dict: TypeAlias = dict[str, str]


def _get_args() -> argparse.Namespace:
    """Returns the command-line arguments for this program."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config_file", help="Path to configuration file", required=True
    )
    args = parser.parse_args()
    return args


def _get_config(config_file_name: str) -> dict[str, config_dict]:
    """Returns configuration for this program, loaded from TOML file."""
    with open(config_file_name, "rb") as f:
        config = tomllib.load(f)
    return config


def _get_xero_config(config_file_name: str) -> config_dict:
    config = _get_config(config_file_name)
    return config["xero"]


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


# def _api_usage_sucks_i_hate_this_sdk():
#     api_client = ApiClient(
#         Configuration(
#             debug=False,
#             oauth2_token=OAuth2Token(
#                 client_id=xero_config["client_id"],
#                 client_secret=xero_config["client_secret"],
#             ),
#         ),
#         pool_threads=1,
#     )

#     @api_client.oauth2_token_getter
#     def obtain_xero_oauth2_token():
#         return xero_config["access_token"]

#     @api_client.oauth2_token_saver
#     def store_xero_oauth2_token(token):
#         xero_config["access_token"] = access_token

#     api_client.set_oauth2_token(access_token)

#     accounting = AccountingApi(api_client)
#     invoices = accounting.get_invoices
#     pprint(invoices)


def get_invoices(access_token: str, tenant_id: str):
    get_url = "https://api.xero.com/api.xro/2.0/Invoices"
    parameters = {"Statuses": "DRAFT,AUTHORISED"}
    # Filtering by invoice number doesn't seem to work, contrary to the docs
    # parameters = {"InvoiceNumber": "PRSV-INV-0017"}
    response = requests.get(
        get_url,
        headers={
            "Authorization": "Bearer " + access_token,
            "Xero-tenant-id": tenant_id,
            "Accept": "application/json",
        },
        params=parameters,
    )
    json_response = response.json()
    # pprint(json_response, width=132)
    invoices = json_response["Invoices"]
    for invoice in invoices:
        print(invoice["InvoiceNumber"], invoice["Status"], invoice["Total"])


def get_invoice(access_token: str, tenant_id: str, invoice_number: str) -> dict:
    # TODO: Merge with get_invoices, if this goes beyond POC.
    get_url = f"https://api.xero.com/api.xro/2.0/Invoices/{invoice_number}"
    response = requests.get(
        get_url,
        headers={
            "Authorization": "Bearer " + access_token,
            "Xero-tenant-id": tenant_id,
            "Accept": "application/json",
        },
    )
    invoice = response.json()
    return invoice


def get_account(access_token: str, tenant_id: str, account_id: str) -> dict:
    get_url = f"https://api.xero.com/api.xro/2.0/Accounts/{account_id}"
    response = requests.get(
        get_url,
        headers={
            "Authorization": "Bearer " + access_token,
            "Xero-tenant-id": tenant_id,
            "Accept": "application/json",
        },
    )
    account = response.json()
    return account


def main() -> None:
    args = _get_args()
    xero_config = _get_xero_config(args.config_file)
    access_token = get_access_token(xero_config)
    # # To make api_client happy, store access_token in config
    # xero_config["access_token"] = access_token
    tenant_id = get_tenant_id(access_token, xero_config)

    get_invoices(access_token, tenant_id)

    invoice_number = "PRSV-INV-0017"
    invoice_data = get_invoice(access_token, tenant_id, invoice_number)
    pprint(invoice_data, width=132)
    # When supposedly retrieving "an invoice", the invoice data is still in a list
    # with an "Invoices" key.
    invoice = invoice_data["Invoices"][0]
    line_items = invoice["LineItems"]
    for line_item in line_items:
        account_id = line_item["AccountID"]
        line_item_amount = line_item["LineAmount"]
        # Just getting one account, API returns a list, QAD for now
        account = get_account(access_token, tenant_id, account_id)["Accounts"][0]
        item_code = account["Name"]
        print(item_code, line_item_amount)


if __name__ == "__main__":
    main()
