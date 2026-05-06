from odoo import fields, models
from odoo.exceptions import UserError


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    l10n_pa_edi_use_global_sequence = fields.Boolean(
        string='Usar secuencia global (legado)',
        default=True,
        help='Si está activo, usa la secuencia global de la empresa. '
             'Desactivar solo cuando se configure secuencia propia en este diario.',
    )
    l10n_pa_edi_punto_facturacion = fields.Char(
        string='Punto Facturación Fiscal',
        size=3,
        help='PFF de 3 dígitos asignado por la DGI. Ej: 001. '
             'Solo requerido si no usa secuencia global.',
    )
    l10n_pa_edi_sequence_id = fields.Many2one(
        'ir.sequence',
        string='Secuencia FEL (Facturas)',
        copy=False,
        help='Secuencia de numeración fiscal para facturas (tipoDocumento 01). '
             'El número siguiente debe ser último folio DGI + 1.',
    )
    l10n_pa_edi_sequence_nc_id = fields.Many2one(
        'ir.sequence',
        string='Secuencia FEL (Notas de Crédito)',
        copy=False,
        help='Secuencia de numeración fiscal para notas de crédito (tipoDocumento 04/06). '
             'El número siguiente debe ser último folio DGI + 1.',
    )

    def action_open_migrate_wizard(self):
        self.ensure_one()
        wizard = self.env['l10n_pa_edi.wizard.migrate.sequence'].create({
            'journal_id': self.id,
            'punto_facturacion': self.l10n_pa_edi_punto_facturacion or '',
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Migrar secuencia FEL',
            'res_model': 'l10n_pa_edi.wizard.migrate.sequence',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }
