from odoo import api, fields, models, _

class AccountTax(models.Model):
    _inherit = 'account.tax'

    l10n_pa_edi_tax_type = fields.Many2one('account.tax.fact', string="Tipo de impuesto para facturación", 
        help="Tipo de impuesto para facturación electrónica")