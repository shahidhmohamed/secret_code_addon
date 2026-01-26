# -*- coding: utf-8 -*-

from odoo import fields, models


class SecretCodesExportHistory(models.Model):
    _name = 'secret_codes.export_history'
    _description = 'Secret Codes Export History'
    _order = 'create_date desc'

    name = fields.Char(string='Filename', required=True)
    export_file = fields.Binary(string='Excel File', readonly=True)
    export_filename = fields.Char(string='Stored Filename', readonly=True)
    record_count = fields.Integer(string='Records Exported', readonly=True)
    public_code_from = fields.Char(string='Public Code From', readonly=True)
    public_code_to = fields.Char(string='Public Code To', readonly=True)
    count_requested = fields.Integer(string='Count Requested', readonly=True)
    range_preview = fields.Char(string='Range Preview', readonly=True)
    last_exported_code = fields.Char(string='Last Exported Code', readonly=True)
    created_by = fields.Many2one('res.users', string='Exported By', readonly=True)
    created_on = fields.Datetime(string='Exported On', readonly=True, default=fields.Datetime.now)
