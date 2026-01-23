# -*- coding: utf-8 -*-

import json
import logging
import secrets
import time

import requests

from odoo import api, fields, models

BULK_INSERT_BATCH_SIZE = 5000
PUBLIC_CODE_LENGTH = 8
PUBLIC_CODE_START = 10100000
SECRET_CODE_LENGTH = 12
BATCH_CODE_LENGTH = 6

# FRAPPE_BASE_URL = 'https://ghori.u.frappe.cloud'
FRAPPE_BASE_URL = 'https://stagingghori.u.frappe.cloud'
# FRAPPE_API_KEY = '1671f30aad9dd4f'
FRAPPE_API_KEY = 'fa62fba39461c4f'
# FRAPPE_API_SECRET = '9ffdd149d876332'
FRAPPE_API_SECRET = 'ba1c168e024aea5'
FRAPPE_PAGE_SIZE = 1000
FRAPPE_TIMEOUT_SECONDS = 120
FRAPPE_MAX_RETRIES = 3
FRAPPE_RETRY_BACKOFF_SECONDS = 2

FRAPPE_SECRET_CODES_DOCTYPE = 'Secret Codes'
FRAPPE_SECRET_CODES_NEXT_PAGE_PARAM = 'secret_codes.frappe_secret_codes_next_page'

# Commit + refresh every N pages (your "100 pages 100 pages")
FRAPPE_PAGES_PER_BATCH = 100

# Optional safety limit per cron run (0 = run until finished)
FRAPPE_MAX_PAGES_PER_RUN = 500

_logger = logging.getLogger(__name__)


class SecretCode(models.Model):
    _name = 'secret_codes'
    _description = 'Secret Codes'
    _rec_name = 'public_code'
    _order = 'write_date desc'
    

    batch_code = fields.Char(required=True, index=True)
    secret_code = fields.Char(required=True, index=True)
    secret_code_masked = fields.Char(compute='_compute_secret_code_masked')
    is_last_updated = fields.Boolean(compute='_compute_is_last_updated')
    public_code = fields.Char(required=True, index=True)


    _sql_constraints = [
        ('secret_code_uniq', 'unique(secret_code)', 'Secret code must be unique.'),
        ('public_code_uniq', 'unique(public_code)', 'Public code must be unique.'),
    ]

    status = fields.Selection(
        [('active', 'ACTIVE'), ('inactive', 'INACTIVE')],
        required=True,
    )
    validate_status = fields.Selection(
        [('validated', 'VALIDATED'), ('pending', 'PENDING')],
        default='pending',
    )
    is_search_limit_reached = fields.Boolean(default=False)
    is_printed = fields.Boolean(default=False)

    searched_count_success = fields.Integer(default=0, readonly=True)
    searched_count_fail = fields.Integer(default=0, readonly=True)

    # -------------------------
    # Live refresh helper
    # -------------------------
    def _notify_live_refresh(self):
        self.env['bus.bus']._sendone(
            'secret_codes_refresh',
            'secret_codes_refresh',
            {'model': self._name},
        )

    @api.depends('secret_code')
    def _compute_secret_code_masked(self):
        for record in self:
            code = record.secret_code or ''
            if not code:
                record.secret_code_masked = ''
                continue
            tail = code[-4:] if len(code) > 4 else code
            record.secret_code_masked = ('*' * max(len(code) - 4, 0)) + tail

    @api.depends('write_date')
    def _compute_is_last_updated(self):
        latest = self.search([], order='write_date desc, id desc', limit=1)
        latest_id = latest.id if latest else False
        for record in self:
            record.is_last_updated = bool(latest_id and record.id == latest_id)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._notify_live_refresh()
        return records

    def write(self, vals):
        result = super().write(vals)
        self._notify_live_refresh()
        return result

    def action_view_secret_code(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'View Secret Code',
            'res_model': 'secret_codes.view_secret_code_wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_secret_code_id': self.id},
        }

    # -------------------------
    # Manual button action
    # -------------------------
    def action_sync_frappe_secret_codes(self):
        cron = self.env.ref('secret_codes.ir_cron_secret_codes_frappe_sync', raise_if_not_found=False)
        if self._last_frappe_code_exists_in_odoo():
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sync skipped',
                    'message': 'Latest Frappe secret code already exists in Odoo.',
                    'type': 'warning',
                    'sticky': False,
                },
            }
        if cron:
            cron.sudo().write({'nextcall': fields.Datetime.now(), 'active': True})
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sync started',
                    'message': 'Frappe sync scheduled in background.',
                    'type': 'info',
                    'sticky': False,
                },
            }
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sync unavailable',
                'message': 'Cron job not found.',
                'type': 'warning',
                'sticky': False,
            },
        }

    @api.model
    def _last_frappe_code_exists_in_odoo(self):
        url = f"{FRAPPE_BASE_URL.rstrip('/')}/api/method/frappe.client.get_list"
        headers = {"Authorization": f"token {FRAPPE_API_KEY}:{FRAPPE_API_SECRET}"}
        params = {
            "doctype": FRAPPE_SECRET_CODES_DOCTYPE,
            "fields": json.dumps(["secret_code"]),
            "limit_start": 0,
            "limit_page_length": 1,
            "order_by": "modified desc",
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
                    "Frappe last-code check retry %s due to error: %s",
                    attempt,
                    exc,
                )
                if attempt >= FRAPPE_MAX_RETRIES:
                    return False
                time.sleep(FRAPPE_RETRY_BACKOFF_SECONDS)

        payload = response.json()
        records = payload.get("message") or []
        if not records:
            return False
        last_code = records[0].get("secret_code")
        if not last_code:
            return False
        return bool(self.search_count([('secret_code', '=', last_code)]))

    # -------------------------
    # Local batch/public generators (unchanged)
    # -------------------------
    @api.model
    def generate_next_batch_code(self):
        self.env.cr.execute(
            """
            SELECT batch_code
            FROM secret_codes
            WHERE batch_code ~ '^B[0-9]+$'
            ORDER BY CAST(SUBSTRING(batch_code FROM 2) AS BIGINT) DESC
            LIMIT 1
            """
        )
        row = self.env.cr.fetchone()
        last_value = int(str(row[0])[1:]) if row else 0
        next_value = last_value + 1
        return f"B{str(next_value).zfill(BATCH_CODE_LENGTH)}"

    @api.model
    def _get_next_public_code(self):
        self.env.cr.execute(
            """
            SELECT public_code
            FROM secret_codes
            WHERE public_code ~ '^[0-9]+$'
            ORDER BY CAST(public_code AS BIGINT) DESC
            LIMIT 1
            """
        )
        row = self.env.cr.fetchone()
        if row and str(row[0]).isdigit():
            return int(row[0])
        return PUBLIC_CODE_START - 1

    @api.model
    def _generate_secret_codes_chunk(self, size, generated_codes):
        codes = set()
        while len(codes) < size:
            code = f"{secrets.randbelow(10 ** SECRET_CODE_LENGTH):0{SECRET_CODE_LENGTH}d}"
            if code in generated_codes or code in codes:
                continue
            codes.add(code)

        self.env.cr.execute(
            "SELECT secret_code FROM secret_codes WHERE secret_code = ANY(%s)",
            (list(codes),),
        )
        existing_set = {row[0] for row in self.env.cr.fetchall()}

        if existing_set:
            codes = {c for c in codes if c not in existing_set}
            while len(codes) < size:
                code = f"{secrets.randbelow(10 ** SECRET_CODE_LENGTH):0{SECRET_CODE_LENGTH}d}"
                if code in generated_codes or code in codes or code in existing_set:
                    continue
                codes.add(code)

        generated_codes.update(codes)
        return list(codes)

    @api.model
    def _insert_secret_codes(self, batch_code, secret_codes, next_public_code):
        now = fields.Datetime.now()
        uid = self.env.user.id
        rows = []
        for secret_code in secret_codes:
            next_public_code += 1
            public_code = str(next_public_code).zfill(PUBLIC_CODE_LENGTH)
            rows.append(
                (
                    batch_code,
                    secret_code,
                    public_code,
                    'inactive',
                    'pending',
                    False,
                    False,
                    0,
                    0,
                    uid,
                    uid,
                    now,
                    now,
                )
            )

        self.env.cr.executemany(
            """
            INSERT INTO secret_codes
                (batch_code, secret_code, public_code, status, validate_status,
                 is_search_limit_reached, is_printed, searched_count_success,
                 searched_count_fail, create_uid, write_uid, create_date, write_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
        return next_public_code

    # -------------------------
    # Frappe sync: 100 pages at a time until finished
    # -------------------------
    @api.model
    def sync_frappe_secret_codes_cron(self, pages_per_batch=None, max_pages_this_run=None):
        """
        Fetch Secret Codes from Frappe and store in Odoo.
        - Processes page-by-page
        - Commits every 100 pages (or FRAPPE_PAGES_PER_BATCH)
        - Continues until no more records
        - Resets next page to 1 when finished
        """
        pages_per_batch = pages_per_batch or FRAPPE_PAGES_PER_BATCH
        max_pages_this_run = FRAPPE_MAX_PAGES_PER_RUN if max_pages_this_run is None else max_pages_this_run

        config = self.env['ir.config_parameter'].sudo()
        next_page = int(config.get_param(FRAPPE_SECRET_CODES_NEXT_PAGE_PARAM, 1))

        url = f"{FRAPPE_BASE_URL.rstrip('/')}/api/method/frappe.client.get_list"
        headers = {"Authorization": f"token {FRAPPE_API_KEY}:{FRAPPE_API_SECRET}"}

        fields_list = [
            "name",
            "batch_code",
            "secret_code",
            "public_code",
            "status",
            "validate_status",
            "modified",
            "is_printed",
            "is_search_limit_reached",
            "searched_count_success",
            "searched_count_fail",
        ]

        def _normalize_status(value, default):
            if not value:
                return default
            value = str(value).strip().lower()
            return value if value in {"active", "inactive"} else default

        def _normalize_validate_status(value, default):
            if not value:
                return default
            value = str(value).strip().lower()
            return value if value in {"validated", "pending"} else default

        if self._last_frappe_code_exists_in_odoo():
            _logger.info("Frappe sync skipped: latest Frappe secret code already exists in Odoo.")
            return True

        pages_done_this_run = 0
        pages_done_in_batch = 0
        stopped_for_limit = False

        def _deactivate_cron():
            cron = self.env.ref('secret_codes.ir_cron_secret_codes_frappe_sync', raise_if_not_found=False)
            if cron:
                cron.sudo().write({'active': False})

        while True:
            # Safety limit (optional)
            if max_pages_this_run and pages_done_this_run >= max_pages_this_run:
                _logger.info(
                    "Frappe sync stopped by max_pages_this_run=%s. Next page=%s",
                    max_pages_this_run,
                    next_page,
                )
                stopped_for_limit = True
                break

            params = {
                "doctype": FRAPPE_SECRET_CODES_DOCTYPE,
                "fields": json.dumps(fields_list),
                "limit_start": (next_page - 1) * FRAPPE_PAGE_SIZE,
                "limit_page_length": FRAPPE_PAGE_SIZE,
                # stable ordering helps if data changes during sync
                "order_by": "modified asc",
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
                        "Frappe sync retry %s on page %s due to error: %s",
                        attempt,
                        next_page,
                        exc,
                    )
                    time.sleep(FRAPPE_RETRY_BACKOFF_SECONDS)

            if response is None:
                # leave next_page as-is so next cron continues
                self.env.cr.commit()
                break

            payload = response.json()
            records = payload.get("message") or []

            # finished
            if not records:
                config.set_param(FRAPPE_SECRET_CODES_NEXT_PAGE_PARAM, 1)
                self.env.cr.commit()
                self._notify_live_refresh()
                _logger.info("Frappe sync complete: no records at page %s. Reset to page 1.", next_page)
                _deactivate_cron()
                break

            incoming_codes = [rec.get("secret_code") for rec in records if rec.get("secret_code")]
            existing_codes = set()
            if incoming_codes:
                self.env.cr.execute(
                    f"SELECT secret_code FROM {self._table} WHERE secret_code = ANY(%s)",
                    (incoming_codes,),
                )
                existing_codes = {row[0] for row in self.env.cr.fetchall()}

            now = fields.Datetime.now()
            uid = self.env.user.id
            rows = []
            for rec in records:
                secret_code = rec.get("secret_code")
                if not secret_code or secret_code in existing_codes:
                    continue

                batch_code = rec.get("batch_code")
                public_code = rec.get("public_code")
                if not batch_code or not public_code:
                    continue

                status = _normalize_status(rec.get("status"), "inactive")
                validate_status = _normalize_validate_status(rec.get("validate_status"), "pending")

                def _to_bool(v):
                    # frappe sometimes sends 0/1, "0"/"1", True/False, None
                    if v is None:
                        return False
                    if isinstance(v, bool):
                        return v
                    try:
                        return bool(int(v))
                    except Exception:
                        return str(v).strip().lower() in {"true", "yes", "y", "1"}

                rows.append(
                    (
                        batch_code,
                        secret_code,
                        str(public_code),
                        status,
                        validate_status,
                        _to_bool(rec.get("is_printed")),
                        _to_bool(rec.get("is_search_limit_reached")),
                        int(rec.get("searched_count_success") or 0),
                        int(rec.get("searched_count_fail") or 0),
                    )
                )

            if rows:
                self.env.cr.executemany(
                    """
                    INSERT INTO secret_codes
                        (batch_code, secret_code, public_code, status, validate_status,
                         is_printed, is_search_limit_reached, searched_count_success,
                         searched_count_fail, create_uid, write_uid, create_date, write_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    [row + (uid, uid, now, now) for row in rows],
                )

            # move forward
            next_page += 1
            config.set_param(FRAPPE_SECRET_CODES_NEXT_PAGE_PARAM, next_page)

            pages_done_this_run += 1
            pages_done_in_batch += 1

            # Commit + refresh every 100 pages
            if pages_done_in_batch >= pages_per_batch:
                self.env.cr.commit()
                self._notify_live_refresh()
                _logger.info(
                    "Frappe sync batch committed: %s pages. Next page=%s",
                    pages_done_in_batch,
                    next_page,
                )
                pages_done_in_batch = 0

            # if last page is smaller than FRAPPE_PAGE_SIZE, it's the end
            if len(records) < FRAPPE_PAGE_SIZE:
                config.set_param(FRAPPE_SECRET_CODES_NEXT_PAGE_PARAM, 1)
                self.env.cr.commit()
                self._notify_live_refresh()
                _logger.info(
                    "Frappe sync complete: last page size %s (<%s). Reset to page 1.",
                    len(records),
                    FRAPPE_PAGE_SIZE,
                )
                _deactivate_cron()
                break

        if stopped_for_limit:
            cron = self.env.ref('secret_codes.ir_cron_secret_codes_frappe_sync', raise_if_not_found=False)
            if cron:
                cron.sudo().write({'nextcall': fields.Datetime.now(), 'active': True})

        return True
