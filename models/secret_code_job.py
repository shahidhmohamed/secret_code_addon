# -*- coding: utf-8 -*-

import time

from odoo import api, fields, models

from .models import BULK_INSERT_BATCH_SIZE


class SecretCodeGenerationJob(models.Model):
    _name = 'secret_codes.generate_job'
    _description = 'Secret Code Generation Job'
    _rec_name = 'batch_code'

    batch_code = fields.Char(required=True)
    count_total = fields.Integer(required=True)
    count_generated = fields.Integer(default=0)
    # Store as string to avoid 32-bit integer overflow in PostgreSQL.
    last_public_code = fields.Char(required=True)
    state = fields.Selection(
        [
            ('pending', 'Pending'),
            ('running', 'Running'),
            ('done', 'Done'),
            ('failed', 'Failed'),
        ],
        default='pending',
        required=True,
    )
    message = fields.Text()

    @api.model
    def _set_generate_cron_active(self, active):
        cron = self.env.ref(
            'secret_codes.ir_cron_secret_codes_generate_job',
            raise_if_not_found=False,
        )
        if not cron:
            return
        values = {'active': bool(active)}
        if active:
            values['nextcall'] = fields.Datetime.now()
        cron.sudo().write(values)

    @api.model
    def _deactivate_generate_cron_if_idle(self):
        remaining = self.search_count([('state', 'in', ['pending', 'running'])])
        if not remaining:
            self._set_generate_cron_active(False)

    @api.model
    def run_pending_jobs(self):
        job = self.search(
            [('state', 'in', ['pending', 'running'])],
            order='id',
            limit=1,
        )
        if not job:
            self._deactivate_generate_cron_if_idle()
            return

        job.state = 'running'
        secret_code_model = self.env['secret_codes']
        start = time.monotonic()
        max_seconds = 50
        try:
            while True:
                remaining = job.count_total - job.count_generated
                if remaining <= 0:
                    job.state = 'done'
                    self._deactivate_generate_cron_if_idle()
                    return

                chunk_size = min(BULK_INSERT_BATCH_SIZE, remaining)
                generated_codes = set()
                secret_codes = secret_code_model._generate_secret_codes_chunk(
                    chunk_size, generated_codes
                )
                if not secret_codes:
                    job.state = 'failed'
                    job.message = 'Failed to generate unique secret codes.'
                    self._deactivate_generate_cron_if_idle()
                    return

                next_public_code = secret_code_model._insert_secret_codes(
                    job.batch_code, secret_codes, int(job.last_public_code)
                )
                job.last_public_code = str(next_public_code)
                job.count_generated += len(secret_codes)

                if job.count_generated >= job.count_total:
                    job.state = 'done'
                    secret_code_model._notify_live_refresh()
                    self._deactivate_generate_cron_if_idle()
                    return

                if time.monotonic() - start >= max_seconds:
                    return
        except Exception as exc:
            job.state = 'failed'
            job.message = str(exc)
            self._deactivate_generate_cron_if_idle()
            raise
