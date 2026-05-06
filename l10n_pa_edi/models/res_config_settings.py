# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import re
import zeep
import logging

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_pa_use_cfe = fields.Boolean(
        string='¿Utiliza facturación electrónica?', related='company_id.l10n_pa_use_cfe', readonly=False)
    l10n_pa_ws_environment = fields.Many2one(
        'dgi.web.service', string='Environment', related='company_id.l10n_pa_ws_environment_id', readonly=False)
    l10n_pa_ws_user_fname = fields.Char(
        string='User name', related='l10n_pa_ws_environment.ws_user_fname', readonly=False)
    l10n_pa_ws_token_fname = fields.Char(
        string='Token', related='l10n_pa_ws_environment.ws_token_fname', readonly=False)
    l10n_pa_ws_wsdl_url = fields.Char(
        string='WSDL', related='l10n_pa_ws_environment.ws_wsdl_url', readonly=False)

    res_partner_def_fields = fields.Many2one(
        'res.partner.def.fields', string='Default Address', default=lambda self: self.env.company.def_fields_part.id, readonly=False)
    
    def_fel_country_id = fields.Many2one(
        'res.country',
        string='Country',
        # default=lambda self: self.env.ref('base.pa'),
        readonly=False)
    def_fel_state_id = fields.Many2one(
        'res.country.state', string='State', 
        # default=lambda self: self.env['res.country.state'].search([('name', '=', 'PANAMA')], limit=1).id,
        readonly=False,
        domain="[('country_id', '=', def_fel_country_id)]"
    )
    def_fel_district_id = fields.Many2one(
        'res.country.state.district',
        string='District',
        # default=lambda self: self.env['res.country.state.district'].search([('name', '=', 'PANAMA')], limit=1).id,
        readonly=False,
        domain="[('state_id', '=', def_fel_state_id)]"
    )
    def_fel_jurisdiction_id = fields.Many2one(
        'res.country.state.district.jurisdiction',
        string='Jurisdiction',
        # default=lambda self: self.env['res.country.state.district.jurisdiction'].search([('name', '=', 'PARQUE LEFEVRE')], limit=1).id,
        readonly=False,
        domain="[('district_id', '=', def_fel_district_id)]"
    )
    def_fel_l10n_pa_edi_customer_type = fields.Selection([
        ('01', '01-Contribuyente'),
        ('02', '02-Consumidor Final'),
        ('03', '03-Gobierno'),
        ('04', '04-Extranjero'),
    ], string="Tipo de cliente", default="02", readonly=False)
    def_fel_l10n_pa_edi_tipo_contribuyente = fields.Selection([
        ('1', '1-Natural'),
        ('2', '2-Jurídico'),
    ], string="Tipo de contribuyente", default="1", readonly=False)
    def_tipoemision = fields.Selection([
        ('01', '01-Autorizacion de Uso Previa, operacion normal'),
        ('02', '02-Autorizacion de Uso Previa, operacion en contingencia'),
        ('03', '03-Autorizacion de Uso Posterior, operacion en normal'),
        ('04', '04-Autorizacion de Uso Posterior, operacion en contingencia'),
    ], string="Tipo de Emision", default="01", readonly=False)
    def_tipodocumento = fields.Selection([
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
    ], string="Tipo de Documento", default="01", readonly=False)
    def_puntofacturacionfiscal = fields.Char(string="Punto de Facturacion Fiscal", size=3, help="Punto de Facturacion Fiscal", default="001", readonly=False)
    def_destinooperacion = fields.Selection([
        ('1', '1-Panamá'),
        ('2', '2-Extranjero'),
    ], string="Detino operacion", default="1", readonly=False)
    def_formatocafe_sd = fields.Selection([
        ('1', '1-Sin generación de CAFE'),
        ('2', '2-CAFE entregado para el receptor en papel'),
        ('3', '3-CAFE enviado para el receptor en formato electrónico.'),
    ], string="Formato CAFE Sd", default="1", readonly=False)
    def_formatocafe_pos = fields.Selection([
        ('1', '1-Sin generación de CAFE'),
        ('2', '2-CAFE entregado para el receptor en papel'),
        ('3', '3-CAFE enviado para el receptor en formato electrónico.'),
    ], string="Formato CAFE POS", default="1", readonly=False)
    def_entregacafe = fields.Selection([
        ('1', '1-Sin generación de CAFE'),
        ('2', '2-CAFE entregado para el receptor en papel'),
        ('3', '3-CAFE enviado para el receptor en formato electrónico.'),
    ], string="Entrega CAFE", default='1', readonly=False)
    def_enviocontenedor = fields.Selection([
        ('1', '1-Normal'),
        ('2', '2-El receptor exceptúa al emisor'),
    ], string="Envio contenedor", default="1", readonly=False)
    def_procesogeneracion = fields.Char(string="Proceso de Generacion", help="Proceso Generacion", default="1", readonly=False)
    def_tipoventa = fields.Selection([
        ('1', '1-Venta de Giro del negocio'),
        ('2', '2-Venta Activo Fijo'),
        ('3', '3-Venta de Bienes Raíces'),
        ('4', '4-Prestación de Servicio')
    ], string="Tipo de Venta", default="1", readonly=False)
        
    
    @api.depends('company_id')
    def _get_res_partner_def_fields(self):
        for rec in self:
            res = rec.company_id.def_fields_part
            rec.res_partner_def_fields = res.id
            


    def l10n_pa_connection_test(self):
        self.ensure_one()
        error = ''
        if not self.l10n_pa_ws_user_fname:
            error += '\n* ' + \
                _('Please set a User Name in order to make the test')
        if not self.l10n_pa_ws_token_fname:
            error += '\n* ' + _('Please set a Token in order to make the test')
        if not self.l10n_pa_ws_wsdl_url:
            error += '\n* ' + _('Please set a WSDL in order to make the test')
        if error:
            raise UserError(error)
        _logger.info(f'Connection test: {self.l10n_pa_ws_wsdl_url}')
        try:
            cliente = zeep.Client(wsdl=self.l10n_pa_ws_wsdl_url)
            datos = {
                "consultarRucDVRequest": {
                    "tokenEmpresa": str(self.env.company.l10n_pa_ws_user_fname),
                    "tokenPassword": str(self.env.company.l10n_pa_ws_token_fname),
                    "tipoRuc": "1",
                    "ruc": "RUC",
                }
            }
            _logger.info(f'Connection test: {datos}')
            req = cliente.service.ConsultarRucDV(**datos)
            if not req or req['codigo'] == '100':
                _logger.error(f'Error: {req}')
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': _('Connection failed: %s') % req['mensaje'],
                        'type': 'danger',
                        'sticky': False,
                    }
                }
            res = ''
            res += ('\n* : ' + _('Connection is available'))
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': res,
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            _logger.error(e)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _('Connection failed: %s') % e,
                    'type': 'danger',
                    'sticky': False,
                }
            }

    def random_demo_cert(self):
        self.company_id.set_demo_random_cert()

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        _logger.info("Ejecutando set_values con datos:")
        _logger.info(f"País: {self.def_fel_country_id}, Estado: {self.def_fel_state_id}")
        self.company_id.write({
            'l10n_pa_use_cfe': self.l10n_pa_use_cfe,
            'l10n_pa_ws_environment_id': self.l10n_pa_ws_environment.id,
            'l10n_pa_ws_user_fname': self.l10n_pa_ws_user_fname,
            'l10n_pa_ws_token_fname': self.l10n_pa_ws_token_fname,
            'l10n_pa_ws_wsdl_url': self.l10n_pa_ws_wsdl_url,
        })
        self.company_id.def_fields_part.write({
            'country_id': self.def_fel_country_id,
            'state_id': self.def_fel_state_id.id,
            'district_id': self.def_fel_district_id.id,
            'jurisdiction_id': self.def_fel_jurisdiction_id.id,
            'l10n_pa_edi_customer_type': self.def_fel_l10n_pa_edi_customer_type,
            'l10n_pa_edi_tipo_contribuyente': self.def_fel_l10n_pa_edi_tipo_contribuyente,
            'tipoemision': self.def_tipoemision,
            'tipodocumento': self.def_tipodocumento,
            'puntofacturacionfiscal': self.def_puntofacturacionfiscal,
            'destinooperacion': self.def_destinooperacion,
            'formatocafe_sd': self.def_formatocafe_sd,
            'formatocafe_pos': self.def_formatocafe_pos,
            'entregacafe': self.def_entregacafe,
            'enviocontenedor': self.def_enviocontenedor,
            'procesogeneracion': self.def_procesogeneracion,
            'tipoventa': self.def_tipoventa,
        })

    @api.model
    def get_values(self):
        # res = super(ResConfigSettings, self).get_values()
        res = super().get_values()
        company = self.env.company
        def_fields = company.def_fields_part
        res.update({
            'l10n_pa_use_cfe': company.l10n_pa_use_cfe,
            'l10n_pa_ws_environment': company.l10n_pa_ws_environment_id.id,
            'l10n_pa_ws_user_fname': company.l10n_pa_ws_user_fname,
            'l10n_pa_ws_token_fname': company.l10n_pa_ws_token_fname,
            'l10n_pa_ws_wsdl_url': company.l10n_pa_ws_wsdl_url,
            'res_partner_def_fields': def_fields.id,
        #    'def_fel_country_id': def_fields.country_id.id,
        #    'def_fel_state_id': def_fields.state_id.id,
        #    'def_fel_district_id': def_fields.district_id.id,
        #    'def_fel_jurisdiction_id': def_fields.jurisdiction_id.id,
            'def_fel_country_id': def_fields.country_id.id if def_fields.country_id else False,
            'def_fel_state_id': def_fields.state_id.id if def_fields.state_id else False,
            'def_fel_district_id': def_fields.district_id.id if def_fields.district_id else False,
            'def_fel_jurisdiction_id': def_fields.jurisdiction_id.id if def_fields.jurisdiction_id else False,
            'def_fel_l10n_pa_edi_customer_type': def_fields.l10n_pa_edi_customer_type,
            'def_fel_l10n_pa_edi_tipo_contribuyente': def_fields.l10n_pa_edi_tipo_contribuyente,
            'def_tipoemision': def_fields.tipoemision,
            'def_tipodocumento': def_fields.tipodocumento,
            'def_puntofacturacionfiscal': def_fields.puntofacturacionfiscal,
            'def_destinooperacion': def_fields.destinooperacion,
            'def_formatocafe_sd': def_fields.formatocafe_sd,
            'def_formatocafe_pos': def_fields.formatocafe_pos,
            'def_entregacafe': def_fields.entregacafe,
            'def_enviocontenedor': def_fields.enviocontenedor,
            'def_procesogeneracion': def_fields.procesogeneracion,
            'def_tipoventa': def_fields.tipoventa,
        })
        return res
        
    ######################
    # Open Views Logs
    ######################
    def open_views_logs_fel_pan(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Logs'),
            'res_model': 'log.fel.pan',
            'view_mode': 'list,form',
            'domain': [('company_id', '=', self.company_id.id)],
            'context': {'default_company_id': self.company_id.id},
            # vista tree 
            'views': [(self.env.ref('l10n_pa_edi.view_log_fel_pan_tree').id, 'list'),
                        (self.env.ref('l10n_pa_edi.view_log_fel_pa_form').id, 'form'),
                        (self.env.ref('l10n_pa_edi.view_log_fel_pan_search').id, 'search')],
            # vista search
            'search_view_id': self.env.ref('l10n_pa_edi.view_log_fel_pan_search').id,
            'target': 'current',
            # evitar que puedan crear registros
            'create': False,
            'edit': False,
        }
    ######################
    # Open Views Default Address
    ######################
    def open_default_address(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Default Address'),
            'res_model': 'res.partner.def.fields',
            'view_mode': 'list,form',
            'domain': [('company_id', '=', self.company_id.id)],
            'context': {'default_company_id': self.company_id.id},
            'target': 'current',
        }
    ######################
    # Open Sequence Factura FEL
    ######################
    def open_sequence_factura_fel(self):
        self.ensure_one()
        sequence = self.company_id._get_l10n_pa_edi_sequence_factura()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sequence Factura FEL'),
            'res_model': 'ir.sequence',
            'res_id': sequence.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def write(self, vals):
        res = super(ResConfigSettings, self).write(vals)
        if 'l10n_pa_use_cfe' in vals:
            self.company_id.l10n_pa_ws_user_fname = self.l10n_pa_ws_user_fname
            self.company_id.l10n_pa_ws_token_fname = self.l10n_pa_ws_token_fname
            self.company_id.l10n_pa_ws_wsdl_url = self.l10n_pa_ws_wsdl_url
        return res