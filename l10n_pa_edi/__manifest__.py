# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    "name": "Panama Electronic Invoicing",
    'version': '18.0.1.0.1',
    'category': 'Accounting/Localizations/EDI',
    'sequence': 14,
    'author': 'MAGA System SA and e-Maanu SAS',
    'description': """
        EDI Panamenian Localization
        ===========================
        Allow the user to generate the EDI document for Panama E-invoicing.
        Development works with TheFactoryHKA WebServices

    """,
    'depends': [
        'base',
        'contacts',
        'l10n_pa',
        'sale_management',
        # 'point_of_sale'
    ],
    'external_dependencies': {
        'python': ['pyOpenSSL', 'zeep']
    },
    'data': [
        'security/localization_security.xml',
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'views/account_move_view.xml',
        'views/account_tax_views.xml',
        'views/sale_order_views.xml',
        # 'views/pos_payment_method_views.xml',
        'views/dgi_web_service_views.xml',
        'views/res_partner_views.xml',
        'views/res_partner_default_fields_views.xml',
        'views/res_city_view.xml',
        'views/product_template_view.xml',
        'views/account_tax_fact_views.xml',
        'views/log_fel_pan_views.xml',
        'views/account_journal_views.xml',
        'views/wizard_migrate_journal_sequence_views.xml',
        'views/report_account_move.xml',
        'data/paperformat.xml',
        'views/report_invoice.xml',
        'data/account_tax_fact_data.xml',
        'data/res.country.state.csv',
        'data/res.country.state.district.csv',
        'data/res.country.state.district.jurisdiction.csv',
    ],
    "post_init_hook": "post_init_hook",
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'OEEL-1',
}
