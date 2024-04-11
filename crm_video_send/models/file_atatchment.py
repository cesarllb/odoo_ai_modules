import base64
import csv
import io
import re

import openpyxl
import requests
from googlesearch import search
from odoo import api, fields, models
from odoo.exceptions import UserError


class MyFileModel(models.Model):
    _name = "my.file.model"

    file_attachment = fields.Binary(string="Archivo adjunto", required=True)
    file_type = fields.Selection(
        [("csv", "CSV"), ("xlsx", "Excel")],
        string="File Type",
        default="csv",
    )

    def get_desctiption(self, email: str, name: str) -> str:
        def is_sensible_description(description: str) -> bool:
            if re.search(
                r"[0-9]{5,}", description
            ):  # Detects strings of 5 or more digits
                return False
            if not re.search(
                r"[a-zA-Z]", description
            ):  # Checks if there are no letters
                return False
            return True

        def search_google():
            results = search(
                f"Company {name}",  # {email}",
                advanced=True,
                lang="es",
                num_results=1,
                # timeout=3,
            )
            first_result = next(results, None)

            if first_result:
                return (
                    first_result.description
                    if is_sensible_description(first_result.description)
                    else "No info"
                )
            else:
                return "No info"

        try:
            possible_url = email.split("@")[-1] if "@" in email else False
            if (
                possible_url != "gmail.com"
                and possible_url != "outlook.com"
                and possible_url != "yahoo.com"
                and possible_url != "hotmail.com"
            ):
                response = requests.get(possible_url)
                if response.status_code == 200:
                    return response.text
                else:
                    return search_google()
        except:
            return search_google()

    @api.model
    def create(self, vals):
        record = super(MyFileModel, self).create(vals)

        if "file_attachment" in vals:
            try:
                file_type = vals["file_type"] if "file_type" in vals else False
                file_bytes = base64.b64decode(vals["file_attachment"])
                data = io.BytesIO(file_bytes)

                if file_type == "csv":
                    decoded_csv = file_bytes.decode("utf-8")
                    lines = decoded_csv.splitlines()
                    reader = csv.DictReader(lines)
                    headers = reader.fieldnames
                elif file_type == "xlsx":
                    workbook = openpyxl.load_workbook(data, read_only=True)
                    sheet = workbook.active
                    headers = [cell.value for cell in sheet[1]]
                else:
                    raise UserError(str(file_type))

                email_field = next((k for k in headers if "email" in k.lower()), None)
                name_field = next((k for k in headers if "name" in k.lower()), None)

                if email_field and name_field:
                    video_sender_id = self._context.get("current_crm_video_sender_id")
                    if video_sender_id:
                        if file_type == "csv":
                            for row in reader:
                                description = self.get_desctiption(
                                    row.get(email_field), row.get(name_field)
                                )
                                self.create_new_line(
                                    video_sender_id,
                                    row,
                                    email_field,
                                    name_field,
                                    description,
                                )
                        elif file_type == "xlsx":
                            for row in sheet.iter_rows(min_row=2, values_only=True):
                                row_dict = dict(zip(headers, row))
                                description = self.get_desctiption(
                                    row_dict.get(email_field), row_dict.get(name_field)
                                )
                                self.create_new_line(
                                    video_sender_id,
                                    row_dict,
                                    email_field,
                                    name_field,
                                    description,
                                )

                else:
                    raise UserError("Invalid file")
            except Exception as e:
                raise UserError("Invalid file. " + str(e))

        return record

    def create_new_line(
        self, video_sender_id, row, email_field, name_field, description
    ):
        self.env["crm.video.sender.line"].create(
            {
                "video_post_id": video_sender_id,
                "email": row.get(email_field),
                "company_name": row.get(name_field),
                "description": description,
                "is_processed": False,
            }
        )
