
import json
import base64
import logging
from odoo import http
from odoo.http import request
from odoo.exceptions import UserError
from werkzeug.wrappers import Response
_logger = logging.getLogger(__name__)

class DownloadInvoiceFel(http.Controller):

    @http.route('/download_invoice_pdf', auth='user', methods=['GET'], csrf=True)
    def download_invoice_pdf(self, **kw):
        invoice_id = kw.get('invoice_id', False)
        if not invoice_id:
            raise UserError('Invoice ID not found')
        invoice = request.env['account.move'].browse(int(invoice_id))
        if not invoice:
            raise UserError('Invoice not found')
        if not invoice.l10n_pa_invoice_pdf:
            invoice.dowload_l10n_pa_edit_pdf()
        pdf = invoice.l10n_pa_invoice_pdf
        if not pdf:
            raise UserError('PDF not found')
        pdf_base64 = base64.b64decode(pdf)
        file_name = f'Factura_{invoice.name or ""}.pdf'
        return request.make_response(pdf_base64, [('Content-Type', 'application/pdf'), ('Content-Disposition', f'attachment; filename={file_name}')])

        
    @http.route('/download_invoice_xml', type='http', auth='user', methods=['GET'], csrf=True)
    def download_invoice_xml(self, **kw):
        invoice_id = kw.get('invoice_id', False)
        if not invoice_id:
            raise UserError('Invoice ID not found')
        invoice = request.env['account.move'].browse(int(invoice_id))
        if not invoice:
            raise UserError('Invoice not found')
        if not invoice.l10n_pa_invoice_xml:
            invoice.dowload_l10n_pa_edit_xml()
        xml = invoice.l10n_pa_invoice_xml
        if not xml:
            raise UserError('XML not found')
        xml_base64 = base64.b64decode(xml)
        file_name = f'Factura_{invoice.name or ""}.xml'
        return request.make_response(xml_base64, [('Content-Type', 'application/xml'), ('Content-Disposition', f'attachment; filename={file_name}')])
        