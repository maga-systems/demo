# coding: utf-8

from odoo import fields, models


class StateInherit(models.Model):

    _inherit = 'res.country.state'
    _defaults = {
        'code': '-'
    }

    districts = fields.One2many("res.country.state.district", "state_id", string="Districts")
    cu_name = fields.Char(string='Codigo unificado')

    _sql_constraints = [
        ('name_code_uniq', 'Check(1=1)', 'The code of the state must be unique by country !')
    ]

class District(models.Model):

    _name = 'res.country.state.district'
    _description = 'District'

    name = fields.Char(string='District ID', required=True, copy=False, index=True)
    state_id = fields.Many2one("res.country.state", string="State")
    country_id = fields.Many2one("res.country", string="Country")
    jurisdictions = fields.One2many("res.country.state.district.jurisdiction", "district_id", string="Jurisdictions")    
    cu_name = fields.Char(string='Codigo unificado')


class Jurisdiction(models.Model):

    _name = 'res.country.state.district.jurisdiction'
    _description = 'Jurisdiction'

    name = fields.Char(string='Jurisdiction ID', required=True, copy=False, index=True)
    district_id = fields.Many2one("res.country.state.district", string="District")
    country_id = fields.Many2one("res.country", string="Country")
    cu_name = fields.Char(string='Codigo unificado')