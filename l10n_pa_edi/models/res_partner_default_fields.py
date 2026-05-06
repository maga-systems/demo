from odoo import api, fields, models, _

class ResPartnerAddress(models.Model):
    _name = 'res.partner.def.fields'
    _description = 'Default Address for Partners'

    company_id = fields.Many2one('res.company', string='Company', required=True, ondelete='cascade', default=lambda self: self.env.company)
    country_id = fields.Many2one('res.country', string='Country', computer=lambda self: self.env['res.country'].search([('code', 'ilike', 'PA')], limit=1).id or False, store=True)
    state_id = fields.Many2one('res.country.state', string='State', computer=lambda self: self.default_res_country_state(), store=True)
    district_id = fields.Many2one("res.country.state.district", string="District", 
        computer=lambda self: self.default_res_country_state_district(), store=True)
    jurisdiction_id = fields.Many2one("res.country.state.district.jurisdiction", string="Jurisdiction", 
        computer=lambda self: self.default_res_country_state_district_jurisdiction(), store=True)
    l10n_pa_edi_customer_type = fields.Selection([
        ('01', '01-Contribuyente'),
        ('02', '02-Consumidor Final'),
        ('03', '03-Gobierno'),
        ('04', '04-Extranjero'),
    ], string="Tipo de cliente", default="02")
    l10n_pa_edi_tipo_contribuyente = fields.Selection([
        ('1', '1-Natural'),
        ('2', '2-Jurídico'),
    ], string="Tipo de contribuyente", default="1")

    # Datos de Factura
    #Tipo de Emision
    tipoemision = fields.Selection([
        ('01', '01-Autorizacion de Uso Previa, operacion normal'),
        ('02', '02-Autorizacion de Uso Previa, operacion en contingencia'),
        ('03', '03-Autorizacion de Uso Posterior, operacion en normal'),
        ('04', '04-Autorizacion de Uso Posterior, operacion en contingencia'),
    ], string="Tipo de Emision", default="01")
    #Tipo de Documento
    tipodocumento = fields.Selection([
        ('01', '01-Factura de operación interna'),
        ('02', '02-Factura de importación'),
        ('03', '03-Factura de exportación'),
        ('04', '04-Nota de Crédito referente a una FE'),
        ('05', '05-Nota de Débito referente a una FE'),
        ('06', '06-Nota de Crédito genérica'),
        ('07', '07-Nota de Débito genérica'),
        ('08', '08-Factura de Zona Franca'),
        ('09', '09-Reembolso'),
        ('10', '10-Factura de operación extranjera'),
    ], string="Tipo de Documento", default="01")
    #Punto de Facturacion Fiscal (Char)
    puntofacturacionfiscal = fields.Char(string="Punto de Facturacion Fiscal", size=3, help="Punto de Facturacion Fiscal", default="001")
    #Detino operacion
    destinooperacion = fields.Selection([
        ('1', '1-Panamá'),
        ('2', '2-Extranjero'),
    ], string="Detino operacion", default="1")
    #Formato CAFE Sd
    formatocafe_sd = fields.Selection([
        ('1', '1-Sin generación de CAFE'),
        ('2', '2-CAFE entregado para el receptor en papel'),
        ('3', '3-CAFE enviado para el receptor en formato electrónico.'),
    ], string="Formato CAFE Sd", default="1")
    #Formato CAFE POS
    formatocafe_pos = fields.Selection([
        ('1', '1-Sin generación de CAFE'),
        ('2', '2-CAFE entregado para el receptor en papel'),
        ('3', '3-CAFE enviado para el receptor en formato electrónico.'),
    ], string="Formato CAFE POS", default="1")
    #Entrega CAFE
    entregacafe = fields.Selection([
        ('1', '1-Sin generación de CAFE'),
        ('2', '2-CAFE entregado para el receptor en papel'),
        ('3', '3-CAFE enviado para el receptor en formato electrónico.'),
    ], string="Entrega CAFE", default="1")
    #Envio Contenedor
    enviocontenedor = fields.Selection([
        ('1', '1-Normal'),
        ('2', '2-El receptor exceptúa al emisor'),
    ], string="Envio Contenedor", default="1")
    #Proceso Generacion
    procesogeneracion = fields.Char(string="Proceso Generacion", help="Proceso Generacion", default="1")

    #Tipo de Venta
    tipoventa = fields.Selection([
        ('1', '1-Venta de Giro del negocio'),
        ('2', '2-Venta Activo Fijo'),
        ('3', '3-Venta de Bienes Raíces'),
        ('4', '4-Prestación de Servicio')
    ], string="Tipo de Venta", default="1")

    @api.constrains('puntofacturacionfiscal')
    def _check_puntofacturacionfiscal(self):
        for record in self:
            if record.puntofacturacionfiscal and not record.puntofacturacionfiscal.isdigit():
                raise ValueError(_('El punto de facturación fiscal debe tener 3 caracteres'))
            if record.puntofacturacionfiscal and len(record.puntofacturacionfiscal) != 3:
                record.puntofacturacionfiscal = record.puntofacturacionfiscal.zfill(3)
    
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
        res = self.env['res.partner.def.fields'].search([
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        if not res:
            res = self.env['res.partner.def.fields'].create({
                'company_id': self.env.company.id
            })
        return {
            'name': 'Address Partner',
            'view_mode': 'form',
            'res_model': 'res.partner.def.fields',
            'type': 'ir.actions.act_window',
            'res_id': res.id,
        }
    