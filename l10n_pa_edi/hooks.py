# coding: utf-8
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from os.path import join, dirname, realpath
from odoo import tools, api, SUPERUSER_ID
_logger = logging.getLogger(__name__)


def post_init_hook(env):
    _load_unspsc_codes(env)
    _load_sequence_factura(env)


def _load_sequence_factura(env):
    """
    Load the sequence for the factura
    """
    sequence_model = env['ir.sequence']
    res_partner_def = env['res.partner.def.fields']
    company_model = env['res.company']
    for company in company_model.search([]):
        sequence = sequence_model.search([
            ('code', '=', 'l10n_pa_edi.sequence_factura'),
            ('company_id', '=', company.id)
        ])
        if not sequence:
            sequence_model.create({
                'name': f"Secuencia para FEL - {company.name}",
                'code': 'l10n_pa_edi.sequence_factura',
                'padding': 10,
                'company_id': company.id,
            })
        default_fields = res_partner_def.search([
            ('company_id', '=', company.id)
        ], limit=1)
        if not default_fields:
            default_fields = res_partner_def.create({
                'company_id': company.id
            })
        company.def_fields_part = default_fields.id


def uninstall_hook(env):
    env.execute("DELETE FROM product_unspsc_code_pa;")
    env.execute("DELETE FROM ir_model_data WHERE model='product_unspsc_code_pa';")
    env.execute("DELETE FROM ir_sequence WHERE code='l10n_pa_edi.sequence_factura';")


def _load_unspsc_codes(env):
    """Import CSV data as it is faster than xml and because we can't use
    noupdate anymore with csv
    Even with the faster CSVs, it would take +30 seconds to load it with
    the regular ORM methods, while here, it is under 3 seconds
    """
    try:
        csv_path = join(dirname(realpath(__file__)), 'data',
                        'product.unspsc.code.pa.csv')
        csv_file = open(csv_path, 'rb')
        csv_file.readline() # Read the header, so we avoid copying it to the db
        env.copy_expert(
            """COPY product_unspsc_code_pa (code, name, active)
            FROM STDIN WITH DELIMITER '|'""", csv_file)
        # Create xml_id, to allow make reference to this data
    except Exception as e:
        _logger.error("Error loading unspsc codes: %s", e)
        pass
    try:
        env.execute(
            """INSERT INTO ir_model_data
            (name, res_id, module, model, noupdate)
            SELECT concat('unspsc_code_', code), id, 'product_unspsc', 'product.unspsc.code.pa', 't'
            FROM product_unspsc_code_pa""")
    except Exception as e:
        _logger.error("Error creating ir_model_data: %s", e)
        pass

def _assign_codes_uom(env):
    """Assign the codes in UoM of each data, this is here because the data is
    created in the last method"""
    tools.convert.convert_file(
        env, 'product_unspsc', 'data/product_data.xml', None, mode='init',
        kind='data')