# Part of Odoo. See LICENSE file for full copyright and licensing details.
import random
from socket import gethostbyname, gaierror
from urllib.parse import urlparse
from odoo.exceptions import UserError, RedirectWarning, ValidationError
from odoo import fields, models, api, _, SUPERUSER_ID
from datetime import datetime
from pytz import timezone
from io import BytesIO
from base64 import b64encode
import logging
from datetime import datetime, timedelta
import qrcode
# from . import afip_errors
import base64
import zeep
import re

_logger = logging.getLogger(__name__)

class AccountMoveReversal(models.TransientModel):
    _inherit = "account.move.reversal"
    
    def reverse_moves(self, is_modify=False):
        res = super(AccountMoveReversal, self).reverse_moves(is_modify=is_modify)
        for move in self.move_ids:
            values = {
                'reference_doc_code': '1',
                'reason': self.reason,
                'move_id': res.get('res_id'),
                'source_move_id': move.id,
                'date': move.invoice_date,
                'origin_doc_number': move.name,
            }
            self.env['account.invoice.reference'].create(values)
            values = {
                'reference_doc_code': '1',
                'reason': self.reason,
                'move_id': move.id,
                'source_move_id': res.get('res_id'),
                'date': move.invoice_date,
            }
            self.env['account.invoice.reference'].create(values)
        return res

class AccountInvoiceReference(models.Model):
    _name = 'account.invoice.reference'
    _description = 'Cross Reference Docs for Chilean Electronic Invoicing'
    _rec_name = 'origin_doc_number'

    reference_doc_code = fields.Selection([
        ('1', '1. Cancels Referenced Document'),
        ('2', '2. Corrects Referenced Document Text'),
        ('3', '3. Corrects Referenced Document Amount')
    ], string='Codigo de referencia')
    reason = fields.Char(string='Motivo')
    move_id = fields.Many2one('account.move', ondelete='cascade', string='Documento Relacionado',required=True,index=True,)
    source_move_id = fields.Many2one('account.move', ondelete='cascade', string='Documento de origen')
    origin_doc_number = fields.Char(string='Nro documento origen', required=True, related='source_move_id.name')
    date = fields.Date(string='Fecha', required=True)


class AccountMove(models.Model):
    _inherit = "account.move"

    l10n_pa_dgi_cufe = fields.Char('CUFE', copy=False, readonly=True, states={'draft': [('readonly', False)]})
    l10n_pa_auth_protocol = fields.Char('Protocolo autorización', copy=False, readonly=True)
    l10n_pa_auth_dgi_reception_date = fields.Char('Fecha Recepcion DGI', copy=False, readonly=True)
    l10n_pa_auth_dgi_reception_date_fmt = fields.Char(
        string='Fecha recepción DGI formateada',
        compute='_compute_l10n_pa_auth_dgi_reception_date_fmt',
    )

    l10n_pa_dgi_qr_code = fields.Char(string='QR Code PA',
                                      help='This QR code is mandatory by the DGI in the electronic invoices when this ones are printed.')
    l10n_pa_edi_post_time = fields.Datetime(
        string="Posted Time", readonly=True, copy=False,
        help="Keep empty to use the current Panama central time")
    l10n_pa_edi_status = fields.Selection(
        selection=[
            ('none', "State not defined"),
            ('undefined', "Not Synced Yet"),
            ('not_found', "Not Found"),
            ('cancelled', "Cancelled"),
            ('process', "Processed"),
        ],
        string="DGI Status", readonly=True, copy=False, required=True, tracking=True,
        default='undefined',
        help="Refers to the status of the journal entry inside the DGI system.")
    qr_img = fields.Binary(string='Imagen QR', copy=False)
    reference_ids = fields.One2many('account.invoice.reference', 'move_id', readonly=True,
                                    states={'draft': [('readonly', False)]},
                                    string='Referencias Cruzadas de Documentos')
    l10n_pa_auth_protocol_date = fields.Char()
    l10n_pa_use_cfe = fields.Boolean(related='company_id.l10n_pa_use_cfe')
    l10n_pa_invoice_pdf = fields.Binary(string='PDF', copy=False, filters='*.pdf', help='PDF of the invoice')
    l10n_pa_invoice_xml = fields.Binary(string='XML', copy=False, filters='*.xml', help='XML of the invoice')
    l10n_pa_invoice_xml_text = fields.Text(string='XML Text', copy=False, help='XML of the invoice')
    l10n_pa_no_doc_factura = fields.Char(string='No. Documento Factura', copy=False)

    log_fel_count = fields.Integer(
        string='Logs FEL', compute='_compute_log_fel_count'
    )
    l10n_pa_last_xml_send = fields.Text(
        string='XML Enviado', compute='_compute_log_fel_count'
    )
    l10n_pa_last_response = fields.Text(
        string='Respuesta Recibida', compute='_compute_log_fel_count'
    )

    def _compute_l10n_pa_auth_dgi_reception_date_fmt(self):
        from datetime import datetime
        for move in self:
            raw = move.l10n_pa_auth_dgi_reception_date
            if raw:
                try:
                    dt = datetime.fromisoformat(raw)
                    move.l10n_pa_auth_dgi_reception_date_fmt = dt.strftime('%d de %B de %Y')
                except Exception:
                    move.l10n_pa_auth_dgi_reception_date_fmt = raw
            else:
                move.l10n_pa_auth_dgi_reception_date_fmt = ''

    def _compute_log_fel_count(self):
        for move in self:
            logs = self.env['log.fel.pan'].search(
                [('no_invoiced_id', '=', str(move.id))],
                order='date_hora desc', limit=1
            )
            move.log_fel_count = self.env['log.fel.pan'].search_count([
                ('no_invoiced_id', '=', str(move.id))
            ])
            move.l10n_pa_last_xml_send = logs.json_send if logs else False
            move.l10n_pa_last_response = logs.json_received if logs else False

    def action_view_fel_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Logs FEL',
            'res_model': 'log.fel.pan',
            'view_mode': 'list,form',
            'domain': [('no_invoiced_id', '=', str(self.id))],
            'context': {'default_no_invoiced_id': str(self.id)},
        }

    # METODO ' Para llamar antes de generar el XML / JSON EDI

    from odoo.exceptions import ValidationError

    def _l10n_pa_validate_dgi_payments(self):
        for move in self:
            if not move.l10n_pa_use_cfe:
                continue
            if move.move_type in ('in_invoice', 'in_refund', 'entry'):
                continue
            payments = move.dgi_payment_ids

            if not payments:
                raise UserError(
                    "Verifique sus datos:\n"
                    "Debe existir al menos una forma de pago DGI."
                )

            for pay in payments:
                if pay.forma_pago_fact == '99' and not pay.desc_forma_pago:
                    raise UserError(
                        "Verifique sus datos:\n"
                        "La descripción de la forma de pago es obligatoria cuando el código es 99."
                    )

                if pay.valor_cuota_pagada <= 0:
                    raise UserError(
                        "Verifique sus datos:\n"
                        "El valor de la cuota pagada debe ser mayor a cero."
                    )
    # CAMPO simple para el EDI
    dgi_payment_ids = fields.One2many(
        'account.move.dgi.payment',
        'move_id',
        string='Formas de Pago DGI'
    )

    # Parte de formaPagoFact en la Factura NO USADO / verificado 20260130
    l10n_pa_dgi_payment_code = fields.Selection([
        ('01', 'Crédito'),
        ('02', 'Efectivo'),
        ('03', 'Tarjeta Crédito'),
        ('04', 'Tarjeta Débito'),
        ('05', 'Tarjeta Fidelización'),
        ('06', 'Vale'),
        ('07', 'Tarjeta de Regalo'),
        ('08', 'Transferencia / Depósito Bancario'),
        ('09', 'Cheque'),
        ('99', 'Otro'),
    ],
        string='Forma de pago DGI',
        compute='_compute_l10n_pa_dgi_payment_code',
        store=True,
        readonly=False)

    # Agregado para los plazos cuando la forma de pago es = 01 Credito
    # dgi_plazo_ids = fields.One2many(
    #     comodel_name="account.move.dgi.payment.plazo",
    #     inverse_name="move_id",
    #     string="Plazos de Crédito DGI",
    #     readonly=False,
    # )
    plazo_ids = fields.One2many(
        comodel_name="account.move.dgi.payment.plazo",
        inverse_name="move_id",
        string="Plazos de Pago DGI"
    )

    @api.onchange('invoice_line_ids')
    def _onchange_invoice_line_ids_dgi_payment(self):
        if not self.l10n_pa_use_cfe:
            return
        if self.move_type not in ('out_invoice', 'out_refund'):
            return
        has_lines = any(line.product_id for line in self.invoice_line_ids)
        if has_lines and not self.dgi_payment_ids:
            self.dgi_payment_ids = [(0, 0, {
                'forma_pago_fact': '02',
                'valor_cuota_pagada': self.amount_total,
            })]
        elif self.dgi_payment_ids:
            pagos = list(self.dgi_payment_ids)
            if len(pagos) == 1:
                pagos[0].valor_cuota_pagada = self.amount_total

    @api.onchange('dgi_payment_ids')
    def _onchange_dgi_payment_ids(self):
        """Asignar payment_id a plazos huérfanos cuando se crea pago de crédito"""
        credit_payment = self.dgi_payment_ids.filtered(lambda p: p.forma_pago_fact == '01')[:1]

        if credit_payment:
            for plazo in self.plazo_ids:
                if not plazo.payment_id:
                    plazo.payment_id = credit_payment.id

    # Calculo automatico de formaPagoFact en la factura NO USADO / verificado 20260130
    def _compute_l10n_pa_dgi_payment_code(self):
        for move in self:
            # Crédito puro (sin pagos)
            # if move.move_type == 'out_invoice' and not move.payment_id:
            if move.move_type == 'out_invoice' and move.payment_state in ('not_paid', 'partial'):
                move.l10n_pa_dgi_payment_code = '01'
                continue

            payment_lines = move.line_ids.filtered(
                lambda l: l.payment_id and l.payment_id.payment_method_id.l10n_pa_dgi_payment_code
            )

            if payment_lines:
                move.l10n_pa_dgi_payment_code = (
                    payment_lines[0]
                    .payment_id
                    .payment_method_id
                    .l10n_pa_dgi_payment_code
                )
            else:
                move.l10n_pa_dgi_payment_code = '99'

    # Definimos forma de pago, referenciado en account_payment_method.py
    def _l10n_pa_get_dgi_payment_code(self):
        self.ensure_one()

        # Crédito: factura sin pagos registrados
        if not self.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable' and l.reconciled):
            return '01'

        payment_lines = self.line_ids.filtered(
            lambda l: l.payment_id and l.payment_id.payment_method_id.l10n_pa_dgi_payment_code
        )

        if payment_lines:
            return payment_lines[0].payment_id.payment_method_id.l10n_pa_dgi_payment_code

        return '99'

    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------
    def l10n_pa_update_files(self):
        for move in self:
            if not move.l10n_pa_no_doc_factura:
                raise UserError('No se ha generado el número de documento de la factura')
            move.dowload_l10n_pa_edit_pdf()
            move.dowload_l10n_pa_edit_xml()
    
    def get_download_invoice_pdf(self):
        
        return {
            'type': 'ir.actions.act_url',
            'url': '/download_invoice_pdf?invoice_id=' + str(self.id),
            'target': 'new',
        }
    def get_download_invoice_xml(self):
        return {
            'type': 'ir.actions.act_url',
            'url': '/download_invoice_xml?invoice_id=' + str(self.id),
            'target': 'new',
        }

    def _data_x_dowload_pdf_xml(self):
        wsdl = self.get_wsdl()
        tokenempresa, tokenPassword = self.get_tokens()

        punto = self._l10n_pa_edi_get_punto(self)

        if self.move_type == 'out_refund':
            tipo_doc = '04' if (self.reversed_entry_id and self.reversed_entry_id.l10n_pa_dgi_cufe) else '06'
        else:
            tipo_doc = '01'

        data = {
            "tokenEmpresa": tokenempresa,
            "tokenPassword": tokenPassword,
            "datosDocumento": {
                "codigoSucursalEmisor": self._l10n_pa_edi_get_codigo_sucursal(self),
                "numeroDocumentoFiscal": self.l10n_pa_no_doc_factura,
                "puntoFacturacionFiscal": punto,
                "tipoDocumento": tipo_doc,
                "tipoEmision": "01",
            },
        }
        # Verifica que el endpoint este disponible
        parsed_url = urlparse(wsdl)
        try:
            gethostbyname(parsed_url.hostname)
        except gaierror:
            raise UserError(
                "No se puede resolver el endpoint del PAC configurado.\n"
                "Revise la URL del ambiente FEL o la conectividad DNS."
            )

        cliente = zeep.Client(wsdl=wsdl)
        return cliente, data

    def dowload_l10n_pa_edit_pdf(self):
        for move in self:
            try:
                cliente, data = move._data_x_dowload_pdf_xml()
                res = cliente.service.DescargaPDF(**data)
                if res['codigo'] == '200':
                    move.l10n_pa_invoice_pdf = res['documento']
                    return True
                else:
                    raise UserError('PAC DescargaPDF código %s: %s' % (res.get('codigo'), res.get('mensaje')))
            except Exception as e:
                move.create_log({
                    'name': 'FEL PDF - %s' % move.name,
                    'state': 'done',
                    'type': 'error_file',
                    'no_invoiced_id': move.id,
                    'message': str(e),
                    'nodocumentofiscal': move.l10n_pa_no_doc_factura,
                    'json_received': 'Error al descargar el PDF de la factura',
                })
                raise

    def dowload_l10n_pa_edit_xml(self):
        for move in self:
            try:
                cliente, data = move._data_x_dowload_pdf_xml()
                res = cliente.service.DescargaXML(**data)
                if res['codigo'] == '200':
                    move.l10n_pa_invoice_xml = res['documento']
                    move.l10n_pa_invoice_xml_text = base64.b64decode(res['documento']).decode('utf-8')
                    return True
                else:
                    raise UserError('PAC DescargaXML código %s: %s' % (res.get('codigo'), res.get('mensaje')))
            except Exception as e:
                move.create_log({
                    'name': 'FEL XML - %s' % move.name,
                    'state': 'done',
                    'type': 'error_file',
                    'no_invoiced_id': move.id,
                    'message': str(e),
                    'nodocumentofiscal': move.l10n_pa_no_doc_factura,
                    'json_received': 'Error al descargar el XML de la factura',
                })
                raise
                
    def _get_l10n_pa_edi_issued_address(self):
        self.ensure_one()
        return self.company_id.partner_id.commercial_partner_id

    # Guardamos el tipo de documento en una variable para poder usarlo en la impresión de la factura
    l10n_pa_edi_tipo_documento_desc = fields.Char(
        string='Tipo Documento FEL',
        compute='_compute_l10n_pa_edi_tipo_documento_desc',
    )
    @api.depends('move_type', 'reversed_entry_id', 'reversed_entry_id.l10n_pa_dgi_cufe')
    def _compute_l10n_pa_edi_tipo_documento_desc(self):
        for move in self:
            if move.move_type == 'out_invoice':
                move.l10n_pa_edi_tipo_documento_desc = '01-Factura de operación interna'
            elif move.move_type == 'out_refund':
                move.l10n_pa_edi_tipo_documento_desc = (
                    '04-Nota de Crédito referente a una FE'
                    if (move.reversed_entry_id and move.reversed_entry_id.l10n_pa_dgi_cufe)
                    else '06-Nota de Crédito genérica'
                )
            else:
                move.l10n_pa_edi_tipo_documento_desc = False
    # Termina tipo de documento para impresion en factura
    @api.model
    def _l10n_pa_edi_get_cfdi_partner_timezone(self, partner):
        # By default, takes the central area timezone
        return timezone('America/Panama')

    # Compute methods

    def get_wsdl(self):
        self = self.sudo()
        company = self.env.company
        wsdl_url = company.l10n_pa_ws_wsdl_url
        return wsdl_url

    def get_tokens(self):
        self = self.sudo()
        company = self.env.company
        tokenempresa = company.l10n_pa_ws_user_fname
        tokenPassword = company.l10n_pa_ws_token_fname
        return tokenempresa, tokenPassword

    def get_tasal_tbms(self, invoice_line):
        tasal_tbms_map = {
            0: '00',
            7: '01',
            10: '02',
            15: '03',
        }
        if invoice_line.tax_ids:
            tax_amount = invoice_line.tax_ids[0].amount
            if tasal_tbms_map.get(int(tax_amount)):
                return tasal_tbms_map[int(tax_amount)]
            else:
                return '01'

    def get_tax_rate(self, invoice_line):
        if invoice_line.tax_ids:
            tax_amount = invoice_line.tax_ids[0].amount
            tax_rate = tax_amount/100 if tax_amount else 0
            return tax_rate
        return 0.07

    def get_forma_pago(self, totalFactura):
        self.ensure_one()

        # 1) Si existen formas de pago DGI, USAMOS ESAS
        if self.dgi_payment_ids:
            total = sum(self.dgi_payment_ids.mapped("valor_cuota_pagada"))
            if round(total, 2) != round(totalFactura, 2):
                raise UserError(
                    "La suma de las formas de pago DGI no coincide con el total de la factura."
                )

            forma_pago = []
            for pago in self.dgi_payment_ids:
                if pago.forma_pago_fact == '01':
                    # DGI: un formaPago por cada pagoPlazo (ocurrencias deben coincidir)
                    plazos = pago.plazo_ids.filtered(lambda p: p.fecha_vence_cuota)
                    if not plazos:
                        plazos = self.plazo_ids.filtered(
                            lambda p: p.fecha_vence_cuota and (not p.payment_id or p.payment_id == pago)
                        )
                    if not plazos:
                        raise UserError(
                            "La forma de pago Crédito requiere al menos un plazo de pago con fecha de vencimiento."
                        )
                    suma_plazos = sum(p.valor_cuota or 0.0 for p in plazos)
                    if round(suma_plazos, 2) != round(pago.valor_cuota_pagada, 2):
                        raise UserError(
                            "Los plazos del pago Crédito (%.2f) no coinciden con el valor del pago (%.2f).\n"
                            "Los plazos deben cubrir únicamente la porción a crédito, no el total de la factura."
                            % (suma_plazos, pago.valor_cuota_pagada)
                        )
                    for plazo in plazos:
                        if not plazo.payment_id:
                            plazo.payment_id = pago.id
                        forma_pago.append({
                            "formaPagoFact": "01",
                            "valorCuotaPagada": "%.2f" % (plazo.valor_cuota or 0.0),
                        })
                else:
                    item = {
                        "formaPagoFact": pago.forma_pago_fact,
                        "valorCuotaPagada": "%.2f" % pago.valor_cuota_pagada,
                    }
                    if pago.forma_pago_fact == '99' and pago.desc_forma_pago:
                        item["descFormaPago"] = pago.desc_forma_pago
                    forma_pago.append(item)

            return forma_pago

        # 2) Fallback SOLO si no hay pagos DGI (no recomendado, pero seguro)
        return [{
            "formaPagoFact": "02",  # Efectivo
            "descFormaPago": " ",
            "valorCuotaPagada": "%.2f" % totalFactura,
        }]

    # Buttons
    def _is_dummy_afip_validation(self):
        self.ensure_one()
        return self.company_id._get_environment_type() == 'testing' and \
               not self.company_id.sudo().l10n_ar_afip_ws_crt or not self.company_id.sudo().l10n_ar_afip_ws_key

    def tax_amount(self, tax, cantidad, precio_unitario):
        """ Verifica si el impuesto tiene un monto fijo, porcentaje o ambos """
        if tax.amount_type == 'fixed':
            return tax.amount * cantidad
        elif tax.amount_type == 'percent':
            return (tax.amount / 100) * cantidad * precio_unitario
        return 0
    
    def _get_dic_parnet_invoice(self):
        type_partner = self.partner_id.l10n_pa_edi_customer_type or '01'
        general = {
            "tipoClienteFE": type_partner,
            
        }
        # Contribuyente
        if type_partner == '01':
            general.update({
                "tipoContribuyente": self.partner_id.l10n_pa_edi_tipo_contribuyente or '2',
                "numeroRUC": self.partner_id.vat,
                "digitoVerificadorRUC": (self.partner_id.l10n_pa_edi_dv or '').zfill(2),
                "pais": self.country_code or 'PA',
                "razonSocial": self.partner_id.name or "CONSUMIDOR FINAL",
                "direccion": self.partner_id.street,
                "codigoUbicacion": self.partner_id.l10n_pa_edi_codigoubicacion,
                "provincia": self.partner_id.state_id.name or '8',
                "distrito": self.partner_id.district_id.name or '8',
                "corregimiento": self.partner_id.jurisdiction_id.name or '8',
            })
            return general
        # Consumidor Final
        if type_partner == '02':
            general.update({
                "pais": self.country_code or 'PA',
                #"numeroRUC": '000000000-0-0000',
                "razonSocial": "CONSUMIDOR FINAL",
            })
            return general
        # Gubernamental
        if type_partner == '03':
            general.update({
                "tipoContribuyente": self.partner_id.l10n_pa_edi_tipo_contribuyente or '2',
                "numeroRUC": self.partner_id.vat,
                "digitoVerificadorRUC": (self.partner_id.l10n_pa_edi_dv or '').zfill(2),
                "pais": self.country_code or 'PA',
                "razonSocial": self.partner_id.name or "CONSUMIDOR FINAL",
                "direccion": self.partner_id.street,
                "codigoUbicacion": self.partner_id.l10n_pa_edi_codigoubicacion,
                "provincia": self.partner_id.state_id.name,
                "distrito": self.partner_id.district_id.name,
                "corregimiento": self.partner_id.jurisdiction_id.name,
            })
            return general
        # Extranjero
        if type_partner == '04':
            general.update({
                "razonSocial": self.partner_id.name or "CONSUMIDOR FINAL",
                "tipoIdentificacion": self.partner_id.l10n_pa_edi_tipo_identificacion or '99',
                "nroIdentificacionExtranjero": self.partner_id.l10n_pa_edi_nro_identificacion_extranjero or '000000000-0-0000',
                "paisExtranjero": self.partner_id.l10n_pa_edi_paisextranjero.code or "PA",
            })
            return general
        raise UserError('Tipo de cliente no definido')

    def l10n_pa_create_dict(self):
        if not self:
            return
        # Si existen pagos DGI, el campo legacy queda fuera
        if self.dgi_payment_ids:
            self.l10n_pa_dgi_payment_code = False

        self = self.sudo()
        # Variants
        # datos default en company
        data_def_company = self.env.company._dict_data_FEL()
        tokenempresa, tokenPassword = self.get_tokens()
        listaItems = []
        listaTotalOTI = []
        totalITBMS = totalISC = 0.0
        MontoGravado = 0.0
        # Iterar por cada producto
        for product in self.invoice_line_ids.filtered(lambda x: x.display_type not in ('line_section', 'line_note')):
            # new variables
            listaItemOTI = []
            isc = itbms = False
            impuesto_all = 0.0
            descuento = (product.discount / 100) * product.price_unit if product.discount else 0.00

            # Iterar por cada impuesto
            for tax in product.tax_ids:
                # Variables
                # Calcular el monto del impuesto
                tax_amount = self.tax_amount(tax, 1, product.price_subtotal)
                tax_type = tax.l10n_pa_edi_tax_type
                # que no se repita el impuesto isc o itbms para el mismo producto
                if not tax_type or \
                    (tax_type.l10n_pa_edi_tax_type == 'isc' and  isc) or \
                    (tax_type.l10n_pa_edi_tax_type == 'itbms' and itbms): 
                    continue
                impuesto_all += tax_amount
                # Si el impuesto es OTI
                if tax_type.l10n_pa_edi_tax_type == 'oti' and tax_type.l10n_pa_edi_tax_code:
                    tax_item = {
                        "tasaOTI": tax_type.l10n_pa_edi_tax_code or '', 
                        "valorTasa": "%.2f" % tax_amount
                    }
                    # buscar uno con el mismo codigo y sumarle el valor
                    buscar = next((item for item in listaTotalOTI if item['codigoTotalOTI'] == tax_item['tasaOTI']), None)
                    if buscar:
                        buscar['valorTotalOTI'] = "%.2f" % (float(buscar['valorTotalOTI']) + float(tax_item['valorTasa']))
                    else:
                        # si no existe agregarlo
                        listaTotalOTI.append({
                            "codigoTotalOTI": tax_item['tasaOTI'],
                            "valorTotalOTI": tax_item['valorTasa']
                        })
                    listaItemOTI.append(tax_item)
                if tax_type.l10n_pa_edi_tax_type == 'isc':
                    isc = {
                        "tasaISC": tax_type.l10n_pa_edi_tax_code,
                        "valorISC": "%.2f" % (tax_amount)
                    }
                if tax_type.l10n_pa_edi_tax_type == 'itbms':
                    itbms = {
                        "tasaITBMS": tax_type.l10n_pa_edi_tax_code,
                        "valorITBMS": "%.2f" % (tax_amount)
                    }
            item = {
                "descripcion": product.name,
                "cantidad": "%.2f" % product.quantity,
                "precioUnitario": "%.2f" % product.price_unit,
                "precioUnitarioDescuento": "%.2f" % descuento,
                "precioItem": "%.2f" % (product.price_subtotal),
                "valorTotal": "0.00",
            }

            # Agregar impuestos al item
            if isc:
                item.update(isc)
                totalISC += float(isc['valorISC'])

            if itbms:
                item.update(itbms)
                totalITBMS += float(itbms['valorITBMS']) 
            if listaItemOTI:
                item['listaItemOTI'] = dict(oti=listaItemOTI)
            item["valorTotal"] = "%.2f" % (float(item['precioItem']) + impuesto_all)
            MontoGravado += impuesto_all 
            listaItems.append(item)
        product_list = dict(item=listaItems)
        totalFactura = self.amount_total
        
        ## Totales
        forma_pago = self.get_forma_pago(totalFactura)

        # Calcular tiempoPago según DGI
        # totalValorRecibido siempre = totalFactura (DGI lo exige así)
        _has_credit = any(p["formaPagoFact"] == "01" for p in forma_pago)
        _all_credit = all(p["formaPagoFact"] == "01" for p in forma_pago) if forma_pago else False
        if _all_credit:
            tiempo_pago = "2"   # Crédito: todos los pagos son crédito
        elif _has_credit:
            tiempo_pago = "3"   # Mixto: hay crédito y otras formas
        else:
            tiempo_pago = "1"   # Contado: ningún pago es crédito
        ### Termina Calcular totalValorRecibido y tiempoPago segun DGI

        totalesSubTotales = dict({
            "totalPrecioNeto": "%.2f" % (sum([float(item['precioItem']) for item in listaItems])),
            "totalITBMS": "%.2f" % totalITBMS,
        })
        if totalISC > 0:
            totalesSubTotales['totalISC'] = "%.2f" % totalISC
        #totalTodosItems	Total de todos los Ítems (Suma de ValorTotal).
        totalesSubTotales.update({
            "totalMontoGravado": "%.2f" % (MontoGravado or 0.00),
            "totalDescuento": "0.00",
            "totalAcarreoCobrado": "",
            "valorSeguroCobrado": "",
            "totalFactura": "%.2f" % (totalFactura),
            "totalValorRecibido": "%.2f" % totalFactura,
            "vuelto": "0.00",
            "tiempoPago": tiempo_pago,
            # "tiempoPago": "1",
            "nroItems": str(int(len([1* item.quantity for item in self.invoice_line_ids if item.display_type not in ('line_section', 'line_note')]))),
            "totalTodosItems": "%.2f" % (sum([float(item['valorTotal']) for item in listaItems])), 
            },
            listaFormaPago=dict(
                formaPago=forma_pago
            ))
        if listaTotalOTI:
            totalesSubTotales['listaTotalOTI'] = dict(totalOti=listaTotalOTI)

        # listaPagoPlazo: DGI requiere 1 entrada por formaPago, sumando totalFactura.
        # Crédito (01): una entrada por plazo definido. Otros: entrada con fecha de emisión.
        if _has_credit:
            invoice_date_str = (self.invoice_date or fields.Date.today()).strftime('%Y-%m-%dT00:00:00-05:00')
            plazo_list = []
            for pago in self.dgi_payment_ids:
                if pago.forma_pago_fact == '01':
                    plazos = self.env['account.move.dgi.payment.plazo'].sudo().search([
                        ('move_id', '=', self.id),
                        ('payment_id', '=', pago.id),
                        ('fecha_vence_cuota', '!=', False),
                    ], order='id')
                    for p in plazos:
                        plazo_item = {
                            'fechaVenceCuota': p.fecha_vence_cuota.strftime('%Y-%m-%dT00:00:00-05:00'),
                            'valorCuota': '%.2f' % (p.valor_cuota or 0.0),
                        }
                        if p.info_pago_cuota:
                            plazo_item['infoPagoCuota'] = p.info_pago_cuota
                        plazo_list.append(plazo_item)
                else:
                    plazo_list.append({
                        'fechaVenceCuota': invoice_date_str,
                        'valorCuota': '%.2f' % pago.valor_cuota_pagada,
                    })
            if plazo_list:
                totalesSubTotales['listaPagoPlazo'] = {'pagoPlazo': plazo_list}

        cfdi_date = datetime.combine(
            fields.Datetime.from_string(self.invoice_date if self.invoice_date else fields.Date.today()),
            self.l10n_pa_edi_post_time.time()).strftime('%Y-%m-%dT%H:%M:%S-05:00')

        ####### Tipo documento  ###########
        partner_id = self.partner_id
        if self.move_type == 'out_invoice':
            tipoDocumento = data_def_company['tipodocumento']
        elif self.move_type == 'out_refund':
            tipoDocumento = '04' if (self.reversed_entry_id and self.reversed_entry_id.l10n_pa_dgi_cufe) else '06'
        tipoClienteFE = partner_id.l10n_pa_edi_customer_type
        correoElectronico1 = partner_id.email
        if tipoClienteFE == '02':
            if not partner_id.email:
                correoElectronico1 = 'test@maga.biz'

        if tipoClienteFE == '01':
            if not correoElectronico1:
                raise UserError('Para los clientes contribuyentes debe definir un correo electrónico en su ficha')
            partner_id.check_ruc()

        # Reutilizar folio ya reservado para evitar huecos en DGI.
        # Solo se consume un nuevo número si no hay folio previo.
        if self.l10n_pa_no_doc_factura:
            folio_number = self.l10n_pa_no_doc_factura
            punto_facturacion = self._l10n_pa_edi_get_punto(self)
        else:
            folio_number, punto_facturacion = self._l10n_pa_edi_get_serie_and_folio(self)
        datos_transaccion = {
            "tipoEmision": data_def_company['tipoemision'],
            "tipoDocumento": tipoDocumento,
            "numeroDocumentoFiscal": folio_number,
            "puntoFacturacionFiscal": punto_facturacion,
            "naturalezaOperacion": "01",
            "tipoOperacion": 1,
            "destinoOperacion": data_def_company['destinooperacion'],
            "formatoCAFE": data_def_company['formatocafe_sd'],
            "entregaCAFE": data_def_company['entregacafe'],
            "envioContenedor": data_def_company['enviocontenedor'],
            "procesoGeneracion": data_def_company['procesogeneracion'],
            "tipoVenta": data_def_company['tipoventa'],
            "fechaEmision": cfdi_date,
            "cliente": self._get_dic_parnet_invoice(),
        }

        if tipoDocumento == '04':
            original = self.reversed_entry_id
            fecha_base = original.invoice_date or fields.Date.today()
            fecha_ref = fecha_base.strftime('%Y-%m-%dT00:00:00-05:00')
            datos_transaccion['listaDocsFiscalReferenciados'] = {
                'docFiscalReferenciado': [{
                    'fechaEmisionDocFiscalReferenciado': fecha_ref,
                    'cufeFEReferenciada': original.l10n_pa_dgi_cufe or '',
                    'nroFacturaPapel': '',
                    'nroFacturaImpFiscal': '',
                }]
            }

        ws_data = dict(
            tokenEmpresa=tokenempresa,
            tokenPassword=tokenPassword,
            documento=dict(
                codigoSucursalEmisor=self._l10n_pa_edi_get_codigo_sucursal(self),
                tipoSucursal="1",
                datosTransaccion=datos_transaccion,
                listaItems=product_list,
                totalesSubTotales=totalesSubTotales,
            )
        )
        return ws_data

    @api.model
    def _l10n_pa_edi_format_error_message(self, error_title, errors):
        bullet_list_msg = ''.join('<li>%s</li>' % msg for msg in errors)
        return '%s<ul>%s</ul>' % (error_title, bullet_list_msg)

    def put_qr_image(self):
        self = self.sudo()
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=20,
                           border=4, )
        qr.add_data(self.l10n_pa_dgi_qr_code)  # you can put here any attribute SKU in my case
        qr.make(fit=True)
        img = qr.make_image()
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        img_str = base64.b64encode(buffer.getvalue())
        self.qr_img = img_str

    def _get_pending_folio(self, move):
        """Devuelve el folio del último intento no-exitoso / no-duplicado, si existe.

        Usa cursor independiente para ver los registros comprometidos por create_log()
        fuera de la transacción principal (que puede haber hecho rollback).
        Un SELECT vía cursor separado NO adquiere bloqueo sobre account_move,
        por lo que no genera el error de serialización de PostgreSQL.

        Retorna el folio (str) o None si no hay intento previo reutilizable.
        """
        with self.env.registry.cursor() as new_cr:
            new_cr.execute(
                """
                SELECT nodocumentofiscal
                  FROM log_fel_pan
                 WHERE no_invoiced_id = %s
                   AND type NOT IN ('success', 'duplicate')
                   AND nodocumentofiscal IS NOT NULL
                   AND nodocumentofiscal != ''
                 ORDER BY id DESC
                 LIMIT 1
                """,
                [str(move.id)],
            )
            row = new_cr.fetchone()
            return row[0] if row else None

    def create_log(self, vals):
        with self.pool.cursor() as new_cr:
            new_env = api.Environment(new_cr, SUPERUSER_ID, self.env.context)
            record = new_env['log.fel.pan'].create(vals)
            new_cr.commit()
            return record
    @api.model
    def write_log(self, id, vals):
        with self.pool.cursor() as new_cr:
            new_env = api.Environment(new_cr, SUPERUSER_ID, self.env.context)
            record = new_env['log.fel.pan'].browse(id)
            record.write(vals)
            new_cr.commit()
            return record

    def _post(self, soft=True):
        try:
            if not self:
                return self
            context = dict(self._context or {})
            _logger.info(f'context: {context}')
            self = self.sudo()
            #res = super()._post(soft=soft)
            ##CNUEVO##
            if not context.get('is_not_post',False):
                # Asignar folio FEL para cada factura.
                # Si existe un intento previo fallido (error no-102), reutilizar el
                # mismo folio: el log.fel.pan lo persiste aunque la transacción principal
                # haya hecho rollback.  En caso de 102 (duplicado) o primer intento,
                # avanzar al siguiente número de la secuencia.
                # IMPORTANTE: el folio se escribe solo en la tx principal (ORM),
                # nunca en cursor separado, para evitar errores de serialización PG.
                for move in self:
                    if not (move.l10n_pa_use_cfe and move.move_type in ('out_invoice', 'out_refund')):
                        continue
                    pending = self._get_pending_folio(move)
                    if pending:
                        folio_number = pending
                    else:
                        folio_number, _punto = move._l10n_pa_edi_get_serie_and_folio(move)
                    move.l10n_pa_no_doc_factura = folio_number

                #  Forzar escritura de pagos y plazos
                self.env.flush_all()
                # Auto-crear pago DGI por defecto si la factura no tiene ninguno
                for move in self:
                    if (move.l10n_pa_use_cfe
                            and move.move_type in ('out_invoice', 'out_refund')
                            and not move.dgi_payment_ids):
                        self.env['account.move.dgi.payment'].create({
                            'move_id': move.id,
                            'forma_pago_fact': '02',
                            'valor_cuota_pagada': move.amount_total,
                        })
                self.env.flush_all()
                # Validar formas de pago DGI ANTES de postear
                self._l10n_pa_validate_dgi_payments()

                res = super(AccountMove, self)._post(soft=soft)
            else:
                res = super(AccountMove, self)._post()
            ####
            if any(not result.id or not result.l10n_pa_use_cfe for result in res):
                return res
            supplier_moves = ['in_invoice', 'in_refund', 'entry']
            for move in self:
                if move.move_type in supplier_moves:
                    return res
                issued_address = move._get_l10n_pa_edi_issued_address()
                tz = self._l10n_pa_edi_get_cfdi_partner_timezone(issued_address)
                tz_force = self.env['ir.config_parameter'].sudo().get_param('l10n_pa_edi_tz_%s' % move.journal_id.id,
                                                                            default=None)
                if tz_force:
                    tz = timezone(tz_force)
                move.l10n_pa_edi_post_time = fields.Datetime.to_string(datetime.now(tz))
            wsdl = self.get_wsdl()
            if not self.invoice_date:
                self.invoice_date = fields.Date.today()
            day_valida = self.invoice_date + timedelta(days=30)
            if fields.Date.today() > day_valida:
                raise UserError('La factura tiene más de 30 días calendarios')
            _logger.info('wsdl: %s' % (wsdl))
            cliente = zeep.Client(wsdl=wsdl)

            ws_data = self.l10n_pa_create_dict()
            _logger.info('ws_data Request: %s' % (ws_data))
            try:
                pos_order_id = self.env['pos.order'].search([('name', '=', self.invoice_origin)], limit=1)
            except Exception:
                pos_order_id = False
            folio_enviado = ws_data['documento']['datosTransaccion']['numeroDocumentoFiscal']
            log = self.create_log({
                'name': f'FEL - {self.name}',
                'type': 'error',
                'no_pos_order_id': pos_order_id.id if pos_order_id else False,
                'invoice_origin': self.invoice_origin,
                'no_pos_order_ref': pos_order_id.pos_reference if pos_order_id else False,
                'no_invoiced_id': self.id,
                'company_id': self.env.company.id,
                'json_send': str(ws_data),
                # Persistir el folio aquí para que sobreviva un rollback de la tx principal.
                # _get_pending_folio() lo leerá en el siguiente reintento.
                'nodocumentofiscal': folio_enviado,
            })
            _logger.info('log: %s' % (log))

            result = cliente.service.Enviar(**ws_data)
            self.write_log(log.id, {'json_received': str(result)})
            _logger.info('Enviar Response: %s' % (result))

            if result['codigo'] == '102':
                folio_dup = ws_data['documento']['datosTransaccion']['numeroDocumentoFiscal']
                self.write_log(log.id, {
                    'type': 'duplicate',
                    'state': 'done',
                    'message': 'Folio duplicado en PAC: %s' % folio_dup,
                    'nodocumentofiscal': folio_dup,
                })
                raise UserError(
                    "El número de documento %s ya está registrado en el PAC (código 102).\n\n"
                    "Vuelva a intentar — se asignará el siguiente número disponible de la secuencia."
                    % folio_dup
                )
            # Se imprime la respuesta a la solicitud del servicio
            if result['resultado'] == 'error':
                # usar cr  para crear un log usando consulta sql
                log = self.write_log(log.id, {
                    'name': f'FEL - {self.name}',
                    'state': 'done',
                    'type': 'error',
                    'no_invoiced_id': self.id,
                    'message': result['mensaje'],
                    'nodocumentofiscal': ws_data['documento']['datosTransaccion']['numeroDocumentoFiscal'],
                    'json_received': str(result)
                })
                # commit
                error_title = result['resultado']
                errors = str(result['mensaje'])
                msg = error_title + errors
                self.message_post(body=_("Electronic Invoice with errors <b>%s</b>", msg=msg))
                raise UserError(result['mensaje'])
            if result['codigo'] == '200':
                log = self.write_log(log.id, {
                    'type': 'success',
                    'state': 'done',
                    'message': str(result['mensaje']),
                    'nodocumentofiscal': ws_data['documento']['datosTransaccion']['numeroDocumentoFiscal']
                })
                # commit
                self.l10n_pa_no_doc_factura = ws_data['documento']['datosTransaccion']['numeroDocumentoFiscal']
                self.l10n_pa_dgi_cufe = result['cufe']
                self.l10n_pa_dgi_qr_code = result['qr']
                self.l10n_pa_auth_dgi_reception_date = result['fechaRecepcionDGI']
                self.l10n_pa_auth_protocol = result['nroProtocoloAutorizacion']
                self.l10n_pa_auth_protocol_date = self.l10n_pa_auth_protocol + ' de ' + self.l10n_pa_auth_dgi_reception_date
                self.put_qr_image()
                self.l10n_pa_edi_status = 'process'
                self.message_post(body=_("Electronic Invoice created successfully"))
                try:
                    self.dowload_l10n_pa_edit_pdf()
                except Exception as e:
                    _logger.warning("FEL: fallo descarga PDF para %s: %s", self.name, e)
                try:
                    self.dowload_l10n_pa_edit_xml()
                except Exception as e:
                    _logger.warning("FEL: fallo descarga XML para %s: %s", self.name, e)
                return res
        except ConnectionError:
            # No hay internet → marcar como contingencia
            self.write({
                'l10n_pa_fel_estado': 'contingencia'
            })
            return super()._post(soft=soft)
        except UserError:
            raise
        except Exception as e:
            raise UserError(
                "Error de conexion al PAC.\n"
                "Detalle técnico:\n%s" % e
            )


    def action_certificate(self):
        """
        Certifica la factura electrónica, siempre y cuando no haya pasado 30 días desde su fecha de emisión.
        """
        self.ensure_one()  # Asegura que el metodo se ejecute en un solo registro

        # Verificar si la facturación electrónica está habilitada
        if not self.l10n_pa_use_cfe:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': f'{self.name} no puede ser facturada',
                    'type': 'warning',
                    'message': 'La certificación electrónica no está habilitada.',
                    'sticky': True,
                }
            }

        # Verificar si la factura ha pasado 30 días desde su fecha de emisión
        if self.invoice_date:
            limit_date = self.invoice_date + timedelta(days=30)
            today = fields.Date.today()

            if today > limit_date:
                # Notificación de éxito
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Límite de tiempo',
                        'type': 'warning',
                        'message': f'ERROR {self.name}: Esta factura tiene más de 30 días calendarios.  Notificar al PAC.',
                        'sticky': True,
                    }
                }
            else:
                # Si no ha pasado 30 días, proceder con la certificación
                self.button_draft()  # Pasar a borrador
                self.action_post()   # Volver a publicar
                # Notificación de éxito
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Factura sin fecha',
                    'type': 'warning',
                    'message': f'La factura {self.name} no tiene fecha.',
                    'sticky': True,
                }
            }

    def certificate_records(self):
        """
        Certifica las facturas seleccionadas, siempre y cuando no hayan pasado 30 días desde su fecha de emisión.
        """
        moves = []  # Lista para almacenar facturas procesadas
        for move in self:
            # Si la factura no está en un estado válido para certificar, se omite
            if move.l10n_pa_use_cfe:
                if move.l10n_pa_edi_status == 'process':
                    moves.append(f'CERTIFICADAS: {move.name}')
                    continue
                elif move.l10n_pa_edi_status == 'cancelled':
                    moves.append(f'CANCELADAS: {move.name}')
                    continue
                elif move.l10n_pa_edi_status == 'not_found':
                    moves.append(f'NOT_FOUND: {move.name}')
                    continue
                elif move.l10n_pa_edi_status == 'none':
                    moves.append(f'SIN ESTADO: {move.name}')
                    continue
                try:
                    # Verificar si la factura está publicada y tiene estado "undefined"
                    if move.state == 'posted' and move.l10n_pa_edi_status == 'undefined':
                        # Calcular la fecha límite (30 días después de la fecha de emisión)
                        limit_date = move.invoice_date + timedelta(days=30)
                        today = fields.Date.today()

                        # Si la factura ha pasado los 30 días, se añade un error
                        if today > limit_date:
                            moves.append(f'ERROR {move.name}: Esta factura tiene más de 30 días calendarios. Notificar al PAC.')
                            continue  # Saltar al siguiente registro

                        # Si no ha pasado los 30 días, se intenta certificar
                        move.button_draft()  # Pasar a borrador
                        move.action_post()   # Volver a publicar
                        moves.append(f'CERTIFICADA: La factura {move.name} ha sido certificada.')  # Añadir a la lista de facturas procesadas

                except Exception as e:
                    # Capturar errores y añadirlos a la lista de errores
                    _logger.error(f'Error en la factura {move.name}: {e} (Línea {e.__traceback__.tb_lineno})')
                    moves.append(f'ERROR: Error en la factura {move.name}: {e} (Línea {e.__traceback__.tb_lineno})')
        if moves:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Historial de registros',
                    'type': 'warning',
                    'message': f'Historial: {", ".join(moves)}',
                    'sticky': True,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'FEL no activado',
                    'type': 'warning',
                    'message': 'Active el FEL para poder certificar las facturas.',
                    'sticky': True,
                }
            }

    @api.model
    def _l10n_pa_edi_get_codigo_sucursal(self, move):
        """Retorna codigoSucursalEmisor configurado en el diario."""
        return (move.journal_id.l10n_pa_edi_codigo_sucursal or '0000').zfill(4)

    @api.model
    def _l10n_pa_edi_get_punto(self, move):
        """Retorna puntoFacturacionFiscal sin consumir secuencia."""
        journal = move.journal_id
        company = move.company_id
        if journal.l10n_pa_edi_use_global_sequence:
            def_fields = company._get_res_partner_def_fields()
            return (def_fields.puntofacturacionfiscal or '001').zfill(3)
        return (journal.l10n_pa_edi_punto_facturacion or '001').zfill(3)

    def _l10n_pa_edi_get_serie_and_folio(self, move):
        journal = move.journal_id
        company = move.company_id
        is_nc = move.move_type == 'out_refund'

        if journal.l10n_pa_edi_use_global_sequence:
            if is_nc:
                sequence = company._get_l10n_pa_edi_sequence_nota_credito()
            else:
                sequence = company._get_l10n_pa_edi_sequence_factura()
            folio = sequence.next_by_id()
            def_fields = company._get_res_partner_def_fields()
            punto = (def_fields.puntofacturacionfiscal or '001').zfill(3)
            return str(int(folio)), punto

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

        if is_nc:
            if not journal.l10n_pa_edi_sequence_nc_id:
                seq_nc_code = 'l10n_pa_edi.seq.journal.nc.%d' % journal.id
                seq_nc = self.env['ir.sequence'].create({
                    'name': 'FEL Notas de Crédito - %s' % journal.name,
                    'code': seq_nc_code,
                    'padding': 10,
                    'number_next': 1,
                    'number_increment': 1,
                    'company_id': journal.company_id.id,
                })
                journal.sudo().write({'l10n_pa_edi_sequence_nc_id': seq_nc.id})
            sequence = journal.l10n_pa_edi_sequence_nc_id
        else:
            sequence = journal.l10n_pa_edi_sequence_id

        folio = sequence.next_by_id()
        punto = journal.l10n_pa_edi_punto_facturacion.zfill(3)
        return str(int(folio)), punto

    # @api.model_create_multi
    # def create(self, vals_list):
    #     moves = super().create(vals_list)
    #     for move in moves:
    #         for payment in move.dgi_payment_ids:
    #             for plazo in move.dgi_plazo_ids:
    #                 if not plazo.payment_id:
    #                     plazo.payment_id = payment.id
    #     return moves

    # CUANDO FORMA DE PAGO = CREDITO
    has_credit_payment = fields.Boolean(
        compute="_compute_has_credit_payment",
        store=True
    )

    @api.depends('dgi_payment_ids.forma_pago_fact')
    def _compute_has_credit_payment(self):
        for move in self:
            move.has_credit_payment = any(
                p.forma_pago_fact == '01'
                for p in move.dgi_payment_ids
            )

    # Termina forma Pago = Credito
