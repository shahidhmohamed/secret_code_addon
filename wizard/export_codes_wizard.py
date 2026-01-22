# -*- coding: utf-8 -*-

import base64
import io

from odoo import api, fields, models
from odoo.exceptions import ValidationError

try:
    import xlsxwriter  # type: ignore
except Exception:  # pragma: no cover - depends on environment
    xlsxwriter = None
from odoo.exceptions import ValidationError

from ..models.models import PUBLIC_CODE_LENGTH


class SecretCodeExportWizard(models.TransientModel):
    _name = 'secret_codes.export_wizard'
    _description = 'Export Secret Codes'

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
    count = fields.Integer(string='Export next N', default=0)
    range_preview = fields.Char(string='Range Preview', compute='_compute_range_preview')
    last_exported_code = fields.Char(string='Last Exported Code', compute='_compute_last_exported_code')

    export_file = fields.Binary(readonly=True)
    export_filename = fields.Char(readonly=True)

    def _normalize_code(self, value):
        value = (value or '').strip()
        if value.isdigit():
            return str(int(value)).zfill(PUBLIC_CODE_LENGTH)
        return value

    def _get_last_printed_public_code(self):
        self.env.cr.execute(
            """
            SELECT public_code
            FROM secret_codes
            WHERE is_printed = true
              AND public_code ~ '^[0-9]+$'
            ORDER BY CAST(public_code AS BIGINT) DESC
            LIMIT 1
            """
        )
        row = self.env.cr.fetchone()
        return row[0] if row else None

    @api.depends()
    def _compute_last_exported_code(self):
        for wizard in self:
            wizard.last_exported_code = ''
            last_code = wizard._get_last_printed_public_code()
            if last_code:
                wizard.last_exported_code = last_code

    def _get_next_records(self, limit):
        last_code = self._get_last_printed_public_code()
        if last_code:
            self.env.cr.execute(
                """
                SELECT id
                FROM secret_codes
                WHERE COALESCE(is_printed, false) = false
                  AND public_code ~ '^[0-9]+$'
                  AND CAST(public_code AS BIGINT) > CAST(%s AS BIGINT)
                ORDER BY CAST(public_code AS BIGINT)
                LIMIT %s
                """,
                (last_code, limit),
            )
        else:
            self.env.cr.execute(
                """
                SELECT id
                FROM secret_codes
                WHERE COALESCE(is_printed, false) = false
                  AND public_code ~ '^[0-9]+$'
                ORDER BY CAST(public_code AS BIGINT)
                LIMIT %s
                """,
                (limit,),
            )
        ids = [row[0] for row in self.env.cr.fetchall()]
        return self.env['secret_codes'].sudo().browse(ids)

    def _get_unprinted_numeric_count(self):
        self.env.cr.execute(
            """
            SELECT COUNT(*)
            FROM secret_codes
            WHERE is_printed = false
              AND public_code ~ '^[0-9]+$'
            """
        )
        return int(self.env.cr.fetchone()[0])

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
                available = wizard._get_unprinted_numeric_count()
                if wizard.count > available:
                    wizard.range_preview = f"Only {available} unprinted codes available."
                    continue
                records = wizard._get_next_records(wizard.count)
                if records:
                    wizard.range_preview = f"{records[0].public_code} → {records[-1].public_code}"
                else:
                    wizard.range_preview = 'No codes found.'
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
                raise ValidationError('Export next N must be at least 1.')
            available = self._get_unprinted_numeric_count()
            if self.count > available:
                raise ValidationError(f'Only {available} unprinted codes available.')
            return self._get_next_records(self.count)

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

        if from_code.isdigit() and to_code.isdigit():
            self.env.cr.execute(
                """
                SELECT id
                FROM secret_codes
                WHERE public_code ~ '^[0-9]+$'
                  AND CAST(public_code AS BIGINT) BETWEEN CAST(%s AS BIGINT) AND CAST(%s AS BIGINT)
                ORDER BY CAST(public_code AS BIGINT)
                """,
                (from_code, to_code),
            )
            ids = [row[0] for row in self.env.cr.fetchall()]
            return secret_code_model.browse(ids)

        domain = [
            ('public_code', '>=', from_code),
            ('public_code', '<=', to_code),
        ]
        return secret_code_model.search(domain, order='public_code asc')

    def action_export(self):
        self.ensure_one()
        if not xlsxwriter:
            raise ValidationError('xlsxwriter is not installed. Please install python package: xlsxwriter')
        records = self._get_target_records()
        if records:
            records.write({'is_printed': True})

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Secret Codes')
        headers = ['batch_code', 'secret_code', 'public_code']
        for col, header in enumerate(headers):
            sheet.write(0, col, header)
        row = 1
        for rec in records:
            sheet.write(row, 0, rec.batch_code or '')
            sheet.write(row, 1, rec.secret_code or '')
            sheet.write(row, 2, rec.public_code or '')
            row += 1
        workbook.close()

        data = output.getvalue()
        filename = 'secret_codes_export.xlsx'
        self.write(
            {
                'export_file': base64.b64encode(data),
                'export_filename': filename,
            }
        )
        return {
            'type': 'ir.actions.act_url',
            'url': (
                '/web/content/?model=secret_codes.export_wizard'
                f'&id={self.id}&field=export_file&filename_field=export_filename&download=true'
            ),
            'target': 'self',
        }
