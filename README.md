# xero-invoicing

Command-line utilities working with the Xero invoicing APIs.

# Developer Information

## Build (first time) / rebuild (as needed)

`docker compose build`

This builds a Docker image, `xero-invoicing-xero:latest`, which can be used for developing, testing, and running code.

## Dev container

This project comes with a basic dev container definition, in `.devcontainer/devcontainer.json`. It's known to work with VS Code,
and may work with other IDEs like PyCharm.  For VS Code, it also installs the Python, Black (formatter), and Flake8 (linter)
extensions.

The project's directory is available within the container at `/home/xero/project`.

### Rebuilding the dev container

VS Code builds its own container from the base image. This container may not always get rebuilt when the base image is rebuilt
(e.g., if packages are changed via `requirements.txt`).

If needed, rebuild the dev container by:
1. Close VS Code and wait several seconds for the dev container to shut down (check via `docker ps`).
2. Delete the dev container.
   1. `docker images | grep vsc-xero-invoicing` # vsc-xero-invoicing-LONG_HEX_STRING-uid
   2. `docker image rm -f vsc-xero-invoicing-LONG_HEX_STRING-uid`
3. Start VS Code as usual.

## Running code

Running code from a VS Code terminal within the dev container should just work, e.g.: `python some_script.py` (whatever the specific program is).

Otherwise, run a program via docker compose.  From the project directory:

```
# Start the system
$ docker compose up -d

# Open a shell in the container
$ docker compose exec xero bash

# Open a Python shell in the container
$ docker compose exec xero python

# Shut the system down
$ docker compose down
```

Or just run something directly:
`docker compose run xero python some_script.py`


## Scripts

### Invoice Audit Log

Generate an invoice audit log which lists all invoices and flags any where the user who created the invoice is the same as the
user who approved it.  Output is written to `invoice_audit_log.csv`, replacing the file if it exists.
```
docker compose run xero python make_invoice_audit_log.py --config_file secrets.toml
```

The script will show output similar to this:
```
Retrieved 213 invoices.
invoice_id='0b5f13c3-5b98-498d-8a06-e724344ba2e4', response.status_code=429
Current API Retry-After: 29
[similar lines removed]
```
The `status-code=429` and `API Retry-After` lines are fine, just messages showing the API rate limit has been reached.  The script
gradually backs off frequency of requests until they start succeeding, then ramps up again.

### Secrets

The Xero API [requires a few secrets](https://developer.xero.com/documentation/guides/oauth2/client-credentials/) and pseudo-secrets.
There are associated with our "UCLA Library API Utilities" application:
* `client_id`: the Xero-assigned client id for each application
* `client_secret`: a generated value associated with the `client_id`
* `tenant_id`: the id of our organization within Xero

A `refresh_token` is stored in a local file which is not included in the repository. This is used to retrieve a current
`access_token` via API. Ask a colleague if you need a copy of this file; otherwise, you will need to generate a new one.
```
# Try to run the desired script
$ docker compose run xero python some_script.py

# If no refresh token file is found, or the token has expired, you'll be prompted in the console
# to visit a login URL. You will need a valid Xero account,

Visit this URL to authorize: https://login.xero.com/identity/connect/authorize.... (parameters omitted)

# You may need to copy/paste/click to open that URL, if it does not open in your browser automatically.

# A Xero page will open with details about what's being requested.
# Click "Allow access" to approve the request.

# A browser error will appear, because the redirect URL is not a real one.  This is OK.
# A prompt should appear in your console, asking for the Xero URL; paste it in and hit return.

What URL did Xero return? http://localhost/redirect_tbd.... (parameters omitted)

# This will create a file with the refresh token, and the script should then be able to run.
```