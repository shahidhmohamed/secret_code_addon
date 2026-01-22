# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from ..models.models import PUBLIC_CODE_LENGTH


class SecretCodeBulkActivateWizard(models.TransientModel):
    _name = 'secret_codes.bulk_activate_wizard'
    _description = 'Bulk Secret Code Actions'

    public_code_from_id = fields.Many2one(
        'secret_codes',
        string='Public Code From',
    )
    public_code_to_id = fields.Many2one(
        'secret_codes',
        string='Public Code To',
    )
    public_code_from = fields.Char()
    public_code_to = fields.Char()
    count = fields.Integer(string='Activate next N', default=0)
    range_preview = fields.Char(string='Range Preview', compute='_compute_range_preview')

    def _normalize_code(self, value):
        value = (value or '').strip()
        if value.isdigit():
            return str(int(value)).zfill(PUBLIC_CODE_LENGTH)
        return value

    def _get_next_records(self, limit):
        secret_code_model = self.env['secret_codes'].sudo()
        last_printed = secret_code_model.search(
            [('is_printed', '=', True)],
            order='write_date desc, id desc',
            limit=1,
        )
        if last_printed:
            domain = [
                ('status', '=', 'inactive'),
                ('id', '>', last_printed.id),
            ]
        else:
            domain = [('status', '=', 'inactive')]
        return secret_code_model.search(domain, order='id asc', limit=limit)

    @api.depends(
        'count',
        'public_code_from_id',
        'public_code_to_id',
        'public_code_from',
        'public_code_to',
    )
    def _compute_range_preview(self):
        for wizard in self:
            wizard.range_preview = ''
            if wizard.count and wizard.count > 0:
                records = wizard._get_next_records(wizard.count)
                if records:
                    wizard.range_preview = f"{records[0].public_code} → {records[-1].public_code}"
                else:
                    wizard.range_preview = 'No inactive codes found.'
                continue

            from_code = wizard.public_code_from_id.public_code if wizard.public_code_from_id else wizard.public_code_from
            to_code = wizard.public_code_to_id.public_code if wizard.public_code_to_id else wizard.public_code_to
            from_code = wizard._normalize_code(from_code)
            to_code = wizard._normalize_code(to_code)
            if from_code and to_code:
                wizard.range_preview = f"{from_code} → {to_code}"

    @api.onchange(
        'count',
        'public_code_from_id',
        'public_code_to_id',
        'public_code_from',
        'public_code_to',
    )
    def _onchange_range_preview(self):
        self._compute_range_preview()

    def _get_target_records(self):
        if self.count and (self.public_code_from or self.public_code_to or self.public_code_from_id or self.public_code_to_id):
            raise ValidationError('Use either range or count, not both.')

        secret_code_model = self.env['secret_codes'].sudo()

        if self.count:
            if self.count < 1:
                raise ValidationError('Activate next N must be at least 1.')
            last_printed = secret_code_model.search(
                [('is_printed', '=', True)],
                order='write_date desc, id desc',
                limit=1,
            )
            if last_printed:
                domain = [
                    ('status', '=', 'inactive'),
                    ('id', '>', last_printed.id),
                ]
            else:
                domain = [('status', '=', 'inactive')]

            return secret_code_model.search(
                domain,
                order='id asc',
                limit=self.count,
            )

        from_code = self.public_code_from_id.public_code if self.public_code_from_id else self.public_code_from
        to_code = self.public_code_to_id.public_code if self.public_code_to_id else self.public_code_to
        from_code = self._normalize_code(from_code)
        to_code = self._normalize_code(to_code)

        if not from_code or not to_code:
            raise ValidationError('Both start and end public codes are required.')

        if from_code.isdigit() and to_code.isdigit():
            if int(from_code) > int(to_code):
                raise ValidationError(
                    'Start public code must be less than or equal to end public code.'
                )

        domain = [
            ('status', '=', 'inactive'),
            ('public_code', '>=', from_code),
            ('public_code', '<=', to_code),
        ]
        return secret_code_model.search(domain)

    def _apply_status(self, status):
        self.ensure_one()
        records = self._get_target_records()
        if records:
            records.write({'status': status})
        return len(records)

    def action_activate_range(self):
        updated = self._apply_status('active')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Bulk activate',
                'message': f'Updated {updated} code(s) to ACTIVE.',
                'type': 'info',
                'sticky': False,
            },
        }

    def action_deactivate_range(self):
        updated = self._apply_status('inactive')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Bulk deactivate',
                'message': f'Updated {updated} code(s) to INACTIVE.',
                'type': 'info',
                'sticky': False,
            },
        }
