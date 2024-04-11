import asyncio
from enum import auto
import os
import random
import smtplib
from concurrent.futures import ThreadPoolExecutor
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .promo_default_msg import subject, prompt_text, sender_email, app_password, email_body, vid_attach_name

import requests
from odoo import api, fields, models
from openai import OpenAI

from .video_generation import check_if_ready, request_video

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

class AutomatedCron(models.Model):
    _name = "automated.cron"

    cron_id = fields.Integer(string="ID")
    cron_stop = fields.Boolean(string="Stop")


class CrmVideoLine(models.Model):
    _name = "crm.video.sender.line"
    _order = "create_date DESC"

    video_post_id = fields.Many2one("crm.video.sender")

    is_processed = fields.Boolean(string="Procesado")
    email = fields.Char(string="Email", required=True)
    company_name = fields.Char(string="Nombre de compañia", required=True)
    description = fields.Text(string="Descripción")

    def record_video_sender_action(self):
        video_sender = self.env["crm.video.sender"].browse(self.video_post_id)
        asyncio.run(video_sender.process_record(self, random.randint(10, 100)))


class CrmVideoSender(models.Model):
    _name = "crm.video.sender"

    client_lines_ids = fields.One2many("crm.video.sender.line", "video_post_id")

    def upload_csv_action(self):
        action = {
            "type": "ir.actions.act_window",
            "name": "Subir Excel o CSV",
            "res_model": "my.file.model",
            "view_mode": "form",
            "target": "new",
            "context": {"current_crm_video_sender_id": self.id},
        }
        return action

    def cron_action(self, email, subject, video_id, cron_id):
        # automated_cron_tool = (
        #     self.env["automated.cron"].sudo().search([("cron_id", "=", cron_id)])
        # )
        status_response = check_if_ready(video_id)
        if (
            status_response["data"]["status"] == "completed"
            # and not automated_cron_tool.cron_stop
        ):
            video_url = status_response["data"]["video_url"]
            self.send_email(email, subject, video_url)
            # automated_cron_tool = (
            #     self.env["automated.cron"].sudo().search([("cron_id", "=", cron_id)])
            # )
            # automated_cron_tool.write({"cron_stop": True})

    def create_cron_job(self, email, subject, video_id, index):
        try:
            user_root = self.env.ref("base.user_root")
            cron_job = (
                self.env["ir.cron"]
                .sudo()
                .create(
                    {
                        "name": f"Send video #{str(index)}",
                        "model_id": self.env["ir.model"]._get(self._name).id,
                        "state": "code",
                        "code": f"model.cron_action('{email}', '{subject}', '{video_id}', {1234})",
                        "active": True,
                        "user_id": user_root.id,
                        "interval_number": 30,
                        "interval_type": "minutes",
                        "numbercall": 1,
                    }
                )
            )
            self.env["ir.cron"].sudo().write(
                {
                    "code": f"model.cron_action('{email}', '{subject}', '{video_id}', {cron_job.id})"
                }
            )
            # self.env["automated.cron"].sudo().create(
            #     {"cron_id": cron_job.id, "cron_stop": False}
            # )
            return True
        except Exception as e:
            return "Failed to create cron job: %s", str(e)

    async def process_record(self, record, index, text=False):
        try:
            promo_text = await self.async_generate_gpt_promo_text(
                record.company_name, record.description
            )
            if not text:
                video_response = request_video(promo_text)
                try:
                    if video_response.get("message") == "Success":
                        video_id = video_response["data"]["video_id"]
                        self.create_cron_job(
                            record.email,
                            subject,
                            video_id,
                            index,
                        )
                except:
                    print("Error getting video id")
                    return
            else:
                self.send_email_no_vid(
                    record.email,
                    subject,
                    promo_text,
                )
            record.write({"is_processed": True})
        except Exception as e:
            print(f"Error processing record {record}: {e}")

    @api.model
    def thread_video_sender_action(self, text=False):
        if not text:
            records_with_description = [
                record
                for record in self.client_lines_ids
                if record.description != "No info" and record.is_processed is False
            ]
            selected_records = random.sample(
                records_with_description, min(5, len(records_with_description))
            )
            # purge_cron = self.env['ir.cron'].sudo().search([('name', '=', "Purge crons")])
            # if not purge_cron.exists():
            #     user_root = self.env.ref("base.user_root")
            #     self.env["ir.cron"].sudo().create(
            #             {
            #                 "name": "Purge crons",
            #                 "model_id": self.env["ir.model"]._get(self._name).id,
            #                 "state": "code",
            #                 "code": "model.purge_crons()",
            #                 "active": True,
            #                 "user_id": user_root.id,
            #                 "interval_number": 2,
            #                 "interval_type": "minutes",
            #                 "numbercall": -1,
            #             }
            #         )
        else:
            selected_records = [
                r for r in self.client_lines_ids if r.is_processed is False
            ]

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        tasks = [
            loop.create_task(self.process_record(record.with_env(self.env), i, text))
            for i, record in enumerate(selected_records)
        ]

        loop.run_until_complete(asyncio.gather(*tasks))

    def purge_crons(self):
        automated_crons_tool = (
            self.env["automated.cron"].sudo().search([("cron_stop", "=", True)])
        )
        for c in automated_crons_tool:
            cron = self.env["ir.cron"].sudo().search([("id", "=", c.cron_id)])
            if cron.exists():
                cron.unlink()
                c.unlink()

    def video_sender_action(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        with ThreadPoolExecutor() as executor:
            loop.run_in_executor(executor, self.thread_video_sender_action)

    def email_sender_action(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        with ThreadPoolExecutor() as executor:
            loop.run_in_executor(executor, self.thread_video_sender_action, True)

    async def async_generate_gpt_promo_text(self, company_name, company_info) -> str:
        client = OpenAI(api_key=OPENAI_API_KEY)
        company_info = (
            company_info if company_info else "No se encontro informacion de la empresa"
        )
        prompt = prompt_text.format(company_name=company_name, company_info=company_info)

        chat_completion = client.chat.completions.create(
            model="gpt-3.5-turbo-1106",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            top_p=1,
        )
        return chat_completion.choices[0].message.content.strip()

    def send_email(self, email, subject, video_url) -> None:
        sender = sender_email
        app_email_password = app_password
        video_data = requests.get(video_url).content
        file_path = "/tmp/video.mp4"
        if os.name == 'nt':
            file_path = "C:\\Temp\\temp_video.mp4"
        with open(file_path, "wb") as file:
            file.write(video_data)
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = email

        msg.attach(
            MIMEText(
                email_body,
                "plain",
            )
        )

        try:
            with open(file_path, "rb") as file:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(file.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    "attachment; filename= %s" % f"{vid_attach_name}.mp4",
                )
                msg.attach(part)
        except Exception as e:
            print(f"File not found: {e}")
            return False

        try:
            server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
            server.login(sender, app_email_password)
            server.send_message(msg)
            server.quit()
            print("Email sent successfully")
            return True
        except Exception as e:
            print(f"Error occurred while sending email: {e}")
            return False
        finally:
            os.remove(file_path)

    def send_email_no_vid(self, email, subject, body) -> None:
        sender = sender_email
        app_email_password = app_password

        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = email

        msg.attach(MIMEText(body, "plain"))

        try:
            server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
            server.login(sender, app_email_password)
            server.send_message(msg)
            server.quit()
            print("Email sent successfully")
        except Exception as e:
            print(f"Error occurred while sending email: {e}")
