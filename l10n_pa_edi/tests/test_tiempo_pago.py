"""
Tests para la detección de tiempoPago y construcción de listaPagoPlazo.

Reglas DGI:
  "1" = Contado  — ningún pago es crédito (01)
  "2" = Crédito  — todos los pagos son crédito (01)
  "3" = Mixto    — hay crédito (01) y otras formas de pago
"""
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


def _tiempo_pago(forma_pago_list):
    """Replica la lógica de tiempoPago de l10n_pa_create_dict."""
    has_credit = any(p["formaPagoFact"] == "01" for p in forma_pago_list)
    all_credit = all(p["formaPagoFact"] == "01" for p in forma_pago_list) if forma_pago_list else False
    if all_credit:
        return "2"
    elif has_credit:
        return "3"
    else:
        return "1"


class TestTiempoPagoLogic(TransactionCase):
    """Tests de la lógica pura de tiempoPago — sin tocar WS."""

    def test_contado_efectivo(self):
        """Un pago en efectivo → tiempoPago = 1."""
        fp = [{"formaPagoFact": "02", "valorCuotaPagada": "100.00"}]
        self.assertEqual(_tiempo_pago(fp), "1")

    def test_contado_tarjeta(self):
        """Un pago con tarjeta de crédito (03) → tiempoPago = 1 (no es crédito DGI)."""
        fp = [{"formaPagoFact": "03", "valorCuotaPagada": "100.00"}]
        self.assertEqual(_tiempo_pago(fp), "1")

    def test_contado_multiples_no_credito(self):
        """Varios pagos ninguno crédito → tiempoPago = 1."""
        fp = [
            {"formaPagoFact": "02", "valorCuotaPagada": "50.00"},
            {"formaPagoFact": "08", "valorCuotaPagada": "50.00"},
        ]
        self.assertEqual(_tiempo_pago(fp), "1")

    def test_credito_unico(self):
        """Un solo pago crédito (01) → tiempoPago = 2."""
        fp = [{"formaPagoFact": "01", "valorCuotaPagada": "100.00"}]
        self.assertEqual(_tiempo_pago(fp), "2")

    def test_credito_multiples_todos_01(self):
        """Dos pagos ambos crédito (01) → tiempoPago = 2, NO mixto."""
        fp = [
            {"formaPagoFact": "01", "valorCuotaPagada": "60.00"},
            {"formaPagoFact": "01", "valorCuotaPagada": "40.00"},
        ]
        self.assertEqual(_tiempo_pago(fp), "2")

    def test_mixto_credito_y_efectivo(self):
        """Crédito + efectivo → tiempoPago = 3."""
        fp = [
            {"formaPagoFact": "01", "valorCuotaPagada": "70.00"},
            {"formaPagoFact": "02", "valorCuotaPagada": "30.00"},
        ]
        self.assertEqual(_tiempo_pago(fp), "3")

    def test_mixto_credito_y_transferencia(self):
        """Crédito + transferencia → tiempoPago = 3."""
        fp = [
            {"formaPagoFact": "08", "valorCuotaPagada": "50.00"},
            {"formaPagoFact": "01", "valorCuotaPagada": "50.00"},
        ]
        self.assertEqual(_tiempo_pago(fp), "3")

    def test_lista_vacia(self):
        """Sin formas de pago → tiempoPago = 1 (contado por defecto)."""
        self.assertEqual(_tiempo_pago([]), "1")


class TestListaPagoPlazoORM(TransactionCase):
    """Tests de integración: plazo_ids se reflejan en listaPagoPlazo."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref('base.main_company')
        cls.partner = cls.env['res.partner'].search([
            ('customer_rank', '>', 0),
            ('vat', '!=', False),
        ], limit=1)
        if not cls.partner:
            cls.partner = cls.env['res.partner'].create({
                'name': 'Test Partner FEL',
                'vat': '155596713-2-2015',
                'customer_rank': 1,
            })

    def _make_move_with_credit_payment(self, plazos_vals):
        """Crea un account.move con pago crédito y los plazos indicados."""
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Servicio Test',
                'quantity': 1,
                'price_unit': 100.0,
            })],
        })
        payment = self.env['account.move.dgi.payment'].create({
            'move_id': move.id,
            'forma_pago_fact': '01',
            'valor_cuota_pagada': move.amount_total,
        })
        for vals in plazos_vals:
            self.env['account.move.dgi.payment.plazo'].create({
                'move_id': move.id,
                'payment_id': payment.id,
                **vals,
            })
        return move

    def test_plazo_ids_visible_desde_move(self):
        """Los plazos creados con move_id son accesibles via move.plazo_ids."""
        from datetime import date, timedelta
        move = self._make_move_with_credit_payment([
            {'fecha_vence_cuota': date.today() + timedelta(days=30), 'valor_cuota': 50.0},
            {'fecha_vence_cuota': date.today() + timedelta(days=60), 'valor_cuota': 50.0},
        ])
        self.assertEqual(len(move.plazo_ids), 2)

    def test_plazo_ids_construye_lista_pago_plazo(self):
        """Dos plazos → listaPagoPlazo tiene exactamente 2 items."""
        from datetime import date, timedelta
        move = self._make_move_with_credit_payment([
            {'fecha_vence_cuota': date.today() + timedelta(days=30), 'valor_cuota': 60.0},
            {'fecha_vence_cuota': date.today() + timedelta(days=60), 'valor_cuota': 57.0},
        ])
        plazo_list = []
        for plazo in move.plazo_ids:
            if plazo.fecha_vence_cuota:
                plazo_list.append({
                    'fechaVenceCuota': plazo.fecha_vence_cuota.strftime('%Y-%m-%dT00:00:00-05:00'),
                    'valorCuota': '%.2f' % (plazo.valor_cuota or 0.0),
                    'infoPagoCuota': plazo.info_pago_cuota or '',
                })
        self.assertEqual(len(plazo_list), 2)

    def test_plazo_sin_fecha_no_incluido(self):
        """Un plazo sin fecha de vencimiento no se incluye en listaPagoPlazo."""
        from datetime import date, timedelta
        move = self._make_move_with_credit_payment([
            {'fecha_vence_cuota': date.today() + timedelta(days=30), 'valor_cuota': 100.0},
            {'fecha_vence_cuota': False, 'valor_cuota': 0.0},  # sin fecha
        ])
        plazo_list = [
            p for p in move.plazo_ids if p.fecha_vence_cuota
        ]
        self.assertEqual(len(plazo_list), 1)

    def test_has_credit_cuando_forma_pago_01(self):
        """dgi_payment_ids con forma_pago_fact=01 → has_credit True."""
        from datetime import date, timedelta
        move = self._make_move_with_credit_payment([
            {'fecha_vence_cuota': date.today() + timedelta(days=30), 'valor_cuota': 107.0},
        ])
        has_credit = any(
            p.forma_pago_fact == '01' for p in move.dgi_payment_ids
        )
        self.assertTrue(has_credit)

    def test_no_has_credit_cuando_solo_efectivo(self):
        """dgi_payment_ids con solo efectivo → has_credit False."""
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Servicio Test',
                'quantity': 1,
                'price_unit': 100.0,
            })],
        })
        self.env['account.move.dgi.payment'].create({
            'move_id': move.id,
            'forma_pago_fact': '02',
            'valor_cuota_pagada': move.amount_total,
        })
        has_credit = any(
            p.forma_pago_fact == '01' for p in move.dgi_payment_ids
        )
        self.assertFalse(has_credit)
