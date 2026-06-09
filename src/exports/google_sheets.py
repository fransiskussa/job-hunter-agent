import logging
import os
import json
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
from src.config.settings import settings

logger = logging.getLogger(__name__)

class GoogleSheetsExporter:
    def __init__(self):
        self.sheet_id = settings.GOOGLE_SHEET_ID
        self.credentials_path = settings.GOOGLE_CREDENTIALS_PATH
        self.client = None
        self.sheet = None

    def _authenticate(self) -> bool:
        """Authenticate with Google Sheets API."""
        if not self.sheet_id:
            logger.warning("GOOGLE_SHEET_ID is not configured. Skipping Google Sheets export.")
            return False

        try:
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            
            if settings.GOOGLE_CREDENTIALS_JSON:
                creds_dict = json.loads(settings.GOOGLE_CREDENTIALS_JSON)
                credentials = Credentials.from_service_account_info(
                    creds_dict,
                    scopes=scopes
                )
            elif os.path.exists(self.credentials_path):
                credentials = Credentials.from_service_account_file(
                    self.credentials_path,
                    scopes=scopes
                )
            else:
                logger.warning(f"No Google credentials found in JSON env or file at {self.credentials_path}. Skipping export.")
                return False

            self.client = gspread.authorize(credentials)
            self.sheet = self.client.open_by_key(self.sheet_id).sheet1
            logger.info("Successfully authenticated with Google Sheets.")
            return True
        except Exception as e:
            logger.error(f"Failed to authenticate with Google Sheets: {e}")
            return False

    def export_jobs(self, matched_jobs: list[dict]):
        """Export all matching jobs to Google Spreadsheet."""
        if not self._authenticate():
            return

        if not matched_jobs:
            logger.info("No jobs to export to Google Sheets.")
            return

        try:
            # Define headers
            headers = ["Timestamp", "Platform", "Title", "Company", "Location", "Score", "Matched Skills", "Status", "Apply Link"]
            
            # If sheet is totally empty, add headers and format them
            try:
                first_row = self.sheet.row_values(1)
                if not first_row:
                    self.sheet.append_row(headers)
                    # Make headers bold and add background color
                    self.sheet.format("A1:I1", {
                        "textFormat": {"bold": True},
                        "backgroundColor": {"red": 0.8, "green": 0.9, "blue": 1.0}
                    })
            except Exception:
                # If error reading (e.g. empty sheet), just add headers
                self.sheet.append_row(headers)

            rows_to_insert = []
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            for job in matched_jobs:
                skills_list = job.get("matched_skills", [])
                skills_str = ", ".join(skills_list) if skills_list else "None"
                
                # Make URL a clickable hyperlink
                url = job.get("url", "")
                hyperlink_formula = f'=HYPERLINK("{url}", "🔗 Apply Here")' if url else ""
                
                row = [
                    timestamp,
                    job.get("source", "Unknown"),
                    job.get("title", ""),
                    job.get("company", ""),
                    job.get("location", ""),
                    job.get("score", 0),
                    skills_str,
                    "📝 To Apply",  # Default status
                    hyperlink_formula
                ]
                rows_to_insert.append(row)

            # Batch insert with USER_ENTERED to parse formulas
            if rows_to_insert:
                self.sheet.append_rows(rows_to_insert, value_input_option='USER_ENTERED')
                logger.info(f"✅ Successfully exported {len(rows_to_insert)} jobs to Google Sheets.")
                
            # Apply Dropdown and Colors to Status Column (Column H)
            self._apply_status_formatting()

        except Exception as e:
            logger.error(f"Error exporting to Google Sheets: {e}")

    def _apply_status_formatting(self):
        """Apply Data Validation (Dropdown) and Conditional Formatting to Status column (H)."""
        try:
            sheet_id = self.sheet.id
            
            # Note: startColumnIndex=7 means Column H (0-indexed). endColumnIndex=8 is exclusive.
            requests = [
                # 1. Setup Dropdown
                {
                    "setDataValidation": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "startColumnIndex": 7,
                            "endColumnIndex": 8
                        },
                        "rule": {
                            "condition": {
                                "type": "ONE_OF_LIST",
                                "values": [
                                    {"userEnteredValue": "📝 To Apply"},
                                    {"userEnteredValue": "✅ Applied"},
                                    {"userEnteredValue": "⏳ In Process"},
                                    {"userEnteredValue": "❌ Rejected"}
                                ]
                            },
                            "showCustomUi": True,
                            "strict": True
                        }
                    }
                },
                # 2. Conditional Format for Applied (Green) - ENTIRE ROW
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 9}],
                            "booleanRule": {
                                "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": '=$H2="✅ Applied"'}]},
                                "format": {"backgroundColor": {"red": 0.85, "green": 0.93, "blue": 0.83}} # Light Green
                            }
                        },
                        "index": 0
                    }
                },
                # 3. Conditional Format for In Process (Yellow) - ENTIRE ROW
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 9}],
                            "booleanRule": {
                                "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": '=$H2="⏳ In Process"'}]},
                                "format": {"backgroundColor": {"red": 1.0, "green": 0.95, "blue": 0.8}} # Light Yellow
                            }
                        },
                        "index": 0
                    }
                },
                # 4. Conditional Format for Rejected (Red) - ENTIRE ROW
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 9}],
                            "booleanRule": {
                                "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": '=$H2="❌ Rejected"'}]},
                                "format": {"backgroundColor": {"red": 0.96, "green": 0.8, "blue": 0.8}} # Light Red
                            }
                        },
                        "index": 0
                    }
                }
            ]
            
            self.sheet.spreadsheet.batch_update({"requests": requests})
        except Exception as e:
            logger.debug(f"Could not apply advanced formatting to Google Sheets: {e}")
