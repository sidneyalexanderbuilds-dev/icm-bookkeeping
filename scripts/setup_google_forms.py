#!/usr/bin/env python3
"""
setup_google_forms.py
Sets up Google Forms + Sheets for icm-bookkeeping subscriber capture.
- Creates a Google Form with email field
- Creates a linked spreadsheet
- Shares spreadsheet with sidneyalexanderbuilds@gmail.com
- Updates landing page with form embed code
"""
import json
import os
import sys
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = [
    "https://www.googleapis.com/auth/forms",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

CLIENT_SECRET_PATH = "/root/.hermes/google_client_secret.json"
TOKEN_PATH = "/root/.hermes/google_token.json"
LANDING_PAGE_PATH = "/tmp/icm-bookkeeping/index.html"


def get_credentials():
    """Load or refresh credentials."""
    creds = None
    if os.path.exists(TOKEN_PATH):
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_config(
            json.load(open(CLIENT_SECRET_PATH)), SCOPES
        )
        auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
        print(f"AUTH_URL={auth_url}")
        print("Visit the URL above, authorize, then paste the localhost redirect URL back here.")
        code = input("Paste the full localhost URL: ").strip()
        flow.fetch_token(code=code)
        creds = flow.credentials
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
    return creds


def create_form(creds):
    """Create Google Form with email question."""
    forms = build("forms", "v1", credentials=creds)

    # Create the form
    form_body = {
        "info": {
            "title": "icm-bookkeeping Waitlist",
            "documentTitle": "icm-bookkeeping Waitlist",
        }
    }
    form = forms.forms().create(body=form_body).execute()
    form_id = form["formId"]
    print(f"Form created: {form_id}")

    # Add email question
    question = {
        "requests": [
            {
                "createItem": {
                    "item": {
                        "title": "Email address",
                        "questionItem": {
                            "question": {
                                "required": True,
                                "textQuestion": {
                                    "paragraph": False,
                                },
                            }
                        },
                    },
                    "location": {"index": 0},
                }
            }
        ]
    }
    forms.forms().batchUpdate(formId=form_id, body=question).execute()
    print(f"Email question added to form")
    return form_id


def create_spreadsheet(creds, form_id):
    """Create spreadsheet linked to form."""
    sheets = build("sheets", "v4", credentials=creds)
    drive = build("drive", "v3", credentials=creds)

    # Create spreadsheet
    spreadsheet = (
        sheets.spreadsheets()
        .create(
            body={
                "properties": {"title": "icm-bookkeeping Waitlist"},
                "sheets": [{"properties": {"title": "Form Responses"}}],
            }
        )
        .execute()
    )
    spreadsheet_id = spreadsheet["spreadsheetId"]
    print(f"Spreadsheet created: {spreadsheet_id}")

    # Write headers
    sheets.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="Form Responses!1:1",
        valueInputOption="RAW",
        body={"values": [["Timestamp", "Email"]]},
    ).execute()

    # Link form to spreadsheet
    try:
        forms = build("forms", "v1", credentials=creds)
        forms.forms().setDestination(
            formId=form_id,
            body={"spreadsheetId": spreadsheet_id},
        ).execute()
        print("Form linked to spreadsheet")
    except Exception as e:
        print(f"Form link note: {e}")

    # Share with sidney
    drive.permissions().create(
        fileId=spreadsheet_id,
        body={
            "type": "user",
            "role": "reader",
            "emailAddress": "sidneyalexanderbuilds@gmail.com",
        },
        fields="id",
    ).execute()
    print("Spreadsheet shared with sidneyalexanderbuilds@gmail.com")

    return spreadsheet_id, f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"


def update_landing_page(form_id):
    """Replace Tally iframe with Google Form iframe."""
    with open(LANDING_PAGE_PATH) as f:
        html = f.read()

    embed_url = f"https://docs.google.com/forms/d/{form_id}/viewform?embedded=true"

    new_embed = f'''  <!-- Google Forms Email Capture -->
  <div class="google-form-embed">
    <iframe
      src="{embed_url}"
      width="100%"
      height="100"
      frameborder="0"
      marginheight="0"
      marginwidth="0"
      style="border: none; max-width: 480px; margin: 0 auto; display: block;">
      Loading…
    </iframe>
  </div>'''

    # Replace existing Tally embed
    if "tally.so" in html:
        import re
        html = re.sub(
            r'<div class="tally-embed-wrapper">.*?</div>\s*<p style="font-size: 0\.8rem',
            new_embed + '\n  <p style="font-size: 0.8rem',
            html,
            flags=re.DOTALL,
        )
    else:
        # Replace the hero actions div
        import re
        html = re.sub(
            r'<div class="hero-actions".*?</div>\s*</section>',
            new_embed + '\n  </section>',
            html,
            flags=re.DOTALL,
        )

    with open(LANDING_PAGE_PATH, "w") as f:
        f.write(html)

    print(f"Landing page updated with Google Form embed")


def main():
    print("=== icm-bookkeeping Google Forms Setup ===\n")

    creds = get_credentials()

    print("\n--- Creating Form ---")
    form_id = create_form(creds)

    print("\n--- Creating Spreadsheet ---")
    spreadsheet_id, spreadsheet_url = create_spreadsheet(creds, form_id)

    print("\n--- Updating Landing Page ---")
    update_landing_page(form_id)

    form_url = f"https://docs.google.com/forms/d/{form_id}/viewform"

    print("\n=== DONE ===")
    print(f"Form URL:  {form_url}")
    print(f"Form embed: {form_url}/viewform?embedded=true")
    print(f"Spreadsheet: {spreadsheet_url}")
    return form_id, spreadsheet_id, form_url, spreadsheet_url


if __name__ == "__main__":
    main()