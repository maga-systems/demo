from odoo import api, fields, models
from odoo.exceptions import UserError


class WizardMigrateJournalSequence(models.TransientModel):
    _name = 'l10n_pa_edi.wizard.migrate.sequence'
    _description = 'Migrar secuencia FEL a diario'

    journal_id = fields.Many2one(
        'account.journal',
        string='Diario',
        required=True,
        readonly=True,
    )
    punto_facturacion = fields.Char(
        string='Punto de Facturación Fiscal (PFF)',
        size=3,
        help='3 dígitos. Debe coincidir con el PFF que usaba este diario en la DGI.',
    )
    ultimo_folio_dgi = fields.Integer(
        string='Último folio Facturas (DGI)',
        default=0,
        help='La nueva secuencia de facturas iniciará en este número + 1. '
             'Consulta FoliosRestantes en el PAC para confirmarlo.',
    )
    next_number = fields.Integer(
        string='Próximo número de Factura',
        compute='_compute_next',
    )
    ultimo_folio_nc = fields.Integer(
        string='Último folio Notas de Crédito (DGI)',
        default=0,
        help='La nueva secuencia de Notas de Crédito iniciará en este número + 1. '
             'Ingresa 0 si nunca se han emitido notas de crédito en este diario.',
    )
    next_number_nc = fields.Integer(
        string='Próximo número de Nota de Crédito',
        compute='_compute_next',
    )

    @api.depends('ultimo_folio_dgi', 'ultimo_folio_nc')
    def _compute_next(self):
        for rec in self:
            rec.next_number = rec.ultimo_folio_dgi + 1
            rec.next_number_nc = rec.ultimo_folio_nc + 1

    def action_migrate(self):
        self.ensure_one()
        journal = self.journal_id

        if self.ultimo_folio_dgi < 0 or self.ultimo_folio_nc < 0:
            raise UserError("El último folio no puede ser negativo.")

        punto = (self.punto_facturacion or journal.l10n_pa_edi_punto_facturacion or '').strip().zfill(3)

        if not punto or len(punto) != 3:
            raise UserError("El Punto de Facturación debe tener exactamente 3 dígitos.")

        if punto == '000':
            raise UserError("El Punto de Facturación '000' no es válido para la DGI.")

        seq_code = 'l10n_pa_edi.seq.journal.%d' % journal.id
        seq_nc_code = 'l10n_pa_edi.seq.journal.nc.%d' % journal.id

        seq = self.env['ir.sequence'].search([
            ('code', '=', seq_code),
            ('company_id', '=', journal.company_id.id),
        ], limit=1)
        if not seq:
            seq = self.env['ir.sequence'].create({
                'name': 'FEL Facturas - %s' % journal.name,
                'code': seq_code,
                'padding': 10,
                'number_next': self.next_number,
                'number_increment': 1,
                'company_id': journal.company_id.id,
            })
        else:
            seq.write({'number_next': self.next_number})

        seq_nc = self.env['ir.sequence'].search([
            ('code', '=', seq_nc_code),
            ('company_id', '=', journal.company_id.id),
        ], limit=1)
        if not seq_nc:
            seq_nc = self.env['ir.sequence'].create({
                'name': 'FEL Notas de Crédito - %s' % journal.name,
                'code': seq_nc_code,
                'padding': 10,
                'number_next': self.next_number_nc,
                'number_increment': 1,
                'company_id': journal.company_id.id,
            })
        else:
            seq_nc.write({'number_next': self.next_number_nc})

        journal.write({
            'l10n_pa_edi_sequence_id': seq.id,
            'l10n_pa_edi_sequence_nc_id': seq_nc.id,
            'l10n_pa_edi_punto_facturacion': punto,
            'l10n_pa_edi_use_global_sequence': False,
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Migración completada',
                'message': 'Diario %s migrado. Facturas desde: %d · NC desde: %d · PFF: %s' % (
                    journal.name, self.next_number, self.next_number_nc, punto),
                'type': 'success',
                'sticky': True,
            },
        }
