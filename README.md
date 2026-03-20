# mubi-to-letterboxd

A command-line script that exports your MUBI watchlist and generates a CSV file ready to import into Letterboxd.

MUBI does not provide a public API. This script works by reading the same internal API endpoints that the MUBI website uses, authenticated with the session token from your browser. Letterboxd does not offer API access for personal projects, so the script produces a CSV file in Letterboxd's supported import format, which you then upload manually through their web interface.

---

## How it works

When you are logged into MUBI in your browser, the site communicates with an internal REST API at `mubi.com/services/api`. Your browser session holds a short-lived Bearer token that authenticates these requests. This script uses that token to call the `/wishes` endpoint, which returns your watchlist, and paginates through all results until every film has been collected.

The output is a two-column CSV file (`Title`, `Year`) that Letterboxd accepts on their import page. Letterboxd matches each row against their film database by title and release year, then adds matched films to a new list of your choosing.

---

## Requirements

- macOS with Python 3.8 or later (`python3 --version` to check)
- The `requests` library
- A MUBI account with films saved to your watchlist
- A Letterboxd account

---

## Installation

**1. Download the script**

Clone the repository or download `mubi_to_letterboxd.py` directly:

```bash
git clone https://github.com/your-username/mubi-to-letterboxd.git
cd mubi-to-letterboxd
```

**2. Install the dependency**

```bash
pip3 install requests
```

---

## Getting your credentials

You need two pieces of information before running the script: your MUBI user ID and your MUBI Bearer token. Both are obtained from your browser.

### Your MUBI user ID

1. Go to [mubi.com](https://mubi.com) and sign in.
2. Click your avatar in the top-right corner and select **Profile**.
3. Look at the URL in your browser's address bar. It will look like:
   ```
   https://mubi.com/en/users/12345678
   ```
4. The number at the end is your user ID. Note it down.

### Your MUBI Bearer token

The Bearer token is a temporary credential tied to your browser session. It expires when your session ends, so you will need to retrieve a fresh token each time you run the script.

1. Go to [mubi.com](https://mubi.com) and sign in.
2. Open your browser's developer tools:
   - **Chrome or Brave:** press `Cmd + Option + I`, then click the **Network** tab.
   - **Firefox:** press `Cmd + Option + I`, then click the **Network** tab.
3. With the Network tab open, reload the page (`Cmd + R`).
4. In the filter/search box within the Network tab, type `wishes` or `api` to narrow down the requests.
5. Click on any request going to `mubi.com/services/api/...`.
6. In the panel that appears on the right, click **Headers**.
7. Scroll down to the **Request Headers** section and find the `Authorization` header. It will look like:
   ```
   Authorization: Bearer eyJhbGciOiJSUzI1NiJ9...
   ```
8. Copy the full value, including the word `Bearer` and the space after it.

> **Note:** If you do not see any requests matching `wishes` or `api`, try navigating to your profile or watchlist page while the Network tab is open, then filter again.

---

## Usage

### Basic usage

```bash
python3 mubi_to_letterboxd.py --user-id 12345678 --token "Bearer eyJ..."
```

Replace `12345678` with your actual user ID and `eyJ...` with your actual token.

The script will:
1. Fetch all films from your MUBI watchlist, paginating through results automatically.
2. Write a file called `mubi_watchlist.csv` in the current directory.
3. Open the Letterboxd import page in your default browser.

### Using environment variables

To avoid typing your credentials on every run, you can export them as environment variables in your terminal session:

```bash
export MUBI_USER_ID=12345678
export MUBI_TOKEN="Bearer eyJ..."
```

Then run the script without flags:

```bash
python3 mubi_to_letterboxd.py
```

To make these permanent, add the two `export` lines to your `~/.zshrc` (or `~/.bash_profile` if you use bash) and restart your terminal.

### All options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--token` | `-t` | `$MUBI_TOKEN` | Your MUBI Bearer token. Include the `Bearer ` prefix. |
| `--user-id` | `-u` | `$MUBI_USER_ID` | Your MUBI numeric user ID. |
| `--output` | `-o` | `mubi_watchlist.csv` | Path and filename for the output CSV. |
| `--no-browser` | | off | Skip opening the Letterboxd import page automatically. |
| `--debug` | | off | Print the raw API response from page 1, useful for diagnosing issues. |

### Examples

Save the CSV to a specific location:
```bash
python3 mubi_to_letterboxd.py --user-id 12345678 --token "Bearer eyJ..." --output ~/Desktop/watchlist.csv
```

Run without opening a browser window:
```bash
python3 mubi_to_letterboxd.py --user-id 12345678 --token "Bearer eyJ..." --no-browser
```

---

## Importing into Letterboxd

Once the script finishes, follow these steps to import the CSV into Letterboxd:

1. Go to [letterboxd.com/import](https://letterboxd.com/import/) (the script opens this automatically).
2. Sign in to Letterboxd if prompted.
3. Under the import options, choose **Import to a List** if you want to create a new dedicated list, or **Import to Watchlist** to add directly to your Letterboxd watchlist.
4. Click **Choose file** and select the `mubi_watchlist.csv` file that was created.
5. Click **Import**.

Letterboxd will process the file and display a summary. Films it successfully matched by title and year will be added immediately. Any films it could not match will be listed separately so you can search for them manually.

---

## Troubleshooting

**Fewer films were exported than expected**

The script paginates automatically using MUBI's default page size of 24 items. If the count is still short, run with `--debug` to print the raw JSON response from the first page. This shows you the exact structure the API is returning, including any pagination fields, so you can see where the discrepancy might be:

```bash
python3 mubi_to_letterboxd.py --user-id 12345678 --token "Bearer eyJ..." --debug
```

**Authentication failed (401)**

Your Bearer token has expired. Tokens are tied to your browser session and become invalid when you log out or the session ends. Follow the steps in [Getting your credentials](#getting-your-credentials) to retrieve a new token.

**404 Not Found**

Your user ID is incorrect. Double-check by visiting your MUBI profile page and reading the number from the URL. Make sure you are not including any extra characters.

**`ModuleNotFoundError: No module named 'requests'`**

The `requests` library is not installed. Run:

```bash
pip3 install requests
```

**SSL warning about LibreSSL**

If you see a warning mentioning `LibreSSL` and `urllib3`, this is a known compatibility notice on older versions of macOS Python and does not affect the script's functionality. The script will still run correctly.

---

## Notes on the MUBI token

- The Bearer token is a session credential. It is equivalent to being logged in. Do not share it with anyone or commit it to version control.
- Add `MUBI_TOKEN` to your `.gitignore` if you store it in a local config file.
- The token expires with your browser session. If you log out of MUBI in your browser, you will need to log back in and copy a new token before running the script again.

---

## License

MIT
