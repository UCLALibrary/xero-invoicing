import argparse
import csv
import datetime
import requests
import tomllib
from retry.api import retry_call
from xero_utils import config_dict, get_access_token, get_tenant_id

# from pprint import pprint


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


def get_invoices(access_token: str, tenant_id: str) -> list[dict]:
    get_url = "https://api.xero.com/api.xro/2.0/Invoices"
    # Just "AUTHORISED" (aka "Awaiting Payment") and "PAID" statuses;
    # "SUBMITTED" (aka "Awaiting Approval") invoices are not yet approved,
    # so not relevant here.

    # "Where": "DateString>='2025-11-19'" doesn't work: 400 Bad Request;
    # use "If-Modified-Since" header (not parameter) instead.
    # First date of production invoices: Nov 6 2025
    start_date = datetime.datetime(2025, 11, 6)
    header_params = {
        "Authorization": "Bearer " + access_token,
        "Xero-tenant-id": tenant_id,
        "Accept": "application/json",
        "If-Modified-Since": start_date.strftime("%a, %d %b %Y %H:%M:%S GMT"),
    }

    invoices: list[dict] = []
    page = 1
    page_size = 100  # default is 100, can be up to 1000.
    # The only way to know how many invoices there are is to retrieve until
    # no more are received.
    more_invoices = True
    while more_invoices:
        query_params = {
            "Statuses": "AUTHORISED,PAID",
            "order": "InvoiceNumber",
            "page": page,
            "pageSize": page_size,
        }

        response = requests.get(
            get_url,
            headers=header_params,
            params=query_params,
        )

        if response.status_code != 200:
            print(response.status_code, response.reason)
        json_response = response.json()
        this_batch: list[dict] = json_response["Invoices"]
        if len(this_batch) > 0:
            invoices.extend(this_batch)
            page += 1
        else:
            more_invoices = False

    print(f"Retrieved {len(invoices)} invoices.")
    return invoices


# def get_invoice(access_token: str, tenant_id: str, invoice_number: str) -> dict:
#     # TODO: Merge with get_invoices, if this goes beyond POC.
#     get_url = f"https://api.xero.com/api.xro/2.0/Invoices/{invoice_number}"
#     response = requests.get(
#         get_url,
#         headers={
#             "Authorization": "Bearer " + access_token,
#             "Xero-tenant-id": tenant_id,
#             "Accept": "application/json",
#         },
#     )
#     invoice = response.json()
#     return invoice


# def get_account(access_token: str, tenant_id: str, account_id: str) -> dict:
#     get_url = f"https://api.xero.com/api.xro/2.0/Accounts/{account_id}"
#     response = requests.get(
#         get_url,
#         headers={
#             "Authorization": "Bearer " + access_token,
#             "Xero-tenant-id": tenant_id,
#             "Accept": "application/json",
#         },
#     )
#     account = response.json()
#     return account


def get_invoice_history(access_token: str, tenant_id: str, invoice_id: str) -> dict:
    get_url = f"https://api.xero.com/api.xro/2.0/Invoices/{invoice_id}/History"
    headers = {
        "Authorization": "Bearer " + access_token,
        "Xero-tenant-id": tenant_id,
        "Accept": "application/json",
    }
    response = requests.get(url=get_url, headers=headers)
    print(f"{invoice_id=}, {response.status_code=}")
    if response.status_code != 200:
        print(
            f"Current API Retry-After: {response.headers.get("Retry-After", "No retry specified")}"
        )
    history = response.json()
    return history


def main() -> None:
    args = _get_args()
    xero_config = _get_xero_config(args.config_file)
    access_token = get_access_token(xero_config)
    tenant_id = get_tenant_id(access_token, xero_config)

    invoices = get_invoices(access_token, tenant_id)

    invoice_audit_data = []
    for invoice in invoices:
        invoice_number = invoice.get("InvoiceNumber", "NO INVOICE NUMBER")
        invoice_date = invoice.get("DateString", "NO DATE")
        status = invoice.get("Status", "NO STATUS")
        invoice_id = invoice.get("InvoiceID", "NO INVOICE ID")

        # Limited by Xero to 60 calls/minute. We could check Retry-After response header,
        # but easier just to use `retry_call()` with a relatively long backoff.
        history = retry_call(
            get_invoice_history,
            fargs=[access_token, tenant_id, invoice_id],
            tries=10,
            delay=1,
            backoff=4,
            max_delay=60,
        )
        history_records = history.get("HistoryRecords", [])
        # pprint(history_records, width=132)
        user_created = ""
        user_approved = ""
        user_paid = ""
        for history_record in history_records:
            event = history_record.get("Changes", "")
            user = history_record.get("User", "")
            if event == "Created":
                user_created = user
            elif event == "Approved":
                user_approved = user
            elif event == "Paid":
                user_paid = user

        # Flag invoices created and approved by the same user.
        audit_message = "SAME USER" if user_created == user_approved else ""

        # Data for output to report.
        invoice_audit_data.append(
            {
                "invoice_number": invoice_number,
                "invoice_date": invoice_date,
                "status": status,
                "user_created": user_created,
                "user_approved": user_approved,
                "user_paid": user_paid,
                "audit_message": audit_message,
            }
        )

    with open("invoice_audit_log.csv", "w") as f:
        writer = csv.DictWriter(f, fieldnames=invoice_audit_data[0].keys())
        writer.writeheader()
        writer.writerows(invoice_audit_data)


if __name__ == "__main__":
    main()
