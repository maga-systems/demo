# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.modules.module import get_module_resource
from datetime import datetime
from OpenSSL import crypto
import base64
import random
import logging


_logger = logging.getLogger(__name__)


class ResCompany(models.Model):

    _inherit = "res.company"

    l10n_pa_use_cfe = fields.Boolean(string='¿Utiliza facturación electrónica?')
    l10n_pa_ws_user_fname = fields.Char(string='PAC username', help='The username used to request the seal from the PAC')
    l10n_pa_ws_token_fname = fields.Char(string='PAC password', help='The password used to request the seal from the PAC')
    l10n_pa_ws_wsdl_url = fields.Char(string='WSDL')
    l10n_pa_ws_environment = fields.Selection([('testing', 'Testing'), ('productive', 'Productive')], string='environment')
    l10n_pa_ws_environment_id = fields.Many2one('dgi.web.service')
    def_fields_part = fields.Many2one('res.partner.def.fields', string='Default Address', computer=lambda self: self._get_res_partner_def_fields())
    
    def _dict_data_FEL(self):
        _ = self.def_fields_part
        return {
            'tipoemision': _.tipoemision or '01',
            'tipodocumento': _.tipodocumento or '01',
            'puntofacturacionfiscal': _.puntofacturacionfiscal or '001',
            'destinooperacion': _.destinooperacion or '1',
            'formatocafe_sd': _.formatocafe_sd or '1',
            'formatocafe_pos': _.formatocafe_pos or '1',
            'entregacafe': _.entregacafe or '1',
            'enviocontenedor': _.enviocontenedor or '1',
            'procesogeneracion': _.procesogeneracion or '1',
            'tipoventa': _.tipoventa or '1',
        }

    def _get_l10n_pa_edi_sequence_factura(self):
        self.ensure_one()
        sequence = self.env['ir.sequence'].search([
            ('code', '=', 'l10n_pa_edi.sequence_factura'),
            ('company_id', '=', self.id)
        ])
        if not sequence:
            sequence = self.env['ir.sequence'].create({
                'name': f"Secuencia para FEL - {self.name}",
                'code': 'l10n_pa_edi.sequence_factura',
                'padding': 10,
                'company_id': self.id,
            })
        return sequence

    def _get_l10n_pa_edi_sequence_nota_credito(self):
        self.ensure_one()
        sequence = self.env['ir.sequence'].search([
            ('code', '=', 'l10n_pa_edi.sequence_nota_credito'),
            ('company_id', '=', self.id)
        ])
        if not sequence:
            sequence = self.env['ir.sequence'].create({
                'name': f"Secuencia NC FEL - {self.name}",
                'code': 'l10n_pa_edi.sequence_nota_credito',
                'padding': 10,
                'company_id': self.id,
            })
        return sequence
    
    def _get_res_partner_def_fields(self):
        res = self.env['res.partner.def.fields'].search([
            ('company_id', '=', self.id)
        ], limit=1)
        if not res:
            res = self.env['res.partner.def.fields'].create({
                'company_id': self.id
            })
        self.def_fields_part = res.id
        return res

    @api.model_create_multi
    def create(self, vals_list):
        companies = super(ResCompany, self).create(vals_list)
        for company in companies:
            company._get_l10n_pa_edi_sequence_factura()
            company._get_res_partner_def_fields()
        return companies
    
    