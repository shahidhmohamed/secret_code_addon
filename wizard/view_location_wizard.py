# -*- coding: utf-8 -*-

from odoo import api, fields, models


class SecretCodeLogLocationWizard(models.TransientModel):
    _name = 'secret_codes.view_location_wizard'
    _description = 'View Log Location'

    latitude = fields.Float(readonly=True)
    longitude = fields.Float(readonly=True)
    map_url = fields.Char(readonly=True)
    map_embed = fields.Html(readonly=True, sanitize=False)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        lat = res.get('latitude')
        lng = res.get('longitude')
        if lat is not None and lng is not None:
            url = f"https://www.google.com/maps?q={lat},{lng}"
            res['map_url'] = url
            res['map_embed'] = (
                f"<iframe width='100%' height='360' frameborder='0' "
                f"style='border:0' src='https://www.google.com/maps?q={lat},{lng}&output=embed' "
                f"allowfullscreen></iframe>"
            )
        return res
