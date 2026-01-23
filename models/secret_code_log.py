# -*- coding: utf-8 -*-

import json
import logging
import time

import requests

from odoo import api, fields, models

# FRAPPE_BASE_URL = 'https://ghori.u.frappe.cloud'
FRAPPE_BASE_URL = 'https://stagingghori.u.frappe.cloud'
# FRAPPE_API_KEY = '1671f30aad9dd4f'
FRAPPE_API_KEY = 'fa62fba39461c4f'
# FRAPPE_API_SECRET = '9ffdd149d876332'
FRAPPE_API_SECRET = 'ba1c168e024aea5'
FRAPPE_PAGE_SIZE = 100
FRAPPE_TIMEOUT_SECONDS = 120
FRAPPE_MAX_RETRIES = 3
FRAPPE_RETRY_BACKOFF_SECONDS = 2
FRAPPE_MAX_RUNTIME_SECONDS = 900
FRAPPE_SECRET_CODE_LOGS_DOCTYPE = 'Secret Code Logs'

_logger = logging.getLogger(__name__)

class SecretCodeLog(models.Model):
    _name = 'secret_code_log'
    _description = 'Secret Code Logs'
    _rec_name = 'searched_code'
    _order = 'write_date desc'

    frappe_name = fields.Char(index=True)
    frappe_creation = fields.Datetime()

    searched_code = fields.Char(required=True, index=True)
    public_code = fields.Char(index=True)

    status = fields.Selection(
        [('validated', 'VALIDATED'), ('rejected', 'REJECTED')],
        required=True,
    )
    is_matched = fields.Boolean(default=False)
    fail_reason = fields.Char()
    success_attempt = fields.Integer()
    message = fields.Char()
    description = fields.Text()

    search_ip_address = fields.Char(readonly=True)
    search_device_details = fields.Text(readonly=True)

    search_city = fields.Char()
    search_country = fields.Char()

    search_latitude = fields.Float(readonly=True)
    search_longitude = fields.Float(readonly=True)
    is_last_updated = fields.Boolean(compute='_compute_is_last_updated')

    def _notify_live_refresh(self):
        self.env['bus.bus']._sendone(
            'secret_codes_refresh',
            'secret_codes_refresh',
            {'model': self._name},
        )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._notify_live_refresh()
        return records
    
    @api.depends('write_date')
    def _compute_is_last_updated(self):
        latest = self.search([], order='write_date desc, id desc', limit=1)
        latest_id = latest.id if latest else False
        for record in self:
            record.is_last_updated = bool(latest_id and record.id == latest_id)
    

    @api.model
    def sync_frappe_logs(self, *args, **kwargs):
        page = 1
        start_time = time.monotonic()

        url = f"{FRAPPE_BASE_URL.rstrip('/')}/api/method/frappe.client.get_list"
        headers = {"Authorization": f"token {FRAPPE_API_KEY}:{FRAPPE_API_SECRET}"}
        fields_list = [
            "name",
            "searched_code",
            "public_code",
            "creation",
            "status",
            "is_matched",
            "search_ip_address",
            "search_device_details",
            "search_city",
            "search_country",
            "search_latitude",
            "search_longitude",
        ]

        def _normalize_status(value):
            if not value:
                return False
            value = str(value).strip().lower()
            return value if value in {"validated", "rejected"} else False

        def _normalize_frappe_datetime(value):
            if not value:
                return False
            value = str(value).strip()
            return value[:19] if len(value) > 19 else value

        while True:
            if time.monotonic() - start_time > FRAPPE_MAX_RUNTIME_SECONDS:
                _logger.info("Frappe logs manual sync paused after max runtime at page %s.", page)
                break

            params = {
                "doctype": FRAPPE_SECRET_CODE_LOGS_DOCTYPE,
                "fields": json.dumps(fields_list),
                "limit_start": (page - 1) * FRAPPE_PAGE_SIZE,
                "limit_page_length": FRAPPE_PAGE_SIZE,
            }

            response = None
            attempt = 0
            while True:
                attempt += 1
                try:
                    response = requests.get(
                        url,
                        headers=headers,
                        params=params,
                        timeout=FRAPPE_TIMEOUT_SECONDS,
                    )
                    response.raise_for_status()
                    break
                except requests.RequestException as exc:
                    _logger.warning(
                        "Frappe logs manual sync retry %s on page %s due to error: %s",
                        attempt,
                        page,
                        exc,
                    )
                    if attempt >= FRAPPE_MAX_RETRIES:
                        raise
                    time.sleep(FRAPPE_RETRY_BACKOFF_SECONDS)

            payload = response.json()
            records = payload.get("message") or []
            if not records:
                _logger.info("Frappe logs manual sync complete: no records at page %s.", page)
                break

            incoming_names = [rec.get("name") for rec in records if rec.get("name")]
            existing_names = set()
            if incoming_names:
                existing_names = set(
                    self.search([('frappe_name', 'in', incoming_names)]).mapped('frappe_name')
                )

            create_vals = []
            for rec in records:
                frappe_name = rec.get("name")
                if not frappe_name or frappe_name in existing_names:
                    continue

                searched_code = rec.get("searched_code")
                if not searched_code:
                    continue

                status = _normalize_status(rec.get("status"))
                create_vals.append(
                    {
                        "frappe_name": frappe_name,
                        "frappe_creation": _normalize_frappe_datetime(rec.get("creation")),
                        "searched_code": searched_code,
                        "public_code": rec.get("public_code") or False,
                        "status": status or "rejected",
                        "is_matched": bool(int(rec.get("is_matched") or 0)),
                        "search_ip_address": rec.get("search_ip_address"),
                        "search_device_details": rec.get("search_device_details"),
                        "search_city": rec.get("search_city"),
                        "search_country": rec.get("search_country"),
                        "search_latitude": rec.get("search_latitude") or 0.0,
                        "search_longitude": rec.get("search_longitude") or 0.0,
                    }
                )

            if create_vals:
                self.sudo().create(create_vals)

            page += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sync completed',
                'message': 'Frappe logs sync finished.',
                'type': 'info',
                'sticky': False,
            },
        }

    def action_view_location(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Location',
            'res_model': 'secret_codes.view_location_wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_latitude': self.search_latitude,
                'default_longitude': self.search_longitude,
            },
        }
        
