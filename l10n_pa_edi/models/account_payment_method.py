from odoo import fields, models

class AccountPaymentMethod(models.Model):
    _inherit = 'account.payment.method'

    l10n_pa_dgi_payment_code = fields.Selection([
        ('01', 'Crédito'),
        ('02', 'Efectivo'),
        ('03', 'Tarjeta Crédito'),
        ('04', 'Tarjeta Débito'),
        ('05', 'Tarjeta Fidelización'),
        ('06', 'Vale'),
        ('07', 'Tarjeta de Regalo'),
        ('08', 'Transferencia / Depósito Bancario'),
        ('09', 'Cheque'),
        ('99', 'Otro'),
    ], string='Forma de pago DGI (Panamá)')
