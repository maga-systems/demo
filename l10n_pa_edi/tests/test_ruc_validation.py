from unittest.mock import patch, MagicMock
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


MOCK_WSDL = 'http://fake-dgi-wsdl'
MOCK_TOKENS = ('TOKEN_EMPRESA', 'TOKEN_PASSWORD')


def make_dgi_response(codigo='200', razon_social='EMPRESA SA',
                      dv='5', afiliado_fe='SI'):
    """Factory de respuestas del WS DGI."""
    if codigo != '200':
        return {'codigo': codigo, 'infoRuc': None,
                'mensaje': 'Error', 'resultado': 'Error'}
    return {
        'codigo': codigo,
        'infoRuc': {
            'tipoRuc': '2',
            'ruc': '155596724-2-2015',
            'dv': dv,
            'razonSocial': razon_social,
            'afiliadoFE': afiliado_fe,
        },
        'mensaje': 'Procesado',
        'resultado': 'Procesado',
    }


class TestCheckRuc(TransactionCase):
    """
    Tests de check_ruc() con WS DGI mockeado.
    Cubre el flujo principal de consulta al WS.
    """

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({
            'name': 'Empresa Test',
            'vat': '155596724-2-2015',
            'country_id': self.env.ref('base.pa').id,
            'l10n_pa_edi_tipo_contribuyente': '2',
        })

    def _patch_ws(self, response):
        """Helper: mockea zeep + get_wsdl + get_tokens."""
        mock_client = MagicMock()
        mock_client.service.ConsultarRucDV.return_value = response

        zeep_patch = patch(
            'odoo.addons.l10n_pa_edi.models.res_partner.zeep.Client',
            return_value=mock_client
        )
        wsdl_patch = patch.object(
            type(self.env['account.move']),
            'get_wsdl', return_value=MOCK_WSDL
        )
        tokens_patch = patch.object(
            type(self.env['account.move']),
            'get_tokens', return_value=MOCK_TOKENS
        )
        return zeep_patch, wsdl_patch, tokens_patch

    # ── Flujo exitoso ─────────────────────────────────────────────────

    def test_codigo_200_actualiza_nombre(self):
        response = make_dgi_response(razon_social='TECNOLOGÍA PANAMEÑA SA')
        z, w, t = self._patch_ws(response)
        with z, w, t:
            self.partner.check_ruc()
        self.assertEqual(self.partner.name, 'TECNOLOGÍA PANAMEÑA SA')

    def test_codigo_200_actualiza_dv(self):
        response = make_dgi_response(dv='7')
        z, w, t = self._patch_ws(response)
        with z, w, t:
            self.partner.check_ruc()
        self.assertEqual(self.partner.l10n_pa_edi_dv, '7')

    def test_codigo_200_marca_checked(self):
        response = make_dgi_response()
        z, w, t = self._patch_ws(response)
        with z, w, t:
            self.partner.check_ruc()
        self.assertTrue(self.partner.l10n_pa_edi_checked)

    def test_codigo_200_postea_en_chatter(self):
        response = make_dgi_response()
        z, w, t = self._patch_ws(response)
        msg_count_before = len(self.partner.message_ids)
        with z, w, t:
            self.partner.check_ruc()
        self.assertGreater(len(self.partner.message_ids), msg_count_before)

    # ── Errores del WS ────────────────────────────────────────────────

    def test_codigo_100_token_invalido(self):
        response = make_dgi_response(codigo='100')
        z, w, t = self._patch_ws(response)
        with z, w, t:
            with self.assertRaises(UserError) as ctx:
                self.partner.check_ruc()
        self.assertIn('token', ctx.exception.args[0].lower())

    def test_codigo_102_contribuyente_no_inscrito(self):
        response = make_dgi_response(codigo='102')
        z, w, t = self._patch_ws(response)
        with z, w, t:
            with self.assertRaises(UserError) as ctx:
                self.partner.check_ruc()
        self.assertIn('inscrito', ctx.exception.args[0].lower())

    def test_codigo_desconocido_usa_fallback(self):
        response = make_dgi_response(codigo='999')
        z, w, t = self._patch_ws(response)
        with z, w, t:
            with self.assertRaises(UserError) as ctx:
                self.partner.check_ruc()
        self.assertIn('desconocido', ctx.exception.args[0].lower())

    # ── Validación previa al WS ───────────────────────────────────────

    def test_sin_vat_lanza_user_error_sin_llamar_ws(self):
        self.partner.vat = False
        with patch('odoo.addons.l10n_pa_edi.models.res_partner.zeep.Client') as mock_zeep:
            with self.assertRaises(UserError):
                self.partner.check_ruc()
            mock_zeep.assert_not_called()


class TestOnchangeCustomerType(TransactionCase):
    """
    Tests de defaults por tipo de cliente.
    """

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].new({
            'name': 'Test',
            'country_id': self.env.ref('base.pa').id,
        })

    def test_contribuyente_asigna_juridico(self):
        self.partner.l10n_pa_edi_customer_type = '01'
        self.partner.onchange_customer_type()
        self.assertEqual(self.partner.l10n_pa_edi_tipo_contribuyente, '2')

    def test_consumidor_final_asigna_natural(self):
        self.partner.l10n_pa_edi_customer_type = '02'
        self.partner.onchange_customer_type()
        self.assertEqual(self.partner.l10n_pa_edi_tipo_contribuyente, '1')

    def test_gobierno_asigna_juridico(self):
        self.partner.l10n_pa_edi_customer_type = '03'
        self.partner.onchange_customer_type()
        self.assertEqual(self.partner.l10n_pa_edi_tipo_contribuyente, '2')

    def test_extranjero_limpia_tipo_contribuyente(self):
        self.partner.l10n_pa_edi_customer_type = '04'
        self.partner.onchange_customer_type()
        self.assertFalse(self.partner.l10n_pa_edi_tipo_contribuyente)