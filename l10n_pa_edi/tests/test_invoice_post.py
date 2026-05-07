"""
Tests de validación y envío de facturas electrónicas FEL Panamá.

Cobertura:
  1. _l10n_pa_validate_dgi_payments() — sin pago, código 99 sin desc, valor cero
  2. get_forma_pago()                 — total no coincide, crédito sin plazos,
                                       mixto crédito+efectivo, código 99 con desc
  3. _get_dic_parnet_invoice()        — tipos 01-04, código ubicación vacío
  4. _post() con WS mockeado         — éxito, error WS, código 102, pago mixto
"""
from contextlib import contextmanager
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


MOCK_WSDL = 'http://fake-hka-wsdl'
MOCK_TOKEN_EMPRESA = 'TOKEN_EMPRESA_TEST'
MOCK_TOKEN_PASSWORD = 'TOKEN_PASSWORD_TEST'

MOCK_ENVIAR_OK = {
    'codigo': '200',
    'resultado': 'procesado',
    'cufe': 'FE01' + '0' * 62,
    'qr': 'https://dgi-fep.mef.gob.pa/?cufe=FE01' + '0' * 62,
    'fechaRecepcionDGI': '2026-05-07T10:30:00+00:00',
    'nroProtocoloAutorizacion': '20260000000000001234',
    'mensaje': 'El documento se envió correctamente.',
}

MOCK_ENVIAR_ERROR = {
    'codigo': '400',
    'resultado': 'error',
    'cufe': None,
    'qr': None,
    'fechaRecepcionDGI': None,
    'nroProtocoloAutorizacion': None,
    'mensaje': 'El campo tasaITBMS es requerido.',
}

MOCK_ENVIAR_102 = {
    'codigo': '102',
    'resultado': 'error',
    'cufe': None,
    'qr': None,
    'fechaRecepcionDGI': None,
    'nroProtocoloAutorizacion': None,
    'mensaje': 'El documento está duplicado.',
}


class TestInvoiceBase(TransactionCase):
    """Setup compartido: empresa con FEL, diario, partners y producto."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company = cls.env.company
        cls.company.write({
            'l10n_pa_use_cfe': True,
            'l10n_pa_ws_wsdl_url': MOCK_WSDL,
            'l10n_pa_ws_user_fname': MOCK_TOKEN_EMPRESA,
            'l10n_pa_ws_token_fname': MOCK_TOKEN_PASSWORD,
        })

        # Defaults FEL de la empresa
        def_fields = cls.company._get_res_partner_def_fields()
        def_fields.write({
            'puntofacturacionfiscal': '001',
            'tipoemision': '01',
            'tipodocumento': '01',
            'destinooperacion': '1',
            'formatocafe_sd': '1',
            'entregacafe': '1',
            'enviocontenedor': '1',
            'procesogeneracion': '1',
            'tipoventa': '1',
        })

        # Diario de ventas
        cls.journal = cls.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', cls.company.id),
        ], limit=1)
        cls.journal.write({
            'l10n_pa_edi_codigo_sucursal': '0000',
            'l10n_pa_edi_use_global_sequence': True,
        })

        # Cuenta de ingresos (requerida por Odoo para las líneas de factura)
        # En Odoo v18 account.account usa company_ids (M2M), no company_id
        cls.income_account = cls.env['account.account'].search([
            ('account_type', 'in', ('income', 'income_other')),
            ('deprecated', '=', False),
        ], limit=1)

        # Geo Panamá
        cls.pa_country = cls.env.ref('base.pa')
        cls.state_pa = cls.env['res.country.state'].search([
            ('country_id', '=', cls.pa_country.id),
        ], limit=1)
        cls.district_pa = cls.env['res.country.state.district'].search(
            [], limit=1)
        cls.jurisdiction_pa = cls.env[
            'res.country.state.district.jurisdiction'
        ].search([], limit=1)

        # Partner tipo 01 — Contribuyente (con ubicación correcta)
        cls.partner_contrib = cls.env['res.partner'].create({
            'name': 'EMPRESA CONTRIBUYENTE SA',
            'vat': '155596713-2-2015',
            'email': 'empresa@test.pa',
            'street': 'Calle 50, Panamá',
            'country_id': cls.pa_country.id,
            'l10n_pa_edi_customer_type': '01',
            'l10n_pa_edi_tipo_contribuyente': '2',
            'l10n_pa_edi_dv': '59',
            'l10n_pa_edi_codigoubicacion': '8-8-8',
            'l10n_pa_edi_checked': True,
            'state_id': cls.state_pa.id if cls.state_pa else False,
            'district_id': cls.district_pa.id if cls.district_pa else False,
            'jurisdiction_id': (
                cls.jurisdiction_pa.id if cls.jurisdiction_pa else False),
        })

        # Partner tipo 01 — Contribuyente SIN código de ubicación (caso de error)
        cls.partner_contrib_sin_ubicacion = cls.env['res.partner'].create({
            'name': 'CONTRIBUYENTE SIN UBICACION SA',
            'vat': '888888888-8-2015',
            'email': 'sinubic@test.pa',
            'street': 'Calle Test',
            'country_id': cls.pa_country.id,
            'l10n_pa_edi_customer_type': '01',
            'l10n_pa_edi_tipo_contribuyente': '2',
            'l10n_pa_edi_dv': '12',
            'l10n_pa_edi_codigoubicacion': '',  # vacío — PAC rechazará
            'l10n_pa_edi_checked': True,
        })

        # Partner tipo 02 — Consumidor Final
        cls.partner_consumidor = cls.env['res.partner'].create({
            'name': 'CONSUMIDOR FINAL',
            'country_id': cls.pa_country.id,
            'l10n_pa_edi_customer_type': '02',
        })

        # Partner tipo 04 — Extranjero
        cls.partner_extranjero = cls.env['res.partner'].create({
            'name': 'FOREIGN CORP',
            'l10n_pa_edi_customer_type': '04',
            'l10n_pa_edi_tipo_identificacion': '01',
            'l10n_pa_edi_nro_identificacion_extranjero': 'P987654321',
        })

        # Producto de servicio sin impuesto (simplifica el setup)
        cls.product = cls.env['product.product'].create({
            'name': 'Servicio FEL Test',
            'list_price': 100.0,
            'type': 'service',
            'taxes_id': [(5, 0, 0)],  # sin impuestos
        })

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _make_invoice(self, partner=None, price=100.0):
        partner = partner or self.partner_consumidor
        line = {
            'name': 'Servicio Test',
            'quantity': 1,
            'price_unit': price,
            'product_id': self.product.id,
        }
        if self.income_account:
            line['account_id'] = self.income_account.id
        return self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'journal_id': self.journal.id,
            'invoice_line_ids': [(0, 0, line)],
        })

    def _add_payment(self, move, forma='02', valor=None, desc=None):
        vals = {
            'move_id': move.id,
            'forma_pago_fact': forma,
            'valor_cuota_pagada': (
                valor if valor is not None else move.amount_total),
        }
        if desc:
            vals['desc_forma_pago'] = desc
        return self.env['account.move.dgi.payment'].create(vals)

    def _add_plazo(self, move, payment, offset_days=30, valor=None):
        return self.env['account.move.dgi.payment.plazo'].create({
            'move_id': move.id,
            'payment_id': payment.id,
            'fecha_vence_cuota': date.today() + timedelta(days=offset_days),
            'valor_cuota': (
                valor if valor is not None else move.amount_total),
        })

    @contextmanager
    def _patch_ws(self, mock_result=None):
        """Mock de zeep.Client + descargas PDF/XML para pruebas de _post()."""
        if mock_result is None:
            mock_result = MOCK_ENVIAR_OK
        mock_client = MagicMock()
        mock_client.service.Enviar.return_value = mock_result
        AccountMove = type(self.env['account.move'])
        with patch('odoo.addons.l10n_pa_edi.models.account_move.zeep.Client',
                   return_value=mock_client), \
             patch.object(AccountMove, 'dowload_l10n_pa_edit_pdf',
                          return_value=True), \
             patch.object(AccountMove, 'dowload_l10n_pa_edit_xml',
                          return_value=True):
            yield mock_client


# ─────────────────────────────────────────────────────────────────────────────
# 1. Validación de formas de pago DGI
# ─────────────────────────────────────────────────────────────────────────────

class TestDgiPaymentValidation(TestInvoiceBase):
    """Tests de _l10n_pa_validate_dgi_payments()."""

    def test_sin_forma_pago_lanza_error(self):
        move = self._make_invoice()
        with self.assertRaises(UserError) as ctx:
            move._l10n_pa_validate_dgi_payments()
        self.assertIn('forma de pago', ctx.exception.args[0].lower())

    def test_codigo_99_sin_descripcion_lanza_error(self):
        move = self._make_invoice()
        self._add_payment(move, forma='99')  # sin desc_forma_pago
        with self.assertRaises(UserError) as ctx:
            move._l10n_pa_validate_dgi_payments()
        self.assertIn('descripción', ctx.exception.args[0].lower())

    def test_valor_cero_lanza_error(self):
        move = self._make_invoice()
        self._add_payment(move, forma='02', valor=0.0)
        with self.assertRaises(UserError) as ctx:
            move._l10n_pa_validate_dgi_payments()
        self.assertIn('mayor a cero', ctx.exception.args[0].lower())

    def test_pago_efectivo_valido_no_lanza_error(self):
        move = self._make_invoice()
        self._add_payment(move, forma='02')
        move._l10n_pa_validate_dgi_payments()  # no debe lanzar

    def test_pago_99_con_descripcion_valido(self):
        move = self._make_invoice()
        self._add_payment(move, forma='99', desc='Pago por convenio especial')
        move._l10n_pa_validate_dgi_payments()  # no debe lanzar

    def test_multiples_pagos_uno_invalido_lanza_error(self):
        move = self._make_invoice()
        self._add_payment(move, forma='02', valor=50.0)
        self._add_payment(move, forma='99', valor=50.0)  # 99 sin desc
        with self.assertRaises(UserError):
            move._l10n_pa_validate_dgi_payments()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Construcción de formas de pago (get_forma_pago)
# ─────────────────────────────────────────────────────────────────────────────

class TestGetFormaPago(TestInvoiceBase):
    """Tests de get_forma_pago() — valida estructura del dict enviado a la DGI."""

    def test_total_no_coincide_lanza_error(self):
        move = self._make_invoice(price=100.0)  # amount_total = 100
        self._add_payment(move, forma='02', valor=50.0)  # suma < total
        with self.assertRaises(UserError) as ctx:
            move.get_forma_pago(move.amount_total)
        self.assertIn('no coincide', ctx.exception.args[0].lower())

    def test_credito_sin_plazos_lanza_error(self):
        move = self._make_invoice()
        self._add_payment(move, forma='01')  # crédito sin plazos
        with self.assertRaises(UserError) as ctx:
            move.get_forma_pago(move.amount_total)
        self.assertIn('plazo', ctx.exception.args[0].lower())

    def test_suma_plazos_no_coincide_con_cuota_lanza_error(self):
        move = self._make_invoice(price=100.0)
        pay = self._add_payment(move, forma='01', valor=100.0)
        self._add_plazo(move, pay, valor=60.0)  # 60 de 100 → no coincide
        with self.assertRaises(UserError) as ctx:
            move.get_forma_pago(move.amount_total)
        self.assertIn('plazos', ctx.exception.args[0].lower())

    def test_efectivo_solo_construye_lista_correcta(self):
        move = self._make_invoice(price=100.0)
        self._add_payment(move, forma='02')
        fp = move.get_forma_pago(move.amount_total)
        self.assertEqual(len(fp), 1)
        self.assertEqual(fp[0]['formaPagoFact'], '02')
        self.assertEqual(fp[0]['valorCuotaPagada'], '100.00')

    def test_mixto_credito_efectivo_construye_dos_entradas(self):
        """Crédito 70 + Efectivo 30 → dos entradas, ninguna es all_credit."""
        move = self._make_invoice(price=100.0)
        pay_cred = self._add_payment(move, forma='01', valor=70.0)
        self._add_payment(move, forma='02', valor=30.0)
        self._add_plazo(move, pay_cred, valor=70.0)
        fp = move.get_forma_pago(move.amount_total)
        tipos = [p['formaPagoFact'] for p in fp]
        self.assertIn('01', tipos)
        self.assertIn('02', tipos)
        all_credit = all(p['formaPagoFact'] == '01' for p in fp)
        self.assertFalse(all_credit)  # mixto, no todo crédito

    def test_credito_con_dos_plazos_genera_una_entrada_por_plazo(self):
        """Un pago crédito con 2 plazos → 2 entradas formaPago."""
        move = self._make_invoice(price=100.0)
        pay = self._add_payment(move, forma='01')
        self._add_plazo(move, pay, offset_days=30, valor=60.0)
        self._add_plazo(move, pay, offset_days=60, valor=40.0)
        fp = move.get_forma_pago(move.amount_total)
        creditos = [p for p in fp if p['formaPagoFact'] == '01']
        self.assertEqual(len(creditos), 2)
        montos = sorted(float(p['valorCuotaPagada']) for p in creditos)
        self.assertEqual(montos, [40.0, 60.0])

    def test_codigo_99_incluye_descripcion_en_dict(self):
        move = self._make_invoice()
        self._add_payment(move, forma='99', desc='Pago por canje de puntos')
        fp = move.get_forma_pago(move.amount_total)
        self.assertEqual(fp[0]['formaPagoFact'], '99')
        self.assertIn('descFormaPago', fp[0])
        self.assertEqual(fp[0]['descFormaPago'], 'Pago por canje de puntos')

    def test_transferencia_construye_lista_correcta(self):
        move = self._make_invoice()
        self._add_payment(move, forma='08')  # Transferencia bancaria
        fp = move.get_forma_pago(move.amount_total)
        self.assertEqual(fp[0]['formaPagoFact'], '08')


# ─────────────────────────────────────────────────────────────────────────────
# 3. Diccionario de cliente por tipo (tipoClienteFE)
# ─────────────────────────────────────────────────────────────────────────────

class TestDictPartnerInvoice(TestInvoiceBase):
    """Tests de _get_dic_parnet_invoice() — estructura del bloque cliente."""

    def test_contribuyente_tipo_fe_es_01(self):
        move = self._make_invoice(partner=self.partner_contrib)
        d = move._get_dic_parnet_invoice()
        self.assertEqual(d['tipoClienteFE'], '01')

    def test_contribuyente_incluye_ruc_y_dv(self):
        move = self._make_invoice(partner=self.partner_contrib)
        d = move._get_dic_parnet_invoice()
        self.assertEqual(d['numeroRUC'], '155596713-2-2015')
        self.assertIn('digitoVerificadorRUC', d)

    def test_contribuyente_incluye_codigo_ubicacion(self):
        move = self._make_invoice(partner=self.partner_contrib)
        d = move._get_dic_parnet_invoice()
        self.assertIn('codigoUbicacion', d)
        self.assertEqual(d['codigoUbicacion'], '8-8-8')

    def test_contribuyente_codigo_ubicacion_vacio_pasa_vacio_al_dict(self):
        """Código de ubicación vacío → se envía '' al PAC (el PAC lo rechaza, no Odoo)."""
        move = self._make_invoice(partner=self.partner_contrib_sin_ubicacion)
        d = move._get_dic_parnet_invoice()
        self.assertIn('codigoUbicacion', d)
        self.assertFalse(d['codigoUbicacion'])  # cadena vacía

    def test_consumidor_tipo_fe_es_02(self):
        move = self._make_invoice(partner=self.partner_consumidor)
        d = move._get_dic_parnet_invoice()
        self.assertEqual(d['tipoClienteFE'], '02')

    def test_consumidor_razon_social_es_consumidor_final(self):
        move = self._make_invoice(partner=self.partner_consumidor)
        d = move._get_dic_parnet_invoice()
        self.assertEqual(d['razonSocial'], 'CONSUMIDOR FINAL')

    def test_consumidor_no_incluye_ruc(self):
        move = self._make_invoice(partner=self.partner_consumidor)
        d = move._get_dic_parnet_invoice()
        self.assertNotIn('numeroRUC', d)
        self.assertNotIn('digitoVerificadorRUC', d)

    def test_consumidor_no_incluye_codigo_ubicacion(self):
        move = self._make_invoice(partner=self.partner_consumidor)
        d = move._get_dic_parnet_invoice()
        self.assertNotIn('codigoUbicacion', d)

    def test_extranjero_tipo_fe_es_04(self):
        move = self._make_invoice(partner=self.partner_extranjero)
        d = move._get_dic_parnet_invoice()
        self.assertEqual(d['tipoClienteFE'], '04')

    def test_extranjero_incluye_tipo_y_numero_identificacion(self):
        move = self._make_invoice(partner=self.partner_extranjero)
        d = move._get_dic_parnet_invoice()
        self.assertIn('tipoIdentificacion', d)
        self.assertEqual(d['tipoIdentificacion'], '01')
        self.assertIn('nroIdentificacionExtranjero', d)
        self.assertEqual(d['nroIdentificacionExtranjero'], 'P987654321')

    def test_extranjero_no_incluye_ruc_ni_ubicacion(self):
        move = self._make_invoice(partner=self.partner_extranjero)
        d = move._get_dic_parnet_invoice()
        self.assertNotIn('numeroRUC', d)
        self.assertNotIn('codigoUbicacion', d)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Envío al PAC — _post() con WS mockeado
# ─────────────────────────────────────────────────────────────────────────────

class TestPostInvoice(TestInvoiceBase):
    """Tests de _post() con zeep.Client mockeado."""

    # ── Flujo exitoso ──────────────────────────────────────────────────────

    def test_envio_exitoso_guarda_cufe(self):
        move = self._make_invoice()
        self._add_payment(move, forma='02')
        with self._patch_ws():
            move.action_post()
        self.assertEqual(move.l10n_pa_dgi_cufe, MOCK_ENVIAR_OK['cufe'])

    def test_envio_exitoso_guarda_estado_process(self):
        move = self._make_invoice()
        self._add_payment(move, forma='02')
        with self._patch_ws():
            move.action_post()
        self.assertEqual(move.l10n_pa_edi_status, 'process')

    def test_envio_exitoso_guarda_protocolo_autorizacion(self):
        move = self._make_invoice()
        self._add_payment(move, forma='02')
        with self._patch_ws():
            move.action_post()
        self.assertEqual(
            move.l10n_pa_auth_protocol,
            MOCK_ENVIAR_OK['nroProtocoloAutorizacion'],
        )

    def test_envio_exitoso_guarda_numero_documento_fiscal(self):
        move = self._make_invoice()
        self._add_payment(move, forma='02')
        with self._patch_ws():
            move.action_post()
        self.assertTrue(move.l10n_pa_no_doc_factura)

    def test_folio_enviado_al_pac_coincide_con_campo(self):
        """El numeroDocumentoFiscal enviado al PAC es el mismo que queda en el campo."""
        move = self._make_invoice()
        self._add_payment(move, forma='02')
        folio_capturado = {}

        def capturar(**kwargs):
            trans = kwargs['documento']['datosTransaccion']
            folio_capturado['numero'] = trans['numeroDocumentoFiscal']
            return MOCK_ENVIAR_OK

        mock_client = MagicMock()
        mock_client.service.Enviar.side_effect = capturar
        AccountMove = type(self.env['account.move'])
        with patch('odoo.addons.l10n_pa_edi.models.account_move.zeep.Client',
                   return_value=mock_client), \
             patch.object(AccountMove, 'dowload_l10n_pa_edit_pdf',
                          return_value=True), \
             patch.object(AccountMove, 'dowload_l10n_pa_edit_xml',
                          return_value=True):
            move.action_post()

        self.assertTrue(folio_capturado.get('numero'))
        self.assertEqual(move.l10n_pa_no_doc_factura, folio_capturado['numero'])

    # ── Formas de pago — validaciones previas al WS ───────────────────────

    def test_sin_forma_pago_autocrea_efectivo_y_llama_ws(self):
        """Sin DGI payment explícito → _post() auto-crea efectivo y llama a Enviar()."""
        move = self._make_invoice()
        with self._patch_ws() as mock_client:
            move.action_post()
        mock_client.service.Enviar.assert_called_once()
        self.assertEqual(len(move.dgi_payment_ids), 1)
        self.assertEqual(move.dgi_payment_ids[0].forma_pago_fact, '02')

    # ── Errores del WS ─────────────────────────────────────────────────────

    def test_error_ws_resultado_error_lanza_user_error(self):
        move = self._make_invoice()
        self._add_payment(move, forma='02')
        with self._patch_ws(MOCK_ENVIAR_ERROR):
            with self.assertRaises(UserError) as ctx:
                with self.env.cr.savepoint():
                    move.action_post()
        self.assertIn('tasaITBMS', ctx.exception.args[0])

    def test_codigo_102_lanza_user_error_con_mensaje_duplicado(self):
        move = self._make_invoice()
        self._add_payment(move, forma='02')
        with self._patch_ws(MOCK_ENVIAR_102):
            with self.assertRaises(UserError) as ctx:
                with self.env.cr.savepoint():
                    move.action_post()
        self.assertIn('102', ctx.exception.args[0])

    def test_codigo_102_crea_log_tipo_duplicate(self):
        move = self._make_invoice()
        self._add_payment(move, forma='02')
        with self._patch_ws(MOCK_ENVIAR_102):
            with self.assertRaises(UserError):
                with self.env.cr.savepoint():
                    move.action_post()
        # create_log / write_log hacen commit en cursor separado.
        # self.env.cr puede no ver esos commits luego de un rollback a savepoint.
        # Consultar con un cursor independiente (mismo aislamiento que create_log).
        with self.env.registry.cursor() as new_cr:
            new_cr.execute(
                "SELECT count(*) FROM log_fel_pan "
                "WHERE no_invoiced_id = %s AND type = 'duplicate'",
                [str(move.id)],
            )
            count = new_cr.fetchone()[0]
        self.assertGreater(count, 0, "Debe existir al menos un log tipo 'duplicate' para este move")

    # ── Formas de pago combinadas ─────────────────────────────────────────

    def test_pago_mixto_credito_efectivo_envio_exitoso(self):
        """Crédito 70 + Efectivo 30 = 100 → se envía y certifica correctamente."""
        move = self._make_invoice(price=100.0)
        pay_cred = self._add_payment(move, forma='01', valor=70.0)
        self._add_payment(move, forma='02', valor=30.0)
        self._add_plazo(move, pay_cred, valor=70.0)
        with self._patch_ws():
            move.action_post()
        self.assertEqual(move.l10n_pa_edi_status, 'process')

    def test_pago_credito_total_envio_exitoso(self):
        """100% crédito con un plazo → envío exitoso."""
        move = self._make_invoice(price=100.0)
        pay = self._add_payment(move, forma='01')
        self._add_plazo(move, pay, offset_days=30)
        with self._patch_ws():
            move.action_post()
        self.assertEqual(move.l10n_pa_edi_status, 'process')

    def test_pago_credito_dos_plazos_envio_exitoso(self):
        """Crédito con 2 plazos → envío exitoso y tiempoPago = 2 (todo crédito)."""
        move = self._make_invoice(price=100.0)
        pay = self._add_payment(move, forma='01')
        self._add_plazo(move, pay, offset_days=30, valor=60.0)
        self._add_plazo(move, pay, offset_days=60, valor=40.0)
        folio_capturado = {}

        def capturar(**kwargs):
            totales = kwargs['documento']['totalesSubTotales']
            folio_capturado['tiempoPago'] = totales.get('tiempoPago')
            return MOCK_ENVIAR_OK

        mock_client = MagicMock()
        mock_client.service.Enviar.side_effect = capturar
        AccountMove = type(self.env['account.move'])
        with patch('odoo.addons.l10n_pa_edi.models.account_move.zeep.Client',
                   return_value=mock_client), \
             patch.object(AccountMove, 'dowload_l10n_pa_edit_pdf',
                          return_value=True), \
             patch.object(AccountMove, 'dowload_l10n_pa_edit_xml',
                          return_value=True):
            move.action_post()

        self.assertEqual(folio_capturado.get('tiempoPago'), '2')  # todo crédito

    def test_pago_mixto_tiempoPago_es_3(self):
        """Crédito + efectivo → tiempoPago = 3 (mixto)."""
        move = self._make_invoice(price=100.0)
        pay_cred = self._add_payment(move, forma='01', valor=70.0)
        self._add_payment(move, forma='02', valor=30.0)
        self._add_plazo(move, pay_cred, valor=70.0)
        folio_capturado = {}

        def capturar(**kwargs):
            totales = kwargs['documento']['totalesSubTotales']
            folio_capturado['tiempoPago'] = totales.get('tiempoPago')
            return MOCK_ENVIAR_OK

        mock_client = MagicMock()
        mock_client.service.Enviar.side_effect = capturar
        AccountMove = type(self.env['account.move'])
        with patch('odoo.addons.l10n_pa_edi.models.account_move.zeep.Client',
                   return_value=mock_client), \
             patch.object(AccountMove, 'dowload_l10n_pa_edit_pdf',
                          return_value=True), \
             patch.object(AccountMove, 'dowload_l10n_pa_edit_xml',
                          return_value=True):
            move.action_post()

        self.assertEqual(folio_capturado.get('tiempoPago'), '3')  # mixto

    def test_pago_efectivo_tiempoPago_es_1(self):
        """Solo efectivo → tiempoPago = 1 (contado)."""
        move = self._make_invoice()
        self._add_payment(move, forma='02')
        folio_capturado = {}

        def capturar(**kwargs):
            totales = kwargs['documento']['totalesSubTotales']
            folio_capturado['tiempoPago'] = totales.get('tiempoPago')
            return MOCK_ENVIAR_OK

        mock_client = MagicMock()
        mock_client.service.Enviar.side_effect = capturar
        AccountMove = type(self.env['account.move'])
        with patch('odoo.addons.l10n_pa_edi.models.account_move.zeep.Client',
                   return_value=mock_client), \
             patch.object(AccountMove, 'dowload_l10n_pa_edit_pdf',
                          return_value=True), \
             patch.object(AccountMove, 'dowload_l10n_pa_edit_xml',
                          return_value=True):
            move.action_post()

        self.assertEqual(folio_capturado.get('tiempoPago'), '1')  # contado
