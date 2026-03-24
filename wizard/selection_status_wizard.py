# -*- coding: utf-8 -*-

from odoo import api, fields, models


class SecretCodeSelectionStatusWizard(models.TransientModel):
    _name = 'secret_codes.selection_status_wizard'
    _description = 'Selected Secret Codes Status Actions'

    selected_count = fields.Integer(readonly=True)
    can_activate_count = fields.Integer(readonly=True)
    can_deactivate_count = fields.Integer(readonly=True)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        records = self._get_selected_records()
        active_count = len(records.filtered(lambda rec: rec.status == 'active'))
        inactive_count = len(records.filtered(lambda rec: rec.status == 'inactive'))
        values.update(
            {
                'selected_count': len(records),
                'can_activate_count': inactive_count,
                'can_deactivate_count': active_count,
            }
        )
        return values

    def _get_selected_records(self):
        active_ids = self.env.context.get('active_ids') or []
        return self.env['secret_codes'].browse(active_ids).exists()

    def action_activate_selected(self):
        self.ensure_one()
        records = self._get_selected_records()
        updated = len(records.filtered(lambda rec: rec.status != 'active'))
        if updated:
            records.action_set_active_selected()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Activate',
                'message': (
                    f'Selected: {self.selected_count} | '
                    f'Can Activate: {self.can_activate_count} | Updated: {updated}.'
                ),
                'type': 'info',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

    def action_deactivate_selected(self):
        self.ensure_one()
        records = self._get_selected_records()
        updated = len(records.filtered(lambda rec: rec.status != 'inactive'))
        if updated:
            records.action_set_inactive_selected()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Deactivate',
                'message': (
                    f'Selected: {self.selected_count} | '
                    f'Can Deactivate: {self.can_deactivate_count} | Updated: {updated}.'
                ),
                'type': 'info',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }
