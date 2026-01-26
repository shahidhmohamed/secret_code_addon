import json
import logging
import time

import requests

from odoo import api, fields, models

FRAPPE_BASE_URL = 'https://ghori.u.frappe.cloud'
# FRAPPE_BASE_URL = 'https://stagingghori.u.frappe.cloud'
FRAPPE_API_KEY = '1671f30aad9dd4f'
# FRAPPE_API_KEY = 'fa62fba39461c4f'
FRAPPE_API_SECRET = '9ffdd149d876332'
# FRAPPE_API_SECRET = 'ba1c168e024aea5'
FRAPPE_PAGE_SIZE = 100
FRAPPE_TIMEOUT_SECONDS = 120
FRAPPE_MAX_RETRIES = 3
FRAPPE_RETRY_BACKOFF_SECONDS = 2
FRAPPE_MAX_RUNTIME_SECONDS = 900
FRAPPE_PRODUCT_OFFER_LEADS_DOCTYPE = 'Product Offer Leads'

_logger = logging.getLogger(__name__)

class ProductOfferLead(models.Model):
    _name = 'product_offer_lead'
    _description = 'Product Offer Lead'
    _rec_name = 'email'
    _order = 'write_date desc'

    frappe_name = fields.Char(index=True)
    frappe_creation = fields.Datetime()

    secret_code = fields.Char(required=True, index=True)
    verification_log = fields.Char()
    email = fields.Char(index=True)
    mobile_number = fields.Char(index=True)
    source = fields.Selection(
        [
            ('PRODUCT_VERIFICATION', 'PRODUCT_VERIFICATION'),
            ('QR_SCAN', 'QR_SCAN'),
            ('MANUAL', 'MANUAL'),
        ],
        default='PRODUCT_VERIFICATION',
    )
    subscribed_count = fields.Integer(string='Subscribed Count', default=0)
    subscription_rating = fields.Float(string='Subscription Rating', default=0.0)
    subscription_rating_stars = fields.Char(
        compute='_compute_subscription_rating_stars',
        string='Subscription Rating',
        store=True,
    )
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
        if not self.env.context.get('skip_subscription_update'):
            pairs = {(rec.email, rec.mobile_number) for rec in records}
            for email, mobile in pairs:
                self._update_subscription_metrics_for(email, mobile)
        return records

    def write(self, vals):
        old_pairs = {(rec.email, rec.mobile_number) for rec in self}
        result = super().write(vals)
        self._notify_live_refresh()
        if not self.env.context.get('skip_subscription_update') and (
            'email' in vals or 'mobile_number' in vals
        ):
            new_pairs = {(rec.email, rec.mobile_number) for rec in self}
            for email, mobile in old_pairs.union(new_pairs):
                self._update_subscription_metrics_for(email, mobile)
        return result

    @api.depends('subscription_rating')
    def _compute_subscription_rating_stars(self):
        for record in self:
            rating = int(round(record.subscription_rating or 0))
            rating = max(0, min(5, rating))
            filled = '★'
            empty = '☆'
            record.subscription_rating_stars = (filled * rating) + (empty * (5 - rating))

    @api.depends('write_date')
    def _compute_is_last_updated(self):
        latest = self.search([], order='write_date desc, id desc', limit=1)
        latest_id = latest.id if latest else False
        for record in self:
            record.is_last_updated = bool(latest_id and record.id == latest_id)

    @api.model
    def _update_subscription_metrics_for(self, email, mobile):
        domain = []
        if email and mobile:
            domain = ['|', ('email', '=', email), ('mobile_number', '=', mobile)]
        elif email:
            domain = [('email', '=', email)]
        elif mobile:
            domain = [('mobile_number', '=', mobile)]
        else:
            return

        records = self.search(domain)
        count = len(records)
        rating = min(5.0, float(count))
        records.with_context(skip_subscription_update=True).write(
            {
                'subscribed_count': count,
                'subscription_rating': rating,
            }
        )

    def action_sync_frappe_product_offer_leads(self):
        return self.sync_frappe_product_offer_leads()

    def action_recompute_subscription_metrics(self):
        self._recompute_subscription_metrics()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Recompute completed',
                'message': 'Subscribed counts and ratings updated.',
                'type': 'info',
                'sticky': False,
            },
        }

    def _recompute_subscription_metrics(self):
        self.env.cr.execute(
            """
            UPDATE product_offer_lead
            SET subscribed_count = (
                SELECT count(*)
                FROM product_offer_lead p2
                WHERE (product_offer_lead.email IS NOT NULL AND p2.email = product_offer_lead.email)
                   OR (product_offer_lead.mobile_number IS NOT NULL
                       AND p2.mobile_number = product_offer_lead.mobile_number)
            )
            """
        )
        self.env.cr.execute(
            """
            UPDATE product_offer_lead
            SET subscription_rating = LEAST(5.0, subscribed_count::float),
                subscription_rating_stars = repeat('★', LEAST(5, subscribed_count))
                                           || repeat('☆', 5 - LEAST(5, subscribed_count))
            """
        )
        self._invalidate_cache()

    @api.model
    def sync_frappe_product_offer_leads(self, *args, **kwargs):
        page = 1
        start_time = time.monotonic()

        url = f"{FRAPPE_BASE_URL.rstrip('/')}/api/method/frappe.client.get_list"
        headers = {"Authorization": f"token {FRAPPE_API_KEY}:{FRAPPE_API_SECRET}"}
        fields_list = [
            "name",
            "secret_code",
            "verification_log",
            "email",
            "mobile_number",
            "source",
            "creation",
        ]
        allowed_sources = {"PRODUCT_VERIFICATION", "QR_SCAN", "MANUAL"}

        def _normalize_frappe_datetime(value):
            if not value:
                return False
            value = str(value).strip()
            return value[:19] if len(value) > 19 else value

        while True:
            if time.monotonic() - start_time > FRAPPE_MAX_RUNTIME_SECONDS:
                _logger.info("Frappe leads manual sync paused after max runtime at page %s.", page)
                break

            params = {
                "doctype": FRAPPE_PRODUCT_OFFER_LEADS_DOCTYPE,
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
                        "Frappe leads manual sync retry %s on page %s due to error: %s",
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
                _logger.info("Frappe leads manual sync complete: no records at page %s.", page)
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

                secret_code = rec.get("secret_code")
                if not secret_code:
                    continue

                source = rec.get("source")
                create_vals.append(
                    {
                        "frappe_name": frappe_name,
                        "frappe_creation": _normalize_frappe_datetime(rec.get("creation")),
                        "secret_code": secret_code,
                        "verification_log": rec.get("verification_log"),
                        "email": rec.get("email") or False,
                        "mobile_number": rec.get("mobile_number") or False,
                        "source": source if source in allowed_sources else "PRODUCT_VERIFICATION",
                    }
                )

            if create_vals:
                self.sudo().create(create_vals)

            page += 1

        self._recompute_subscription_metrics()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sync completed',
                'message': 'Frappe leads sync finished.',
                'type': 'info',
                'sticky': False,
            },
        }
