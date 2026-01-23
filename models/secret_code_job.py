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
    def run_pending_jobs(self):
        job = self.search(
            [('state', 'in', ['pending', 'running'])],
            order='id',
            limit=1,
        )
        if not job:
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
                    return

                chunk_size = min(BULK_INSERT_BATCH_SIZE, remaining)
                generated_codes = set()
                secret_codes = secret_code_model._generate_secret_codes_chunk(
                    chunk_size, generated_codes
                )
                if not secret_codes:
                    job.state = 'failed'
                    job.message = 'Failed to generate unique secret codes.'
                    return

                next_public_code = secret_code_model._insert_secret_codes(
                    job.batch_code, secret_codes, int(job.last_public_code)
                )
                job.last_public_code = str(next_public_code)
                job.count_generated += len(secret_codes)

                if job.count_generated >= job.count_total:
                    job.state = 'done'
                    secret_code_model._notify_live_refresh()
                    return

                if time.monotonic() - start >= max_seconds:
                    return
        except Exception as exc:
            job.state = 'failed'
            job.message = str(exc)
            raise
