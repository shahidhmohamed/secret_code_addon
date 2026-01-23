# -*- coding: utf-8 -*-
import json
from odoo import api, fields, models

class SecretCodesDashboard(models.TransientModel):
    _name = 'secret_codes.dashboard'
    _description = 'Secret Codes Dashboard'

    # Stats Fields
    total_codes = fields.Integer(compute='_compute_dashboard_data')
    total_active = fields.Integer(compute='_compute_dashboard_data')
    total_inactive = fields.Integer(compute='_compute_dashboard_data')
    total_validated = fields.Integer(compute='_compute_dashboard_data')
    total_pending = fields.Integer(compute='_compute_dashboard_data')
    total_success = fields.Integer(compute='_compute_dashboard_data')
    total_fail = fields.Integer(compute='_compute_dashboard_data')
    total_offer_leads = fields.Integer(compute='_compute_dashboard_data')
    total_subscribed = fields.Integer(compute='_compute_dashboard_data')
    total_search_locations = fields.Integer(compute='_compute_dashboard_data')
    total_logs = fields.Integer(compute='_compute_dashboard_data')
    total_validated_logs = fields.Integer(compute='_compute_dashboard_data')
    total_rejected_logs = fields.Integer(compute='_compute_dashboard_data')
    total_pending_logs = fields.Integer(compute='_compute_dashboard_data')

    # Chart Fields
    graph_status_data = fields.Text(compute='_compute_dashboard_data')
    graph_search_trends = fields.Text(compute='_compute_dashboard_data')

    def _compute_dashboard_data(self):
        for rec in self:
            # Models
            secret_model = self.env['secret_codes'].sudo()
            lead_model = self.env['product_offer_lead'].sudo()
            log_model = self.env['secret_code_log'].sudo()
            log_date_domain = []

            # Stats Calculation
            rec.total_codes = secret_model.search_count([])
            rec.total_active = secret_model.search_count([('status', '=', 'active')])
            rec.total_inactive = secret_model.search_count([('status', '=', 'inactive')])
            rec.total_validated = secret_model.search_count([('validate_status', '=', 'validated')])
            rec.total_pending = secret_model.search_count([('validate_status', '=', 'pending')])

            # Aggregated Stats
            rec.total_success = sum(secret_model.mapped('searched_count_success') or [0])
            rec.total_fail = sum(secret_model.mapped('searched_count_fail') or [0])
            rec.total_offer_leads = lead_model.search_count([])
            rec.total_subscribed = sum(lead_model.mapped('subscribed_count') or [0])
            rec.total_search_locations = log_model.search_count([
                ('search_latitude', '!=', False), 
                ('search_longitude', '!=', False)
            ])
            rec.total_logs = log_model.search_count(log_date_domain)
            rec.total_validated_logs = log_model.search_count(log_date_domain + [('status', '=', 'validated')])
            rec.total_rejected_logs = log_model.search_count(log_date_domain + [('status', '=', 'rejected')])
            rec.total_pending_logs = log_model.search_count(log_date_domain + [('status', '=', 'pending')])

            # 1. DONUT CHART DATA
            rec.graph_status_data = json.dumps([{
                'values': [
                    {'label': 'Active', 'value': rec.total_active},
                    {'label': 'Inactive', 'value': rec.total_inactive},
                    {'label': 'Pending', 'value': rec.total_pending}
                ],
                'area': True,
                'title': '',
            }])

            # 2. BAR CHART DATA
            rec.graph_search_trends = json.dumps([{
                'key': 'Performance',
                'values': [
                    {'label': 'Success', 'value': rec.total_success},
                    {'label': 'Failed', 'value': rec.total_fail},
                ]
            }])

    # Actions for clickable cards
    def action_open_all(self):
        return self._action_view('secret_codes', [])

    def action_open_active(self):
        return self._action_view('secret_codes', [('status', '=', 'active')])

    def action_open_pending(self):
        return self._action_view('secret_codes', [('validate_status', '=', 'pending')])

    def action_open_leads(self):
        return self._action_view('product_offer_lead', [])

    def _action_view(self, model, domain):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Details',
            'res_model': model,
            'view_mode': 'tree,form',
            'domain': domain,
            'target': 'current',
        }

    @api.model
    def get_metrics(self, date_from=None, date_to=None):
        secret_model = self.env['secret_codes'].sudo()
        lead_model = self.env['product_offer_lead'].sudo()
        log_model = self.env['secret_code_log'].sudo()
        if date_from and date_to:
            log_date_domain = [
                ('create_date', '>=', date_from),
                ('create_date', '<=', date_to),
            ]
        else:
            log_date_domain = []

        logs = log_model.search(log_date_domain + [
            ('search_latitude', '!=', False),
            ('search_longitude', '!=', False),
            ('search_latitude', '!=', 0.0),
            ('search_longitude', '!=', 0.0),
        ], order="create_date desc")
        map_points = [
            {
                'lat': float(log.search_latitude),
                'lng': float(log.search_longitude),
                'status': log.status,
            }
            for log in logs
            if log.search_latitude and log.search_longitude
        ]

        return {
            'total_codes': secret_model.search_count([]),
            'total_active': secret_model.search_count([('status', '=', 'active')]),
            'total_inactive': secret_model.search_count([('status', '=', 'inactive')]),
            'total_validated': secret_model.search_count([('validate_status', '=', 'validated')]),
            'total_pending': secret_model.search_count([('validate_status', '=', 'pending')]),
            'total_success': sum(secret_model.mapped('searched_count_success') or [0]),
            'total_fail': sum(secret_model.mapped('searched_count_fail') or [0]),
            'total_offer_leads': lead_model.search_count([]),
            'total_subscribed': sum(lead_model.mapped('subscribed_count') or [0]),
            'total_search_locations': log_model.search_count([
                ('search_latitude', '!=', False),
                ('search_longitude', '!=', False),
            ]),
            'total_logs': log_model.search_count(log_date_domain),
            'total_validated_logs': log_model.search_count(log_date_domain + [('status', '=', 'validated')]),
            'total_rejected_logs': log_model.search_count(log_date_domain + [('status', '=', 'rejected')]),
            'total_pending_logs': log_model.search_count(log_date_domain + [('status', '=', 'pending')]),
            'map_points': map_points,
        }
