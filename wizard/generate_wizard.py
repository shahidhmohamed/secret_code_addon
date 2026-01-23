# -*- coding: utf-8 -*-

from odoo import api, fields, models

from ..models.models import BULK_INSERT_BATCH_SIZE


class SecretCodeGenerateWizard(models.TransientModel):
    _name = 'secret_codes.generate_wizard'
    _description = 'Generate Secret Codes'

    count = fields.Integer(string='How many codes?', required=True)
    batch_code = fields.Char(required=True, default=lambda self: self._default_batch_code())
    run_in_background = fields.Boolean(default=True)

    @api.model
    def _default_batch_code(self):
        return self.env['secret_codes'].generate_next_batch_code()

    def action_generate(self):
        self.ensure_one()
        secret_code_model = self.env['secret_codes']

        if self.run_in_background or self.count > BULK_INSERT_BATCH_SIZE:
            job = self.env['secret_codes.generate_job'].create(
                {
                    'batch_code': self.batch_code,
                    'count_total': self.count,
                    'last_public_code': str(secret_code_model._get_next_public_code()),
                }
            )
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Generation queued',
                    'message': (
                        f'Job {job.batch_code} queued for {job.count_total} codes.'
                    ),
                    'sticky': False,
                },
            }

        remaining = self.count
        next_public_code = secret_code_model._get_next_public_code()
        generated_codes = set()
        while remaining > 0:
            chunk_size = min(BULK_INSERT_BATCH_SIZE, remaining)
            secret_codes = secret_code_model._generate_secret_codes_chunk(
                chunk_size, generated_codes
            )
            if not secret_codes:
                break
            next_public_code = secret_code_model._insert_secret_codes(
                self.batch_code, secret_codes, next_public_code
            )
            remaining -= len(secret_codes)

        secret_code_model._notify_live_refresh()
        return {'type': 'ir.actions.act_window_close'}
