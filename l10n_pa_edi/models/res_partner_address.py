from odoo import api, fields, models, _

class ResPartnerAddress(models.Model):
    _name = 'res.partner.def.address'
    _description = 'Default Address for Partners'

    company_id = fields.Many2one('res.company', string='Company', required=True, ondelete='cascade', default=lambda self: self.env.company)
    country_id = fields.Many2one('res.country', string='Country', computer=lambda self: self.env['res.country'].search([('code', 'ilike', 'PA')], limit=1).id or False, store=True)
    state_id = fields.Many2one('res.country.state', string='State', computer=lambda self: self.default_res_country_state(), store=True,
        domain="[('country_id', '=', country_id)]")
    district_id = fields.Many2one("res.country.state.district", string="District", domain="[('state_id','=',state_id)]",
        computer=lambda self: self.default_res_country_state_district(), store=True)
    jurisdiction_id = fields.Many2one("res.country.state.district.jurisdiction", string="Jurisdiction", domain="[('district_id','=', district_id)]",
        computer=lambda self: self.default_res_country_state_district_jurisdiction(), store=True)
    l10n_pa_edi_customer_type = fields.Selection([
        ('01', 'Contribuyente'),
        ('02', 'Consumidor Final'),
        ('03', 'Gobierno'),
        ('04', 'Extranjero'),
    ], string="Tipo de cliente", default="01", store=True)
    l10n_pa_edi_tipo_contribuyente = fields.Selection([
        ('1', 'Natural'),
        ('2', 'Jurídico'),
    ], string="Tipo de contribuyente", default="2", store=True)
    @api.model
    def default_res_country_state(self):
        return self.env['res.country.state'].search([('name', '=', 'PANAMA')], limit=1).id or False
    
    @api.model
    def default_res_country_state_district(self):
        return self.env['res.country.state.district'].search([('name', '=', 'PANAMA')], limit=1).id or False
    
    @api.model
    def default_res_country_state_district_jurisdiction(self):
        return self.env['res.country.state.district.jurisdiction'].search([('name', '=', 'PUEBLO NUEVO')], limit=1).id or False

    def open_view_res_country(self):
        res = self.env['res.partner.def.address'].search([
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        if not res:
            res = self.env['res.partner.def.address'].create({
                'company_id': self.env.company.id
            })
        return {
            'name': 'Address Partner',
            'view_mode': 'form',
            'res_model': 'res.partner.def.address',
            'type': 'ir.actions.act_window',
            'res_id': res.id,
        }