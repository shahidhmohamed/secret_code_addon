# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import AccessDenied, ValidationError


class SecretCodeViewWizard(models.TransientModel):
    _name = 'secret_codes.view_secret_code_wizard'
    _description = 'View Secret Code'

    secret_code_id = fields.Many2one('secret_codes', required=True, readonly=True)
    password = fields.Char(required=True, password=True)
    revealed_secret_code = fields.Char(readonly=True)

    def action_reveal(self):
        self.ensure_one()
        try:
            user = self.env.user
            try:
                user._check_credentials(
                    {'type': 'password', 'password': self.password, 'login': user.login},
                    {'interactive': True},
                )
            except TypeError:
                # Fallback for older signature.
                user._check_credentials(self.password, {'interactive': True})
        except Exception as exc:
            if isinstance(exc, AccessDenied):
                raise ValidationError('Invalid password.')
            raise

        self.revealed_secret_code = self.secret_code_id.secret_code
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'secret_codes.view_secret_code_wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
