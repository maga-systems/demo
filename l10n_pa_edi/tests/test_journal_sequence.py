from unittest.mock import patch, MagicMock
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestJournalSequenceMigration(TransactionCase):
    """
    Tests para la migración de secuencia FEL a nivel de diario.
    Cubre: campos nuevos, wizard, fallback legado, modo nuevo.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref('base.main_company')

        cls.journal = cls.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', cls.company.id),
        ], limit=1)

        if not cls.journal:
            cls.journal = cls.env['account.journal'].create({
                'name': 'Test Ventas FEL',
                'type': 'sale',
                'code': 'TFEL',
                'company_id': cls.company.id,
            })

    # ------------------------------------------------------------------
    # Campos nuevos en account.journal
    # ------------------------------------------------------------------

    def test_campo_use_global_sequence_default_true(self):
        """Todos los diarios arrancan en modo legado por defecto."""
        journal_nuevo = self.env['account.journal'].create({
            'name': 'Nuevo Diario FEL',
            'type': 'sale',
            'code': 'NFT1',
            'company_id': self.company.id,
        })
        self.assertTrue(
            journal_nuevo.l10n_pa_edi_use_global_sequence,
            "Un diario nuevo debe usar secuencia global por defecto."
        )

    def test_campos_punto_y_sequence_vacios_por_defecto(self):
        """PFF y secuencia vacíos en diario nuevo."""
        journal_nuevo = self.env['account.journal'].create({
            'name': 'Nuevo Diario FEL 2',
            'type': 'sale',
            'code': 'NFT2',
            'company_id': self.company.id,
        })
        self.assertFalse(journal_nuevo.l10n_pa_edi_punto_facturacion)
        self.assertFalse(journal_nuevo.l10n_pa_edi_sequence_id)

    # ------------------------------------------------------------------
    # Wizard — validaciones
    # ------------------------------------------------------------------

    def test_wizard_pff_000_invalido(self):
        """PFF '000' debe ser rechazado."""
        wizard = self.env['l10n_pa_edi.wizard.migrate.sequence'].create({
            'journal_id': self.journal.id,
            'punto_facturacion': '000',
            'ultimo_folio_dgi': 100,
        })
        with self.assertRaises(UserError, msg="PFF 000 debe lanzar UserError"):
            wizard.action_migrate()

    def test_wizard_folio_negativo_invalido(self):
        """Último folio negativo debe ser rechazado."""
        wizard = self.env['l10n_pa_edi.wizard.migrate.sequence'].create({
            'journal_id': self.journal.id,
            'punto_facturacion': '001',
            'ultimo_folio_dgi': -1,
        })
        with self.assertRaises(UserError, msg="Folio negativo debe lanzar UserError"):
            wizard.action_migrate()

    def test_wizard_migra_correctamente(self):
        """Migración exitosa: secuencia creada, PFF asignado, flag desactivado."""
        journal_test = self.env['account.journal'].create({
            'name': 'Diario Migración Test',
            'type': 'sale',
            'code': 'DMIG',
            'company_id': self.company.id,
        })
        self.assertTrue(journal_test.l10n_pa_edi_use_global_sequence)

        wizard = self.env['l10n_pa_edi.wizard.migrate.sequence'].create({
            'journal_id': journal_test.id,
            'punto_facturacion': '5',
            'ultimo_folio_dgi': 500,
        })
        wizard.action_migrate()

        self.assertFalse(
            journal_test.l10n_pa_edi_use_global_sequence,
            "Después de migrar, use_global_sequence debe ser False."
        )
        self.assertEqual(
            journal_test.l10n_pa_edi_punto_facturacion, '005',
            "El PFF debe ser rellenado con ceros a la izquierda."
        )
        self.assertTrue(
            journal_test.l10n_pa_edi_sequence_id,
            "Debe existir una secuencia asignada al diario."
        )
        self.assertEqual(
            journal_test.l10n_pa_edi_sequence_id.number_next, 501,
            "El próximo número debe ser último_folio + 1."
        )

    def test_wizard_compute_next_number(self):
        """next_number siempre es ultimo_folio_dgi + 1."""
        wizard = self.env['l10n_pa_edi.wizard.migrate.sequence'].create({
            'journal_id': self.journal.id,
            'punto_facturacion': '001',
            'ultimo_folio_dgi': 999,
        })
        self.assertEqual(wizard.next_number, 1000)

    def test_wizard_doble_migracion_lanza_error(self):
        """No se puede migrar un diario que ya fue migrado."""
        journal_test = self.env['account.journal'].create({
            'name': 'Diario Ya Migrado',
            'type': 'sale',
            'code': 'DYM1',
            'company_id': self.company.id,
        })
        w1 = self.env['l10n_pa_edi.wizard.migrate.sequence'].create({
            'journal_id': journal_test.id,
            'punto_facturacion': '002',
            'ultimo_folio_dgi': 100,
        })
        w1.action_migrate()

        w2 = self.env['l10n_pa_edi.wizard.migrate.sequence'].create({
            'journal_id': journal_test.id,
            'punto_facturacion': '002',
            'ultimo_folio_dgi': 200,
        })
        with self.assertRaises(UserError, msg="Segunda migración debe lanzar UserError"):
            w2.action_migrate()

    def test_wizard_reutiliza_secuencia_existente(self):
        """Si ya existe una secuencia con el mismo code, la reutiliza y actualiza."""
        journal_test = self.env['account.journal'].create({
            'name': 'Diario Reuse Seq',
            'type': 'sale',
            'code': 'DRS1',
            'company_id': self.company.id,
        })
        seq_code = 'l10n_pa_edi.seq.journal.%d' % journal_test.id
        seq_existente = self.env['ir.sequence'].create({
            'name': 'Seq Existente',
            'code': seq_code,
            'padding': 10,
            'number_next': 50,
            'company_id': self.company.id,
        })

        wizard = self.env['l10n_pa_edi.wizard.migrate.sequence'].create({
            'journal_id': journal_test.id,
            'punto_facturacion': '003',
            'ultimo_folio_dgi': 300,
        })
        wizard.action_migrate()

        self.assertEqual(
            journal_test.l10n_pa_edi_sequence_id.id, seq_existente.id,
            "Debe reutilizar la secuencia existente, no crear una nueva."
        )
        self.assertEqual(
            seq_existente.number_next, 301,
            "El number_next debe actualizarse al nuevo valor."
        )

    # ------------------------------------------------------------------
    # _l10n_pa_edi_get_serie_and_folio — modo legado
    # ------------------------------------------------------------------

    def test_get_serie_folio_modo_legado_usa_secuencia_global(self):
        """
        En modo legado, _l10n_pa_edi_get_serie_and_folio llama
        a la secuencia global de la empresa.
        """
        move_mock = MagicMock()
        move_mock.journal_id = self.journal
        move_mock.company_id = self.company
        self.journal.l10n_pa_edi_use_global_sequence = True

        fake_seq = MagicMock()
        fake_seq.next_by_id.return_value = '0000000099'

        fake_def_fields = MagicMock()
        fake_def_fields.puntofacturacionfiscal = '007'

        move_model = self.env['account.move']

        with patch.object(
            type(self.company),
            '_get_l10n_pa_edi_sequence_factura',
            return_value=fake_seq,
        ), patch.object(
            type(self.company),
            '_get_res_partner_def_fields',
            return_value=fake_def_fields,
        ):
            folio, punto = move_model._l10n_pa_edi_get_serie_and_folio(move_mock)

        self.assertEqual(folio, '99')
        self.assertEqual(punto, '007')

    # ------------------------------------------------------------------
    # _l10n_pa_edi_get_serie_and_folio — modo nuevo
    # ------------------------------------------------------------------

    def test_get_serie_folio_modo_nuevo_usa_secuencia_diario(self):
        """En modo nuevo, usa la secuencia y PFF del diario."""
        journal_test = self.env['account.journal'].create({
            'name': 'Diario Modo Nuevo',
            'type': 'sale',
            'code': 'DMN1',
            'company_id': self.company.id,
        })
        seq = self.env['ir.sequence'].create({
            'name': 'FEL DMN1',
            'code': 'l10n_pa_edi.seq.journal.test.dmn1',
            'padding': 10,
            'number_next': 250,
            'company_id': self.company.id,
        })
        journal_test.write({
            'l10n_pa_edi_use_global_sequence': False,
            'l10n_pa_edi_sequence_id': seq.id,
            'l10n_pa_edi_punto_facturacion': '004',
        })

        move_mock = MagicMock()
        move_mock.journal_id = journal_test
        move_mock.company_id = self.company

        folio, punto = self.env['account.move']._l10n_pa_edi_get_serie_and_folio(
            move_mock
        )

        self.assertEqual(punto, '004')
        self.assertIn('250', folio or str(folio))

    def test_get_serie_folio_modo_nuevo_sin_secuencia_lanza_error(self):
        """Modo nuevo sin secuencia asignada debe lanzar UserError claro."""
        journal_test = self.env['account.journal'].create({
            'name': 'Diario Sin Seq',
            'type': 'sale',
            'code': 'DSS1',
            'company_id': self.company.id,
        })
        journal_test.write({
            'l10n_pa_edi_use_global_sequence': False,
            'l10n_pa_edi_punto_facturacion': '005',
        })

        move_mock = MagicMock()
        move_mock.journal_id = journal_test
        move_mock.company_id = self.company

        with self.assertRaises(UserError):
            self.env['account.move']._l10n_pa_edi_get_serie_and_folio(move_mock)

    def test_get_serie_folio_modo_nuevo_sin_pff_lanza_error(self):
        """Modo nuevo sin PFF debe lanzar UserError claro."""
        journal_test = self.env['account.journal'].create({
            'name': 'Diario Sin PFF',
            'type': 'sale',
            'code': 'DSP1',
            'company_id': self.company.id,
        })
        seq = self.env['ir.sequence'].create({
            'name': 'FEL DSP1',
            'code': 'l10n_pa_edi.seq.journal.test.dsp1',
            'padding': 10,
            'number_next': 1,
            'company_id': self.company.id,
        })
        journal_test.write({
            'l10n_pa_edi_use_global_sequence': False,
            'l10n_pa_edi_sequence_id': seq.id,
        })

        move_mock = MagicMock()
        move_mock.journal_id = journal_test
        move_mock.company_id = self.company

        with self.assertRaises(UserError):
            self.env['account.move']._l10n_pa_edi_get_serie_and_folio(move_mock)

    def test_pff_se_rellena_con_ceros(self):
        """PFF '5' almacenado en el diario queda '005' al leerlo."""
        journal_test = self.env['account.journal'].create({
            'name': 'Diario PFF Corto',
            'type': 'sale',
            'code': 'DPC1',
            'company_id': self.company.id,
        })
        seq = self.env['ir.sequence'].create({
            'name': 'FEL DPC1',
            'code': 'l10n_pa_edi.seq.journal.test.dpc1',
            'padding': 10,
            'number_next': 1,
            'company_id': self.company.id,
        })
        journal_test.write({
            'l10n_pa_edi_use_global_sequence': False,
            'l10n_pa_edi_sequence_id': seq.id,
            'l10n_pa_edi_punto_facturacion': '5',
        })

        move_mock = MagicMock()
        move_mock.journal_id = journal_test
        move_mock.company_id = self.company

        _, punto = self.env['account.move']._l10n_pa_edi_get_serie_and_folio(
            move_mock
        )
        self.assertEqual(punto, '005')
