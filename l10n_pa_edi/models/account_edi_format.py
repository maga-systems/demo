    # -*- coding: utf-8 -*-
from odoo import api, models, fields, tools, _
from odoo.tools.xml_utils import _check_with_xsd
from odoo.tools.float_utils import float_round, float_is_zero
from odoo.exceptions import UserError, RedirectWarning, ValidationError

import logging
import re
import base64
import json
import requests
import random
import string

from lxml import etree
from lxml.objectify import fromstring
from math import copysign
from datetime import datetime, timezone
from io import BytesIO
from zeep import Client
from zeep.transports import Transport
from json.decoder import JSONDecodeError

_logger = logging.getLogger(__name__)


class AccountEdiFormat(models.Model):
    _inherit = 'account.edi.format'

    # -------------------------------------------------------------------------
    # FE: Helpers
    # -------------------------------------------------------------------------

    @api.model
    def _l10n_pa_edi_get_cfdi_partner_timezone(self, partner):
        # By default, takes the central area timezone
        return timezone('America/Panama')

    def _post_invoice_edi(self, invoices):
        # OVERRIDE
        edi_result = super()._post_invoice_edi(invoices)
        if self.code != 'edi_thefactoryhka':
            return edi_result

        invoice = invoices  # No batching ensures that only one invoice is given as parameter

        for invoice in invoices:

            # == Check the configuration ==
            errors = self._l10n_pa_edi_check_configuration(invoice)
            if errors:
                edi_result[invoice] = {
                    'error': self._l10n_pa_edi_format_error_message(_("Invalid configuration:"), errors),
                }
                continue

            # == Generate the FE ==
            res = self._l10n_pa_edi_export_invoice_fe(invoice)
            print ('res -->>', res)
            if res.get('errors'):
                edi_result[invoice] = {
                    'error': self._l10n_pa_edi_format_error_message(_("Failure during the generation of the FE:"), res['errors']),
                }
                continue

            # == Call the web-service ==
            res = self._l10n_pa_edi_post_invoice_pac(invoice, res)

            edi_result[invoice] = {'success': True, 'attachment': False}

            # == Chatter ==
            invoice.with_context(no_new_invoice=True).message_post(
                body=_("The FE document was successfully created and signed by the government."),
            )
        return edi_result

    @api.model
    def _l10n_pa_edi_check_configuration(self, move):
        company = move.company_id
        pac_name = company.l10n_pa_edi_pac

        errors = []

        # == Check the credentials to call the PAC web-service ==
        if pac_name:
            pac_username = company.l10n_pa_ws_user_fname
            pac_password = company.l10n_pa_ws_token_fname
            if not pac_username and not pac_password and not company.l10n_pa_edi_pac_test_env:
                errors.append(_('No PAC credentials specified.'))
        else:
            errors.append(_('No PAC specified.'))

        return errors

    @api.model
    def _l10n_pa_edi_format_error_message(self, error_title, errors):
        bullet_list_msg = ''.join('<li>%s</li>' % msg for msg in errors)
        return '%s<ul>%s</ul>' % (error_title, bullet_list_msg)


    def _l10n_pa_edi_export_invoice_fe(self, invoice):

        # == CFDI values ==
        fe_values = self._l10n_pa_edi_get_invoice_cfdi_values(invoice)

        res = {
            'fe_values': fe_values,
        }

        return res

    # -------------------------------------------------------------------------
    # CFDI: PACs
    # -------------------------------------------------------------------------

    def _l10n_pa_edi_post_invoice_pac(self, invoice, exported):
        pac_name = invoice.company_id.l10n_pa_edi_pac

        credentials = getattr(self, '_l10n_pa_edi_get_%s_credentials' % pac_name)(invoice)
        if credentials.get('errors'):
            return {
                'error': self._l10n_pa_edi_format_error_message(_("PAC authentification error:"), credentials['errors']),
            }

        res = getattr(self, '_l10n_pa_edi_%s_sign_invoice' % pac_name)(invoice, credentials, exported['fe_values'])


        # Se imprime la respuesta a la solicitud del servicio
        if res['resultado'] == 'error':
            error_title = res['resultado']
            errors = res['mensaje']
            msg = error_title + errors
            invoice.message_post(body=_("Electronic Invoice with errors <b>%s</b>", msg=msg))
            raise ValidationError('Electronic Invoice with errors %s' % errors)


        if res['codigo'] == '200':
            invoice.l10n_pa_dgi_cufe = res['cufe']
            invoice.l10n_pa_dgi_qr_code = res['qr']
            invoice.l10n_pa_edi_status = 'process'
            invoice.message_post(body=_("Electronic Invoice created successfully"))

        return res


    # -------------------------------------------------------------------------
    # FE Generation: Invoices
    # -------------------------------------------------------------------------

    @api.model
    def _l10n_pa_edi_get_serie_and_folio(self, move):
        name_numbers = list(re.finditer('\d+', move.name))
        serie_number = name_numbers[0].group()
        folio_number = name_numbers[1].group()
        if len(serie_number+folio_number) < 10:
            folio_number = '0' * (10 - len(serie_number+folio_number)) + folio_number
        folio_number =  serie_number + folio_number
        logging.info(f"{'*'*20} folio_number {folio_number}")
        return {
            'folio_number': str(folio_number),
        }
        

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


    def _l10n_pa_edi_get_invoice_cfdi_values(self, invoice):
        ''' Doesn't check if the config is correct so you need to call _l10n_pa_edi_check_config first.
        :param invoice:
        :return:
        '''

        fe_date = datetime.combine(
            fields.Datetime.from_string(invoice.invoice_date),
            invoice.l10n_pa_edi_post_time.time(),
        ).strftime('%Y-%m-%dT%H:%M:%S-05:00')

        ####### Tipo documento  ###########
        if invoice.move_type == 'out_invoice':
            tipoDocumento = '01'
        elif invoice.move_type == 'out_refund':
            tipoDocumento = '06'

        tokenempresa = 'muokzsxikthh_tfhka'
        tokenPassword = 'den,XJM0Qa?:'

        ## products Dictionary
        listaItems = []
        totalPrecioNeto = totalITBMS = totalFactura = 0
        for product in invoice.invoice_line_ids:
            tax_rate = self.get_tax_rate(product)
            listaItemOTI = []
            isc = False
            itbms = False
            for tax in product.tax_ids:
                tax_type = tax.l10n_pa_edi_tax_type
                if not tax_type:
                    continue
                if tax_type.l10n_pa_edi_tax_type == 'oti' and tax_type.l10n_pa_edi_tax_code:
                    tax_rate = tax.amount
                    tax_item = {
                        "tasaOTI": "%.2f" % tax_type.l10n_pa_edi_tax_code,
                        "valorTasa": "%.2f" % tax_rate,
                    }
                    logging.info('tax_item: %s' % tax_item)
                    listaItemOTI.append(tax_item)
                if tax_type.l10n_pa_edi_tax_type == 'isc':
                    isc = tax
                if tax_type.l10n_pa_edi_tax_type == 'itbms':
                    itbms = tax
            item = {
                "descripcion": product.name,
                "cantidad": "%.2f" % product.quantity,
                "precioUnitario": "%.2f" % product.price_unit,
                "precioUnitarioDescuento": " ",
                "precioItem": "%.2f" % ( product.price_unit * product.quantity),
                "valorTotal": "%.2f" % (product.price_unit * product.quantity * (1 + tax_rate)),
                "codigoGTIN": "0",
                "cantGTINCom": "0.99",
                "codigoGTINInv": "0",
                "cantGTINComInv": "1.00"
            }
            if isc:
                item["tasaISC"] = "%.2f" % isc.l10n_pa_edi_tax_code
                item["valorISC"] = "%.2f" % isc.amount
            if itbms:
                item["tasaITBMS"] = itbms.l10n_pa_edi_tax_code 
                item["valorITBMS"] = "%.2f" % itbms.amount
            if listaItemOTI:
                item['listaItemOTI'] = listaItemOTI
            listaItems.append(item)
            totalPrecioNeto += product.price_unit * product.quantity
            totalITBMS += product.price_unit * product.quantity * tax_rate
            totalFactura += product.price_unit * product.quantity * (1 + tax_rate)
        product_list = dict(item=listaItems)

        ## Totales
        subtotal = []

        forma_pago = invoice.get_forma_pago(totalFactura)

        # ===============================
        # Validación DGI: crédito requiere listaPagoPlazo
        # ===============================
        for pago in invoice.dgi_payment_ids:
            if pago.forma_pago_fact == '01' and not pago.plazo_ids:
                raise ValidationError(
                    "La DGI requiere listaPagoPlazo cuando la forma de pago es Crédito (01)."
                )
        # Si Forma de Pago es Credito, arma lista de pagos
        # Construcción de lista de plazos desde datos reales
        lista_pago_plazo = []

        for pago in invoice.dgi_payment_ids:
            if pago.forma_pago_fact == '01':  # Solo si es Crédito
                for plazo in pago.plazo_ids:
                    plazo_item = {
                        "fechaVenceCuota": plazo.fecha_vence_cuota.strftime('%Y-%m-%dT00:00:00-05:00'),
                        "valorCuota": "%.2f" % plazo.valor_cuota,
                    }
                    if plazo.info_pago_cuota:
                        plazo_item["infoPagoCuota"] = plazo.info_pago_cuota
                    lista_pago_plazo.append(plazo_item)
        #if lista_pago_plazo:
        #    data["listaPagoPlazo"] = lista_pago_plazo
        # termina lista de pagos para Credito

        # Agregamos validacion antes de enviar por FE
        if invoice.forma_pago_fact == '01' and not lista_pago_plazo:
            raise UserError(
                "Forma de pago Crédito requiere al menos un plazo de pago."
            )

        totalesSubTotales = {
            "totalPrecioNeto": "%.2f" % (totalPrecioNeto),
            "totalITBMS": "%.2f" % (totalITBMS),
            "totalMontoGravado": "%.2f" % (totalITBMS),
            "totalDescuento": "",
            "totalAcarreoCobrado": "",
            "valorSeguroCobrado": "",
            "totalFactura": "%.2f" % (totalFactura),
            "totalValorRecibido": "%.2f" % (totalFactura),
            "vuelto": "0.00",
            "tiempoPago": "1",
            "nroItems": len(invoice.invoice_line_ids),
            "totalTodosItems": "%.2f" % (totalFactura),
            "listaFormaPago": {
                "formaPago": lista_forma_pago
            }
        }

        # Agregar listaPagoPlazo si hay plazos
        if lista_pago_plazo:
            totalesSubTotales["listaPagoPlazo"] = {
                "pagoPlazo": lista_pago_plazo
            }
        _logger.info("FEL | totalesSubTotales ANTES de enviar: %s", totalesSubTotales)

        fe_values = dict(
            tokenEmpresa = tokenempresa,
            tokenPassword = tokenPassword,
            documento=dict(
            codigoSucursalEmisor=invoice._l10n_pa_edi_get_codigo_sucursal(invoice),
            tipoSucursal="1",
            datosTransaccion=dict({
            "tipoEmision": "01",
            "tipoDocumento": tipoDocumento,
            "numeroDocumentoFiscal": self._l10n_pa_edi_get_serie_and_folio(invoice)['folio_number'],
            "puntoFacturacionFiscal": "001",
            "naturalezaOperacion": "01",
            "tipoOperacion": 1,
            "destinoOperacion": 1,
            "formatoCAFE": 1,
            "entregaCAFE": 1,
            "envioContenedor": 1,
            "procesoGeneracion": 1,
            "tipoVenta": 1,
            "fechaEmision": fe_date,
            "cliente": {
            "tipoClienteFE": invoice.partner_id.l10n_pa_edi_customer_type,
            "tipoContribuyente": invoice.partner_id.l10n_pa_edi_tipo_contribuyente,
            "numeroRUC": invoice.partner_id.vat,
            "digitoVerificadorRUC" : invoice.partner_id.l10n_pa_edi_dv,
            "pais": invoice.country_code,
            "correoElectronico1": invoice.partner_id.email,
            "razonSocial": invoice.partner_id.name,
            }
            }),
            listaItems = product_list,
            totalesSubTotales = totalesSubTotales, 
            )
            )
        
        if invoice.partner_id.l10n_pa_edi_customer_type in ('01', '03'):
            fe_values['documento']['datosTransaccion']['cliente']['direccion'] = invoice.partner_id.street
            # fe_values['documento']['datosTransaccion']['cliente']['codigoUbicacion'] = invoice.partner_id.l10n_pa_edi_codigoubicacion
            fe_values['documento']['datosTransaccion']['cliente']['codigoUbicacion'] = "8-8-7"
            fe_values['documento']['datosTransaccion']['cliente']['provincia'] = invoice.partner_id.state_id.name
            fe_values['documento']['datosTransaccion']['cliente']['distrito'] = invoice.partner_id.district_id.name
            fe_values['documento']['datosTransaccion']['cliente']['corregimiento'] = invoice.partner_id.jurisdiction_id.name
            fe_values['documento']['datosTransaccion']['cliente']['paisOtro'] = ''

        return fe_values


    def _l10n_pa_edi_get_thefactoryhka_credentials(self, move):
        return self._l10n_pa_edi_get_thefactoryhka_credentials_company(move.company_id)

    def _l10n_pa_edi_get_thefactoryhka_credentials_company(self, company):
        ''' Return the company credentials for PAC: thefactoryhka. Does not depend on a recordset
        '''
        if company.l10n_pa_edi_pac_test_env:
            return {
                'username': 'muokzsxikthh_tfhka',
                'password': 'den,XJM0Qa?:',
                'sign_url': 'http://demoemision.thefactoryhka.com.pa/ws/obj/v1.0/Service.svc?singleWsdl',
                # 'cancel_url': '',
            }
        else:
            if not company.l10n_pa_ws_user_fname or not company.l10n_pa_ws_token_fname:
                return {
                    'errors': [_("The username and/or Token are missing.")]
                }

            return {
                'username': company.l10n_pa_ws_user_fname,
                'password': company.l10n_pa_ws_token_fname,
                'sign_url': '',
                'cancel_url': '',
            }


    def _l10n_pa_edi_thefactoryhka_sign(self, move, credentials, cfdi):
        return self._l10n_pa_edi_thefactoryhka_sign_service(credentials, cfdi)

    def _l10n_pa_edi_thefactoryhka_sign_service(self, credentials, cfdi):
        ''' Send the CFDI XML document to the factory hka for signature. Does not depend on a recordset
        '''
        try:
            transport = Transport(timeout=20)
            client = Client(credentials['sign_url'], transport=transport)
            response = (client.service.Enviar(**cfdi))
        except Exception as e:
            return {
                'errors': [_("The The Factory HKA service failed to sign with the following error: %s", str(e))],
            }

        return response


    def _l10n_pa_edi_thefactoryhka_sign_invoice(self, invoice, credentials, fe):
        return self._l10n_pa_edi_thefactoryhka_sign(invoice, credentials, fe)

    def _l10n_pa_edi_thefactoryhka_cancel_invoice(self, invoice, credentials, fe):
        return self._l10n_pa_edi_thefactoryhka_cancel(invoice, credentials, fe)

