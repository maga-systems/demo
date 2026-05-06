# coding: utf-8
import json
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import zeep
from lxml import etree
from zeep.helpers import serialize_object
import logging
result_map = {
    '100': ' El token del emisor es inválido.',
    # '101': ' Error al acceder al certificado de transmisión.',
    '101': ' Error al validar el certificado de transmisión.',
    '102': ' Contribuyente no inscrito',
    # '102': ' Error XSD',
    '202': ' Error al recibir la respuesta de la DGI. No pudo procesar el documento.',
    '201': 'Error al procesar la consulta',
    'N/A': 'Error desconocido',
}


class ResPartner(models.Model):
    _inherit = 'res.partner'

    district_id = fields.Many2one("res.country.state.district", string="Distrit", domain="[('state_id','=',state_id)]",
                                  default=lambda self: self.default_district_id())
    jurisdiction_id = fields.Many2one("res.country.state.district.jurisdiction", string="Corregimiento",
                                      domain="[('district_id','=', district_id)]", default=lambda self: self.default_jurisdiction_id())
    l10n_pa_edi_codigoubicacion = fields.Char(string='Codigo Ubicacion')

    # DV field
    l10n_pa_edi_dv = fields.Char(
        string="DV")
    l10n_pa_edi_checked = fields.Boolean(
        string="Checked")

    # Extra information for Customers in Panama
    #
    l10n_pa_edi_customer_type = fields.Selection([
        ('01', 'Contribuyente'),
        ('02', 'Consumidor Final'),
        ('03', 'Gobierno'),
        ('04', 'Extranjero'),
    ], string="Tipo de cliente", store=True, default=lambda self: self.default_l10n_pa_edi_customer_type())
    #
    l10n_pa_edi_tipo_contribuyente = fields.Selection([
        ('1', 'Natural'),
        ('2', 'Jurídico'),
    ], string="Tipo de contribuyente", store=True, default=lambda self: self.default_l10n_pa_edi_tipo_contribuyente())
    l10n_pa_edi_tipo_identificacion = fields.Selection([
        ('01', 'Pasaporte'),
        ('02', 'Numero Tributario'),
        ('99', 'Otro'),
    ], string='Tipo de identificacion', store=True)
    l10n_pa_edi_nro_identificacion_extranjero = fields.Char(
        string='N° Identificacion')
    l10n_pa_edi_paisextranjero = fields.Many2one(
        comodel_name="res.country", string='Pais Extranjero')

    country_id = fields.Many2one(
        'res.country', default=lambda self: self.default_country_id())
    state_id = fields.Many2one(
        'res.country.state', string='Provincia', default=lambda self: self.default_state_id())

    @api.model
    def default_l10n_pa_edi_customer_type(self):
        res = self.env['res.partner.def.fields'].search([
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        res = res.l10n_pa_edi_customer_type if res else '01'
        return res

    @api.model
    def default_l10n_pa_edi_tipo_contribuyente(self):
        res = self.env['res.partner.def.fields'].search([
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        res = res.l10n_pa_edi_tipo_contribuyente if res else '2'
        return res


    @api.model
    def default_country_id(self):
        res = self.env['res.partner.def.fields'].search([
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        if not res:
            res = self.env['res.country'].search([('code', 'ilike', 'PA')], limit=1)
        else:
            res = res.country_id if res else False
        return res.id if res else False

    @api.model
    def default_jurisdiction_id(self):
        res = self.env['res.partner.def.fields'].search([
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        if not res:
            res = self.env['res.country.state.district.jurisdiction'].search([
                ('name', '=', 'PUEBLO NUEVO')
            ], limit=1)
        else:
            res = res.jurisdiction_id if res else False
        return res.id if res else False

    @api.model
    def default_district_id(self):
        res = self.env['res.partner.def.fields'].search([
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        if not res:
            res = self.env['res.country.state.district'].search([
                ('name', '=', 'PANAMA')
            ], limit=1)
        else:
            res = res.district_id if res else False
        return res.id if res else False

    @api.model
    def default_state_id(self):
        res = self.env['res.partner.def.fields'].search([
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        if not res:
            res = self.env['res.country.state'].search([
                ('name', '=', 'PANAMA')
            ], limit=1)
        else:
            res = res.state_id if res else False
        return res.id if res else False

    def validar_ruc_panama(self, ruc):
        """
        Valida formatos comunes de RUC en Panamá:
        Jurídico: 155596724-2-2015
        Natural con RUC: 8-123-456-7
        Natural con cédula: 8-123-456
        """
        if not ruc:
            return False

        parts = ruc.split('-')

        # Jurídico
        if len(parts) == 3:
            return all(p.isdigit() for p in parts)

        # Natural con DV
        if len(parts) == 4:
            return all(p.isdigit() for p in parts)

        # Natural solo cédula
        if len(parts) == 3 and len(parts[0]) <= 2:
            return all(p.isdigit() for p in parts)

        return False

    @api.onchange('vat')
    def onchange_customer_vat(self):
        for customer in self:
            result = {}

            if (
                    customer.l10n_pa_edi_customer_type == '01'
                    and customer.vat
                    and customer.country_id
                    and customer.country_id.code == 'PA'
            ):

                valid_vat = self.validar_ruc_panama(customer.vat)

                if not valid_vat:
                    return {
                        'warning': {
                            'title': _('RUC inválido'),
                            'message': _(
                                'Formato esperado: XXXXXXXXX-X-XXXX o X-XXX-XXXX\n'
                                'Ejemplo: 155596724-2-2015 o 8-333-4444'
                            )
                        }
                    }

                wsdl = self.env['account.move'].get_wsdl()
                cliente = zeep.Client(wsdl=wsdl)

                tokenempresa, tokenPassword = self.env['account.move'].get_tokens()

                ws_data = {
                    'tokenEmpresa': tokenempresa,
                    'tokenPassword': tokenPassword,
                    'tipoRuc': '1' if customer.l10n_pa_edi_tipo_contribuyente == '1' else '2',
                    'ruc': customer.vat,
                }

                try:
                    res = cliente.service.ConsultarRucDV(
                        consultarRucDVRequest=ws_data
                    )

                    result_dict = serialize_object(res)
                    code = result_dict.get('codigo', False)

                    if code != '200':
                        customer.l10n_pa_edi_dv = False
                        result['warning'] = {
                            'title': _('Error'),
                            'message': result_map.get(code, 'Error desconocido')
                        }

                except Exception as error:
                    raise UserError(str(error))

            return result
    """
    @api.onchange('l10n_pa_edi_customer_type')
    def onchange_customer_type(self):
        for rec in self:
            if rec.l10n_pa_edi_customer_type == '02':
                rec.vat = '000000000-0-0000'
                rec.l10n_pa_edi_dv = '00'
                rec.email = 'test@maga.biz'
            else:
                rec.vat = ''
                rec.l10n_pa_edi_dv = ''
                rec.email = ''
    """


    def check_ruc(self):
        for customer in self:
            if not customer.vat:
                raise UserError(
                    'Formato de RUC invalido -> Se espera el siguiente formato XXXXXXXXX-X-XXXX \n'
                    'Ejemplo: 155596724-2-2015'
                )

        wsdl = self.env['account.move'].get_wsdl()
        cliente = zeep.Client(wsdl=wsdl)
        tokenempresa, tokenPassword = self.env['account.move'].get_tokens()

        for customer in self:

            ws_data = {
                'tokenEmpresa': tokenempresa,
                'tokenPassword': tokenPassword,
                'tipoRuc': '1' if customer.l10n_pa_edi_tipo_contribuyente == '1' else '2',
                'ruc': customer.vat
            }

            try:
                res = cliente.service.ConsultarRucDV(
                    consultarRucDVRequest=ws_data
                )

                # convertir respuesta SOAP a dict
                result_dict = serialize_object(res)

            except Exception as error:
                raise UserError(str(error))

            code = result_dict.get('codigo', False)

            if code != '200':
                customer.l10n_pa_edi_dv = False
                raise UserError(result_map.get(code, 'Error desconocido'))

            logging.info("Respuesta RUC DGI: %s", result_dict)

            customer.l10n_pa_edi_checked = True

            info_ruc = result_dict.get('infoRuc')

            if info_ruc:

                if isinstance(info_ruc, str):
                    info_ruc_dict = json.loads(info_ruc)
                else:
                    info_ruc_dict = info_ruc

                razon_social = info_ruc_dict.get('razonSocial')
                dv = info_ruc_dict.get('dv')
                tipo_contribuyente = info_ruc_dict.get('tipoContribuyente')

                if razon_social:
                    customer.name = razon_social

                if dv:
                    customer.l10n_pa_edi_dv = dv

            message = json.dumps(result_dict.get('infoRuc'))

            customer.message_post(
                body=message,
                message_type='comment',
                subtype_xmlid='mail.mt_note'
            )

        return True
                #ventana de dialogo con el resultado
                # return {
                #     'type': 'ir.actions.act_window',
                #     'name': 'Resultado de la consulta',
                #     'res_model': 'res.partner',
                #     'view_mode': 'form',
                #     'res_id': customer.id,
                #     'target': 'new',
                # }

    @api.onchange('state_id', 'district_id', 'jurisdiction_id')
    def onchange_l10n_pa_edi_codigoubicacion(self):
        if not self.state_id.cu_name:
            return
        codigo = self.state_id.cu_name
        codigo += '-' + (self.district_id.cu_name if self.district_id.cu_name else '0')
        codigo += '-' + (self.jurisdiction_id.cu_name if self.jurisdiction_id.cu_name else '0')
        self.l10n_pa_edi_codigoubicacion = codigo

    @api.onchange('l10n_pa_edi_customer_type')
    def onchange_customer_type(self):
        for rec in self:
            if rec.l10n_pa_edi_customer_type == '03':  # Gobierno
                rec.l10n_pa_edi_tipo_contribuyente = '2'
            if rec.l10n_pa_edi_customer_type == '01':  # Contribuyente
                rec.l10n_pa_edi_tipo_contribuyente = '2'
            if rec.l10n_pa_edi_customer_type == '02':  # Consumidor Final
                rec.l10n_pa_edi_tipo_contribuyente = '1'
                # rec.vat = '000000000-0-0000'
                # rec.l10n_pa_edi_dv = '00'
            if rec.l10n_pa_edi_customer_type == '04':  # Extranjero
                rec.l10n_pa_edi_tipo_contribuyente = ''
