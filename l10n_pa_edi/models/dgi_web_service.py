from odoo import models, fields, api
from odoo.exceptions import UserError

import logging

class DGIWebService(models.Model):
    _name = 'dgi.web.service'
    _rec_name = 'environment'

    environment = fields.Char(ondelete=False)
    ws_user_fname = fields.Char(string='User name')
    ws_token_fname = fields.Char(string='Token')
    ws_wsdl_url = fields.Char(string='WSDL')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    pac_footer_text = fields.Char(
        string='Texto pie de página PAC',
        help='Ejemplo: Documento validado por The Factory HKA Corp. '
             'con RUC 155596713-2-2015, es Proveedor Autorizado Calificado, '
             'Resolución No. 201-9719 de 12/10/2021'
    )

    def write(self, vals):
        res = super(DGIWebService, self).write(vals)
        for record in self:
            if record.company_id.l10n_pa_ws_environment_id.id == record.id:
                record.company_id.l10n_pa_ws_user_fname = record.ws_user_fname
                record.company_id.l10n_pa_ws_token_fname = record.ws_token_fname
                record.company_id.l10n_pa_ws_wsdl_url = record.ws_wsdl_url
        return res