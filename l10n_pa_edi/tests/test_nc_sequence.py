"""
Tests para la separación de secuencias FEL: Facturas vs Notas de Crédito.

Reglas DGI:
  - Facturas (out_invoice, tipoDocumento 01): usan secuencia propia
  - Notas de Crédito (out_refund, tipoDocumento 04/06): usan secuencia separada
"""
from unittest.mock import patch, MagicMock
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestNcSequenceGlobal(TransactionCase):
    """Secuencia global de empresa: facturas y NC usan contadores separados."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref('base.main_company')

    def test_sequence_factura_created_on_demand(self):
        """_get_l10n_pa_edi_sequence_factura crea la secuencia si no existe."""
        seq = self.company._get_l10n_pa_edi_sequence_factura()
        self.assertEqual(seq.code, 'l10n_pa_edi.sequence_factura')
        self.assertEqual(seq.company_id, self.company)

    def test_sequence_nc_created_on_demand(self):
        """_get_l10n_pa_edi_sequence_nota_credito crea la secuencia NC si no existe."""
        seq = self.company._get_l10n_pa_edi_sequence_nota_credito()
        self.assertEqual(seq.code, 'l10n_pa_edi.sequence_nota_credito')
        self.assertEqual(seq.company_id, self.company)

    def test_sequences_are_independent(self):
        """Las secuencias de factura y NC son objetos distintos."""
        seq_fac = self.company._get_l10n_pa_edi_sequence_factura()
        seq_nc = self.company._get_l10n_pa_edi_sequence_nota_credito()
        self.assertNotEqual(seq_fac.id, seq_nc.id)
        self.assertNotEqual(seq_fac.code, seq_nc.code)

    def test_sequence_nc_idempotent(self):
        """Llamar dos veces a _get_l10n_pa_edi_sequence_nota_credito retorna la misma."""
        seq1 = self.company._get_l10n_pa_edi_sequence_nota_credito()
        seq2 = self.company._get_l10n_pa_edi_sequence_nota_credito()
        self.assertEqual(seq1.id, seq2.id)


class TestNcSequenceJournal(TransactionCase):
    """Secuencia por diario: facturas y NC usan l10n_pa_edi_sequence_id vs _nc_id."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref('base.main_company')
        cls.journal = cls.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', cls.company.id),
        ], limit=1)

    def _make_sequences(self, next_fac=100, next_nc=200):
        """Crea par de secuencias para el diario."""
        seq_fac = self.env['ir.sequence'].create({
            'name': 'Test FEL Facturas',
            'code': 'test.fel.fac.%d' % self.journal.id,
            'padding': 10,
            'number_next': next_fac,
            'company_id': self.company.id,
        })
        seq_nc = self.env['ir.sequence'].create({
            'name': 'Test FEL NC',
            'code': 'test.fel.nc.%d' % self.journal.id,
            'padding': 10,
            'number_next': next_nc,
            'company_id': self.company.id,
        })
        return seq_fac, seq_nc

    def test_invoice_uses_sequence_id(self):
        """out_invoice consume l10n_pa_edi_sequence_id, no la de NC."""
        seq_fac, seq_nc = self._make_sequences(next_fac=100, next_nc=200)
        self.journal.write({
            'l10n_pa_edi_use_global_sequence': False,
            'l10n_pa_edi_sequence_id': seq_fac.id,
            'l10n_pa_edi_sequence_nc_id': seq_nc.id,
            'l10n_pa_edi_punto_facturacion': '001',
        })
        move = self.env['account.move'].new({'move_type': 'out_invoice', 'journal_id': self.journal.id})
        folio, punto = move._l10n_pa_edi_get_serie_and_folio(move)
        self.assertEqual(folio, '100')
        self.assertEqual(seq_fac.number_next_actual, 101)
        self.assertEqual(seq_nc.number_next_actual, 200)  # NC no tocada

    def test_refund_uses_sequence_nc_id(self):
        """out_refund consume l10n_pa_edi_sequence_nc_id, no la de facturas."""
        seq_fac, seq_nc = self._make_sequences(next_fac=100, next_nc=200)
        self.journal.write({
            'l10n_pa_edi_use_global_sequence': False,
            'l10n_pa_edi_sequence_id': seq_fac.id,
            'l10n_pa_edi_sequence_nc_id': seq_nc.id,
            'l10n_pa_edi_punto_facturacion': '001',
        })
        move = self.env['account.move'].new({'move_type': 'out_refund', 'journal_id': self.journal.id})
        folio, punto = move._l10n_pa_edi_get_serie_and_folio(move)
        self.assertEqual(folio, '200')
        self.assertEqual(seq_nc.number_next_actual, 201)
        self.assertEqual(seq_fac.number_next_actual, 100)  # Facturas no tocada

    def test_sequences_increment_independently(self):
        """Emitir factura y NC incrementan contadores independientes."""
        seq_fac, seq_nc = self._make_sequences(next_fac=50, next_nc=10)
        self.journal.write({
            'l10n_pa_edi_use_global_sequence': False,
            'l10n_pa_edi_sequence_id': seq_fac.id,
            'l10n_pa_edi_sequence_nc_id': seq_nc.id,
            'l10n_pa_edi_punto_facturacion': '001',
        })
        move_inv = self.env['account.move'].new({'move_type': 'out_invoice', 'journal_id': self.journal.id})
        move_nc = self.env['account.move'].new({'move_type': 'out_refund', 'journal_id': self.journal.id})

        folio_inv, _ = move_inv._l10n_pa_edi_get_serie_and_folio(move_inv)
        folio_nc, _ = move_nc._l10n_pa_edi_get_serie_and_folio(move_nc)

        self.assertEqual(folio_inv, '50')
        self.assertEqual(folio_nc, '10')
        self.assertEqual(seq_fac.number_next_actual, 51)
        self.assertEqual(seq_nc.number_next_actual, 11)

    def test_refund_sin_seq_nc_lanza_error(self):
        """out_refund sin secuencia NC configurada lanza UserError."""
        seq_fac, _ = self._make_sequences()
        self.journal.write({
            'l10n_pa_edi_use_global_sequence': False,
            'l10n_pa_edi_sequence_id': seq_fac.id,
            'l10n_pa_edi_sequence_nc_id': False,
            'l10n_pa_edi_punto_facturacion': '001',
        })
        move = self.env['account.move'].new({'move_type': 'out_refund', 'journal_id': self.journal.id})
        with self.assertRaises(UserError):
            move._l10n_pa_edi_get_serie_and_folio(move)

    def test_punto_es_igual_para_facturas_y_nc(self):
        """El puntoFacturacionFiscal es el mismo para facturas y NC del mismo diario."""
        seq_fac, seq_nc = self._make_sequences()
        self.journal.write({
            'l10n_pa_edi_use_global_sequence': False,
            'l10n_pa_edi_sequence_id': seq_fac.id,
            'l10n_pa_edi_sequence_nc_id': seq_nc.id,
            'l10n_pa_edi_punto_facturacion': '007',
        })
        move_inv = self.env['account.move'].new({'move_type': 'out_invoice', 'journal_id': self.journal.id})
        move_nc = self.env['account.move'].new({'move_type': 'out_refund', 'journal_id': self.journal.id})

        _, punto_inv = move_inv._l10n_pa_edi_get_serie_and_folio(move_inv)
        _, punto_nc = move_nc._l10n_pa_edi_get_serie_and_folio(move_nc)

        self.assertEqual(punto_inv, '007')
        self.assertEqual(punto_nc, '007')


class TestWizardMigrateNcSequence(TransactionCase):
    """El wizard crea ambas secuencias (facturas y NC) al migrar."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref('base.main_company')
        cls.journal = cls.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', cls.company.id),
        ], limit=1)

    def _reset_journal(self):
        self.journal.write({
            'l10n_pa_edi_use_global_sequence': True,
            'l10n_pa_edi_sequence_id': False,
            'l10n_pa_edi_sequence_nc_id': False,
            'l10n_pa_edi_punto_facturacion': False,
        })

    def test_wizard_crea_secuencia_facturas(self):
        """Migrar crea l10n_pa_edi_sequence_id para el diario."""
        self._reset_journal()
        wizard = self.env['l10n_pa_edi.wizard.migrate.sequence'].create({
            'journal_id': self.journal.id,
            'punto_facturacion': '001',
            'ultimo_folio_dgi': 99,
            'ultimo_folio_nc': 0,
        })
        wizard.action_migrate()
        self.assertTrue(self.journal.l10n_pa_edi_sequence_id)
        self.assertEqual(self.journal.l10n_pa_edi_sequence_id.number_next_actual, 100)

    def test_wizard_crea_secuencia_nc(self):
        """Migrar crea l10n_pa_edi_sequence_nc_id para el diario."""
        self._reset_journal()
        wizard = self.env['l10n_pa_edi.wizard.migrate.sequence'].create({
            'journal_id': self.journal.id,
            'punto_facturacion': '001',
            'ultimo_folio_dgi': 99,
            'ultimo_folio_nc': 49,
        })
        wizard.action_migrate()
        self.assertTrue(self.journal.l10n_pa_edi_sequence_nc_id)
        self.assertEqual(self.journal.l10n_pa_edi_sequence_nc_id.number_next_actual, 50)

    def test_wizard_next_numbers_correctos(self):
        """next_number = ultimo_folio + 1, next_number_nc = ultimo_folio_nc + 1."""
        wizard = self.env['l10n_pa_edi.wizard.migrate.sequence'].create({
            'journal_id': self.journal.id,
            'ultimo_folio_dgi': 200,
            'ultimo_folio_nc': 30,
        })
        self.assertEqual(wizard.next_number, 201)
        self.assertEqual(wizard.next_number_nc, 31)

    def test_wizard_folio_nc_negativo_lanza_error(self):
        """ultimo_folio_nc negativo lanza UserError."""
        self._reset_journal()
        wizard = self.env['l10n_pa_edi.wizard.migrate.sequence'].create({
            'journal_id': self.journal.id,
            'punto_facturacion': '001',
            'ultimo_folio_dgi': 0,
            'ultimo_folio_nc': -1,
        })
        with self.assertRaises(UserError):
            wizard.action_migrate()

    def test_wizard_desmarca_global_sequence(self):
        """Después de migrar, use_global_sequence queda en False."""
        self._reset_journal()
        wizard = self.env['l10n_pa_edi.wizard.migrate.sequence'].create({
            'journal_id': self.journal.id,
            'punto_facturacion': '003',
            'ultimo_folio_dgi': 0,
            'ultimo_folio_nc': 0,
        })
        wizard.action_migrate()
        self.assertFalse(self.journal.l10n_pa_edi_use_global_sequence)
