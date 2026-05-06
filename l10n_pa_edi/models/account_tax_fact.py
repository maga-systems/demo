from odoo import api, fields, models, _


_type_tax = [
        ('itbms', 'ITBMS'),
        ('oti', 'OTI'),
        ('isc', 'ISC')
    ] 

class AccountTaxFact(models.Model):
    _name = 'account.tax.fact'

    l10n_pa_edi_tax_type = fields.Selection(
        _type_tax, string="Tipo de impuesto para facturación", store=True,
        help="Tipo de impuesto para facturación electrónica", required=True)

    l10n_pa_edi_tax_code = fields.Char(string="Código de impuesto", 
        help="Código de impuesto para facturación electrónica")
    
    l10n_pa_edi_tax_rate = fields.Float(string="Tasa de impuesto",
        help="Tasa de impuesto para facturación electrónica")
    
    l10n_pa_edi_tax_name = fields.Char(string='Nombre', required=True)
    
    name = fields.Char(string='Nombre', compute='_compute_name' )

    @api.depends('l10n_pa_edi_tax_type', 'l10n_pa_edi_tax_name')
    def _compute_name(self):
        for tax_a in self:
            type_tax = dict(_type_tax)
            tax_a.name = f"{type_tax.get(str(tax_a.l10n_pa_edi_tax_type), '')} - {tax_a.l10n_pa_edi_tax_name or ''}"

    @api.onchange('l10n_pa_edi_tax_name')
    def _onchange_l10n_pa_edi_tax_name(self):
        if self.l10n_pa_edi_tax_rate == False and self.l10n_pa_edi_tax_name:
            # buscar el signo de porcentaje y tomar el valor
            name = self.l10n_pa_edi_tax_name
            if '%' in name:
                name = name.split('%')[0]
                lista_char = []
                for char in name:
                    if char.isdigit() or char == '.':
                        lista_char.append(char)
                if lista_char:
                    self.l10n_pa_edi_tax_rate = float(''.join(lista_char)) / 100
       