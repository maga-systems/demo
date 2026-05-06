# coding: utf-8
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api
from odoo.osv import expression



class ProductTemplate(models.Model):
    _inherit = 'product.template'

    unspsc_code_pa_id = fields.Many2one("product.unspsc.code.pa", string="CPBS", help='Codificación Panameña de Bienes y Servicios')
    

class ProductCodePa(models.Model):
    """Product codes defined by CPBS
    Used by Panamenian localizations
    """
    _name = 'product.unspsc.code.pa'
    _description = "Product Codes for CPBS"

    code = fields.Char('Code', required=True)
    name = fields.Char('Name', required=True)
    active = fields.Boolean()

    def name_get(self):
        result = []
        for prod in self:
            result.append((prod.id, "%s %s" % (prod.code, prod.name or '')))
        return result

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None):
        args = args or []
        if operator == 'ilike' and not (name or '').strip():
            domain = []
        else:
            domain = ['|', ('name', 'ilike', name), ('code', 'ilike', name)]
        return self._search(expression.AND([domain, args]), limit=limit, access_rights_uid=name_get_uid)