# TAREA: Secuencia FEL por Diario — `l10n_pa_edi`

## CONTEXTO OBLIGATORIO — LEER PRIMERO

Estás trabajando sobre el módulo `l10n_pa_edi` (Odoo CE v18).
El módulo ya existe y está en producción. **No renombres nada existente.**

Esta tarea agrega soporte para secuencias de numeración fiscal (FEL)
independientes por diario contable, manteniendo compatibilidad total
con el comportamiento actual (secuencia global por empresa).

**Regla de oro:** Antes de modificar cualquier archivo, léelo completo.

---

## PASO 0 — RECONOCIMIENTO INICIAL

Ejecuta esto antes de cualquier cambio:

```bash
# Ubicar el módulo
find / -type d -name "l10n_pa_edi" 2>/dev/null | grep -v __pycache__

# Ver estructura completa
ls -la {RUTA_MODULO}/
ls -la {RUTA_MODULO}/models/
ls -la {RUTA_MODULO}/views/
ls -la {RUTA_MODULO}/wizard/ 2>/dev/null || echo "wizard/ no existe aún"
ls -la {RUTA_MODULO}/tests/
cat {RUTA_MODULO}/__manifest__.py
cat {RUTA_MODULO}/__init__.py
cat {RUTA_MODULO}/models/__init__.py
```

Reemplaza `{RUTA_MODULO}` con la ruta real encontrada.
Úsala en todos los pasos siguientes.

```bash
# Leer archivos que vas a modificar — OBLIGATORIO antes de tocarlos
cat {RUTA_MODULO}/models/account_move.py
cat {RUTA_MODULO}/security/ir.model.access.csv
```

---

## PASO 1 — CREAR `models/account_journal.py`

Crea el archivo. Si ya existe, léelo primero y agrega solo lo que falte.

```python
# {RUTA_MODULO}/models/account_journal.py
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
        string='Secuencia FEL',
        copy=False,
        help='Secuencia de numeración fiscal para este diario. '
             'El número siguiente debe ser último folio DGI + 1.',
    )

    def action_open_migrate_wizard(self):
        self.ensure_one()
        wizard = self.env['l10n_pa_edi.wizard.migrate.sequence'].create({
            'journal_id': self.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Migrar secuencia FEL',
            'res_model': 'l10n_pa_edi.wizard.migrate.sequence',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }
```

---

## PASO 2 — REGISTRAR EN `models/__init__.py`

Lee el archivo actual. Agrega la línea en orden alfabético junto a los demás imports:

```python
from . import account_journal
```

**Verificación:** El archivo debe quedar con todos los imports anteriores intactos.

---

## PASO 3 — CREAR CARPETA `wizard/`

```bash
mkdir -p {RUTA_MODULO}/wizard
```

### `wizard/__init__.py`

```python
from . import wizard_migrate_journal_sequence
```

### `wizard/wizard_migrate_journal_sequence.py`

```python
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
        required=True,
        help='3 dígitos. Debe coincidir con el PFF que usaba este diario en la DGI.',
    )
    ultimo_folio_dgi = fields.Integer(
        string='Último folio autorizado por la DGI',
        required=True,
        help='La nueva secuencia iniciará en este número + 1. '
             'Consulta FoliosRestantes en el PAC para confirmarlo.',
    )
    next_number = fields.Integer(
        string='Próximo número de documento',
        compute='_compute_next',
    )

    @api.depends('ultimo_folio_dgi')
    def _compute_next(self):
        for rec in self:
            rec.next_number = rec.ultimo_folio_dgi + 1

    def action_migrate(self):
        self.ensure_one()
        journal = self.journal_id

        if not journal.l10n_pa_edi_use_global_sequence:
            raise UserError(
                "El diario '%s' ya fue migrado a secuencia propia." % journal.name
            )

        punto = (self.punto_facturacion or '').strip().zfill(3)

        if not punto or len(punto) != 3:
            raise UserError("El Punto de Facturación debe tener exactamente 3 dígitos.")

        if punto == '000':
            raise UserError("El Punto de Facturación '000' no es válido para la DGI.")

        if self.ultimo_folio_dgi < 0:
            raise UserError("El último folio no puede ser negativo.")

        seq_code = 'l10n_pa_edi.seq.journal.%d' % journal.id

        seq = self.env['ir.sequence'].search([
            ('code', '=', seq_code),
            ('company_id', '=', journal.company_id.id),
        ], limit=1)

        if not seq:
            seq = self.env['ir.sequence'].create({
                'name': 'FEL - %s' % journal.name,
                'code': seq_code,
                'padding': 10,
                'number_next': self.next_number,
                'number_increment': 1,
                'company_id': journal.company_id.id,
            })
        else:
            seq.write({'number_next': self.next_number})

        journal.write({
            'l10n_pa_edi_sequence_id': seq.id,
            'l10n_pa_edi_punto_facturacion': punto,
            'l10n_pa_edi_use_global_sequence': False,
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Migración completada',
                'message': 'Diario %s migrado. Próximo folio: %d · PFF: %s' % (
                    journal.name, self.next_number, punto),
                'type': 'success',
                'sticky': True,
            },
        }
```

---

## PASO 4 — CREAR VISTAS

### `views/account_journal_views.xml`

Si el archivo ya existe, agrégale el record nuevo. Si no existe, créalo completo.

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_account_journal_form_l10n_pa_edi" model="ir.ui.view">
        <field name="name">account.journal.form.l10n_pa_edi</field>
        <field name="model">account.journal</field>
        <field name="inherit_id" ref="account.view_account_journal_form"/>
        <field name="arch" type="xml">
            <xpath expr="//notebook" position="inside">
                <page string="Fact. Electrónica PA"
                      name="l10n_pa_edi_journal"
                      invisible="type != 'sale'">

                    <group string="Configuración FEL">
                        <field name="l10n_pa_edi_use_global_sequence"/>
                        <field name="l10n_pa_edi_punto_facturacion"
                               invisible="l10n_pa_edi_use_global_sequence == True"
                               required="l10n_pa_edi_use_global_sequence == False"/>
                        <field name="l10n_pa_edi_sequence_id"
                               invisible="l10n_pa_edi_use_global_sequence == True"
                               required="l10n_pa_edi_use_global_sequence == False"/>
                    </group>

                    <div class="alert alert-info"
                         invisible="l10n_pa_edi_use_global_sequence == False">
                        <p>
                            Este diario usa la <strong>secuencia global de la empresa</strong>
                            (comportamiento original). Para migrar a secuencia independiente
                            por diario, usa el botón de abajo.
                        </p>
                    </div>

                    <div class="alert alert-success"
                         invisible="l10n_pa_edi_use_global_sequence == True">
                        <p>
                            Este diario usa su <strong>propia secuencia FEL</strong>.
                            PFF configurado: <strong><field name="l10n_pa_edi_punto_facturacion"
                                                            readonly="1" nolabel="1"/></strong>
                        </p>
                    </div>

                    <footer invisible="l10n_pa_edi_use_global_sequence == False">
                        <button name="action_open_migrate_wizard"
                                string="Migrar a secuencia por diario"
                                type="object"
                                class="btn-secondary"
                                icon="fa-exchange"/>
                    </footer>

                </page>
            </xpath>
        </field>
    </record>
</odoo>
```

### `views/wizard_migrate_journal_sequence_views.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_wizard_migrate_journal_sequence_form"
            model="ir.ui.view">
        <field name="name">l10n_pa_edi.wizard.migrate.sequence.form</field>
        <field name="model">l10n_pa_edi.wizard.migrate.sequence</field>
        <field name="arch" type="xml">
            <form string="Migrar secuencia FEL a diario">
                <sheet>
                    <group>
                        <field name="journal_id" readonly="1"/>
                    </group>
                    <group string="Datos de migración">
                        <field name="punto_facturacion"
                               placeholder="Ej: 001"/>
                        <field name="ultimo_folio_dgi"/>
                        <field name="next_number" readonly="1"/>
                    </group>
                    <div class="alert alert-warning" role="alert">
                        <strong>Antes de continuar:</strong>
                        Confirma el último folio autorizado consultando
                        <em>FoliosRestantes</em> en el PAC (The Factory HKA).
                        Una vez migrado, el diario dejará de usar la secuencia global.
                    </div>
                </sheet>
                <footer>
                    <button name="action_migrate"
                            string="Confirmar migración"
                            type="object"
                            class="btn-primary"/>
                    <button string="Cancelar"
                            class="btn-secondary"
                            special="cancel"/>
                </footer>
            </form>
        </field>
    </record>
</odoo>
```

---

## PASO 5 — SEGURIDAD

Lee el contenido actual de `security/ir.model.access.csv`.
Agrega esta línea al final (sin línea en blanco al final del archivo):

```csv
access_l10n_pa_edi_wizard_migrate_sequence,l10n_pa_edi.wizard.migrate.sequence,model_l10n_pa_edi_wizard_migrate_sequence,base.group_system,1,1,1,1
```

---

## PASO 6 — ACTUALIZAR `__manifest__.py`

Lee el manifest completo. En la clave `data`, agrega las entradas nuevas.
**Respeta el orden existente.** Las vistas van después de security:

```python
'views/account_journal_views.xml',
'views/wizard_migrate_journal_sequence_views.xml',
```

En la clave `depends`, verifica que `account` esté presente (casi seguro que sí).

En `__init__.py` raíz del módulo, agrega:

```python
from . import wizard
```

---

## PASO 7 — MODIFICAR `models/account_move.py`

Lee el archivo completo primero.

Localiza el método `_l10n_pa_edi_get_serie_and_folio`. Reemplaza **únicamente su cuerpo**,
sin tocar la firma ni nada fuera del método.

El nuevo cuerpo:

```python
def _l10n_pa_edi_get_serie_and_folio(self, move):
    journal = move.journal_id
    company = move.company_id

    if journal.l10n_pa_edi_use_global_sequence:
        # Modo legado: secuencia global de empresa — comportamiento original intacto
        sequence = company._get_l10n_pa_edi_sequence_factura()
        folio = sequence.next_by_id()
        def_fields = company._get_res_partner_def_fields()
        punto = (def_fields.puntofacturacionfiscal or '001').zfill(3)
        return folio, punto

    # Modo nuevo: secuencia independiente por diario
    if not journal.l10n_pa_edi_sequence_id:
        raise UserError(
            "El diario '%s' está configurado para usar secuencia propia "
            "pero no tiene ninguna asignada.\n"
            "Ve al diario → pestaña 'Fact. Electrónica PA' → Migrar secuencia."
            % journal.name
        )
    if not journal.l10n_pa_edi_punto_facturacion:
        raise UserError(
            "El diario '%s' no tiene Punto de Facturación configurado.\n"
            "Ve al diario → pestaña 'Fact. Electrónica PA'."
            % journal.name
        )

    folio = journal.l10n_pa_edi_sequence_id.next_by_id()
    punto = journal.l10n_pa_edi_punto_facturacion.zfill(3)
    return folio, punto
```

---

## PASO 8 — TESTS

Lee primero `tests/__init__.py` y el patrón de los tests existentes en `test_ruc_validation.py`.

Crea `tests/test_journal_sequence.py`:

```python
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

        # Diario de venta existente o creado para tests
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
            'punto_facturacion': '5',   # debe rellenarse a '005'
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
        # Primera migración
        w1 = self.env['l10n_pa_edi.wizard.migrate.sequence'].create({
            'journal_id': journal_test.id,
            'punto_facturacion': '002',
            'ultimo_folio_dgi': 100,
        })
        w1.action_migrate()

        # Segunda migración — debe fallar
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

        self.assertEqual(folio, '0000000099')
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
        # El folio debe ser el formateado por la secuencia (padding 10)
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
            # sin l10n_pa_edi_sequence_id
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
            # sin l10n_pa_edi_punto_facturacion
        })

        move_mock = MagicMock()
        move_mock.journal_id = journal_test
        move_mock.company_id = self.company

        with self.assertRaises(UserError):
            self.env['account.move']._l10n_pa_edi_get_serie_and_folio(move_mock)

    def test_pff_se_rellena_con_ceros(self):
        """PFF '5' debe quedar '005' en el resultado."""
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
            'l10n_pa_edi_punto_facturacion': '5',  # sin zfill
        })

        move_mock = MagicMock()
        move_mock.journal_id = journal_test
        move_mock.company_id = self.company

        _, punto = self.env['account.move']._l10n_pa_edi_get_serie_and_folio(
            move_mock
        )
        self.assertEqual(punto, '005')
```

Registra el test en `tests/__init__.py` agregando:

```python
from . import test_journal_sequence
```

---

## PASO 9 — VERIFICACIÓN FINAL

### Verificar que no rompiste nada en `__init__.py` y `__manifest__.py`

```bash
# Revisar que todos los archivos nuevos existen
ls {RUTA_MODULO}/models/account_journal.py
ls {RUTA_MODULO}/wizard/__init__.py
ls {RUTA_MODULO}/wizard/wizard_migrate_journal_sequence.py
ls {RUTA_MODULO}/views/account_journal_views.xml
ls {RUTA_MODULO}/views/wizard_migrate_journal_sequence_views.xml
ls {RUTA_MODULO}/tests/test_journal_sequence.py
```

### Verificar sintaxis Python

```bash
python3 -m py_compile {RUTA_MODULO}/models/account_journal.py && echo "OK account_journal"
python3 -m py_compile {RUTA_MODULO}/wizard/wizard_migrate_journal_sequence.py && echo "OK wizard"
python3 -m py_compile {RUTA_MODULO}/tests/test_journal_sequence.py && echo "OK tests"
python3 -m py_compile {RUTA_MODULO}/models/account_move.py && echo "OK account_move"
```

### Actualizar módulo

```bash
# Ajusta la ruta de odoo-bin y el nombre de tu base de datos
python3 {RUTA_ODOO}/odoo-bin \
    -u l10n_pa_edi \
    -d {NOMBRE_BD} \
    --stop-after-init \
    2>&1 | tail -30
```

Si ves errores de XML (`ir.ui.view`), revisa que el `inherit_id` apunte
a `account.view_account_journal_form` exactamente — ese es el external_id
estándar en v18.

### Ejecutar tests

```bash
python3 {RUTA_ODOO}/odoo-bin \
    --test-enable \
    --test-tags=l10n_pa_edi \
    -u l10n_pa_edi \
    -d {NOMBRE_BD} \
    --stop-after-init \
    2>&1 | grep -E "(ERROR|FAIL|OK|test_|Ran)"
```

Resultado esperado: todos los tests `test_journal_sequence` en OK,
y los tests existentes `test_ruc_validation` sin regresiones.

---

## CRITERIOS DE ACEPTACIÓN

- [ ] Diario de venta muestra pestaña "Fact. Electrónica PA"
- [ ] Campo `l10n_pa_edi_use_global_sequence` arranca en `True` para todos los diarios
- [ ] Botón "Migrar a secuencia por diario" abre el wizard
- [ ] Wizard valida PFF `000` y folio negativo
- [ ] Wizard crea secuencia con `number_next = ultimo_folio + 1`
- [ ] Wizard asigna PFF con zfill(3)
- [ ] Diarios en modo legado siguen usando secuencia global sin cambios
- [ ] `_l10n_pa_edi_get_serie_and_folio` respeta el flag del diario
- [ ] `UserError` claro si modo nuevo pero sin secuencia o sin PFF
- [ ] 11 tests pasan sin errores
- [ ] Tests existentes (`test_ruc_validation`) sin regresiones

---

## NOTAS PARA CLAUDE CODE

- Si `_l10n_pa_edi_get_serie_and_folio` no existe con ese nombre exacto en
  `account_move.py`, búscalo por su comportamiento: es el método que obtiene
  el siguiente número de secuencia para la DGI. Lee el archivo completo y
  ajusta el nombre en los tests también.

- Si `tests/__init__.py` usa `from . import *` en lugar de imports explícitos,
  agrega el import explícito de todas formas al final del archivo.

- No elimines ni modifiques ningún test existente.

- Si encuentras que `account_journal_views.xml` ya existe con contenido,
  agrega solo el `<record>` nuevo respetando la estructura XML existente.
