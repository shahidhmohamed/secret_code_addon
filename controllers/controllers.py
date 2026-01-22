# -*- coding: utf-8 -*-

import json
import re

from odoo import http
from odoo.http import Response, request


class SecretCodeApiController(http.Controller):
    def _require_api_key(self):
        api_key = (
            request.env['ir.config_parameter']
            .sudo()
            .get_param('secret_codes.api_key')
        )
        if not api_key:
            return self._json_response({'message': 'api_key_not_configured'}, status=500)

        provided = request.httprequest.headers.get('X-API-Key')
        if not provided:
            payload = self._get_payload({})
            provided = payload.get('api_key')
        if provided != api_key:
            return self._json_response({'message': 'invalid_api_key'}, status=401)
        return None

    @http.route(
        '/secret_codes/product_offer_lead',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
    )
    def create_product_offer_lead(self, **kwargs):
        auth_error = self._require_api_key()
        if auth_error:
            return auth_error
        payload = self._get_payload(kwargs)
        email = (payload.get('email') or '').strip()
        mobile_number = (payload.get('mobile_number') or '').strip()
        secret_code = (payload.get('secret_code') or '').strip()
        verification_log = payload.get('verification_log')
        source = payload.get('source')

        if not email and not mobile_number:
            return self._json_response(
                {'message': 'email_or_mobile_required'},
                status=400,
            )
        if not secret_code:
            return self._json_response(
                {'message': 'secret_code_required'},
                status=400,
            )

        lead_model = request.env['product_offer_lead'].sudo()
        if email and mobile_number:
            search_domain = ['|', ('email', '=', email), ('mobile_number', '=', mobile_number)]
        elif email:
            search_domain = [('email', '=', email)]
        else:
            search_domain = [('mobile_number', '=', mobile_number)]

        if search_domain:
            existing = lead_model.search(search_domain)
            if existing:
                # Increment for repeat subscriptions without recomputing from row count.
                current_count = max(existing.mapped('subscribed_count') or [0])
                next_count = current_count + 1
                existing.with_context(skip_subscription_update=True).write(
                    {
                        'subscribed_count': next_count,
                        'subscription_rating': min(5.0, float(next_count)),
                    }
                )
                return self._json_response(
                    {'message': 'already_registered', 'id': existing[0].id},
                    status=200,
                )

        values = {
            'secret_code': secret_code,
            'verification_log': verification_log,
            'email': email or False,
            'mobile_number': mobile_number or False,
        }
        allowed_sources = {'PRODUCT_VERIFICATION', 'QR_SCAN', 'MANUAL'}
        if source in allowed_sources:
            values['source'] = source

        record = lead_model.create(values)
        return self._json_response({'message': 'created', 'id': record.id}, status=200)

    @http.route(
        '/secret_codes/get_secret_code_by_secret_code',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
    )
    def get_secret_code_by_secret_code(self, **kwargs):
        auth_error = self._require_api_key()
        if auth_error:
            return auth_error
        payload = self._get_payload(kwargs)
        secret_code = payload.get('secret_code')
        lat = self._to_float(payload.get('lat'))
        lng = self._to_float(payload.get('lng'))
        city = payload.get('city')
        country = payload.get('country')

        if not secret_code:
            return self._json_response({'message': 'Secret code is required.'}, status=400)

        max_searches_success = 3
        request_ip = request.httprequest.remote_addr
        user_agent = request.httprequest.headers.get('User-Agent')
        cleaned_code = str(secret_code or '').strip()
        valid_hex_16 = bool(re.match(r'^[0-9A-Fa-f]{16}$', cleaned_code))
        valid_digits_12 = bool(re.match(r'^\d{12}$', cleaned_code))

        secret_model = request.env['secret_codes'].sudo()
        log_model = request.env['secret_code_log'].sudo()

        if not (valid_hex_16 or valid_digits_12):
            invalid_message = 'invalid_code_format'
            public_match = secret_model.search([('public_code', '=', secret_code)], limit=1)
            if public_match:
                self._create_secret_code_log(
                    log_model=log_model,
                    searched_code=secret_code,
                    public_code=public_match.public_code,
                    status='rejected',
                    is_matched=True,
                    fail_reason='searched_by_public_code',
                    message='searched_by_public_code',
                    description='Searched by public code with invalid format.',
                    search_ip_address=request_ip,
                    search_device_details=user_agent,
                    search_city=city,
                    search_country=country,
                    search_latitude=lat,
                    search_longitude=lng,
                )
                return self._json_response({'message': 'searched_by_public_code'}, status=400)

            self._create_secret_code_log(
                log_model=log_model,
                searched_code=secret_code,
                status='rejected',
                is_matched=False,
                fail_reason=invalid_message,
                message=invalid_message,
                description='Invalid secret code format.',
                search_ip_address=request_ip,
                search_device_details=user_agent,
                search_city=city,
                search_country=country,
                search_latitude=lat,
                search_longitude=lng,
            )
            return self._json_response(
                {
                    'message': 'invalid_code_format',
                    'whatsapp': 'https://wa.me/971543077174',
                },
                status=400,
            )

        public_match = secret_model.search([('public_code', '=', secret_code)], limit=1)
        secret = secret_model.search([('secret_code', '=', secret_code)], limit=1)

        if not secret:
            if public_match:
                self._create_secret_code_log(
                    log_model=log_model,
                    searched_code=secret_code,
                    public_code=public_match.public_code,
                    status='rejected',
                    is_matched=True,
                    fail_reason='search_public_code',
                    message='search_public_code',
                    description='Secret code not found; public code matched.',
                    search_ip_address=request_ip,
                    search_device_details=user_agent,
                    search_city=city,
                    search_country=country,
                    search_latitude=lat,
                    search_longitude=lng,
                )
                return self._json_response({'message': 'search_public_code'}, status=400)

            self._create_secret_code_log(
                log_model=log_model,
                searched_code=secret_code,
                status='rejected',
                is_matched=False,
                fail_reason='not_found',
                message='Secret code not found',
                description='Secret code not found.',
                search_ip_address=request_ip,
                search_device_details=user_agent,
                search_city=city,
                search_country=country,
                search_latitude=lat,
                search_longitude=lng,
            )
            return self._json_response({'message': 'Secret code not found'}, status=404)

        next_fail = int(secret.searched_count_fail or 0) + 1
        next_success = int(secret.searched_count_success or 0) + 1
        is_limit_reached = bool(secret.is_search_limit_reached)

        if secret.status == 'inactive':
            secret.write({'searched_count_fail': next_fail})
            self._create_secret_code_log(
                log_model=log_model,
                searched_code=secret_code,
                public_code=secret.public_code,
                status='rejected',
                is_matched=True,
                fail_reason='inactive',
                message='Secret code is inactive',
                description='Secret code is inactive.',
                search_ip_address=request_ip,
                search_device_details=user_agent,
                search_city=city,
                search_country=country,
                search_latitude=lat,
                search_longitude=lng,
            )
            return self._json_response({'message': 'Secret code is inactive'}, status=403)

        if next_success > max_searches_success or is_limit_reached:
            secret.write(
                {
                    'searched_count_fail': next_fail,
                    'is_search_limit_reached': True,
                }
            )
            self._create_secret_code_log(
                log_model=log_model,
                searched_code=secret_code,
                public_code=secret.public_code,
                status='rejected',
                is_matched=True,
                fail_reason='search_limit_reached',
                message='Search limit reached',
                description='Search limit reached.',
                search_ip_address=request_ip,
                search_device_details=user_agent,
                search_city=city,
                search_country=country,
                search_latitude=lat,
                search_longitude=lng,
            )
            return self._json_response({'message': 'Search limit reached'}, status=403)

        secret.write(
            {
                'searched_count_success': next_success,
                'validate_status': 'validated',
            }
        )
        self._create_secret_code_log(
            log_model=log_model,
            searched_code=secret_code,
            public_code=secret.public_code,
            status='validated',
            is_matched=True,
            success_attempt=next_success,
            message='validated',
            description='Secret code validated.',
            search_ip_address=request_ip,
            search_device_details=user_agent,
            search_city=city,
            search_country=country,
            search_latitude=lat,
            search_longitude=lng,
        )

        return self._json_response(secret.read()[0], status=200)

    def _get_payload(self, kwargs):
        if request.httprequest.data:
            try:
                return json.loads(request.httprequest.data.decode('utf-8'))
            except (ValueError, UnicodeDecodeError):
                return kwargs or {}
        return kwargs or {}

    def _to_float(self, value):
        if value in (None, ''):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _create_secret_code_log(self, log_model, **values):
        log_model.create(values)

    def _json_response(self, payload, status=200):
        return Response(
            json.dumps(payload, default=str),
            status=status,
            content_type='application/json',
        )
