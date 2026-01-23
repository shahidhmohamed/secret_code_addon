# -*- coding: utf-8 -*-
{
    'name': "Secret Codes",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
        Long description of module's purpose
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'bus', 'web'],
    'application': True,

    # always loaded
    'data': [
        'security/secret_codes_groups.xml',
        'security/ir.model.access.csv',
        'data/cron.xml',
        'views/generate_wizard.xml',
        'views/bulk_actions_wizard.xml',
        'views/export_codes_wizard.xml',
        'views/view_secret_code_wizard.xml',
        'views/view_location_wizard.xml',
        'views/secret_codes.xml',
        'views/secret_code_logs.xml',
        'views/product_offer_leads.xml',
        'views/dashboard.xml',
        'views/templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'secret_codes/static/src/js/secret_codes_live_refresh.js',
            'secret_codes/static/src/scss/dashboard.scss',
            'secret_codes/static/src/components/kpi_card/kpi_card.js',
            'secret_codes/static/src/components/kpi_card/kpi_card.xml',
            'secret_codes/static/src/components/chart_renderer/chart_renderer.js',
            'secret_codes/static/src/components/chart_renderer/chart_renderer.xml',
            'secret_codes/static/src/components/map_card/map_card.js',
            'secret_codes/static/src/components/map_card/map_card.xml',
            'secret_codes/static/src/dashboard/dashboard.js',
            'secret_codes/static/src/dashboard/dashboard.xml',
        ],
    },
    'external_dependencies': {
        'python': ['xlsxwriter'],
    },
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}
