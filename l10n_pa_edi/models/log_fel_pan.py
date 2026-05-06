from odoo import models, fields, api, _
from odoo.exceptions import UserError

class LogFelPan(models.Model):
    _name = "log.fel.pan"
    _description = "Log FEL PAN"
    _default_order = 'date_hora desc'
    
    name = fields.Char(string="Nombre", required=True)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Hecho')
    ], string="Estado", required=True, default="draft")
    date_hora = fields.Datetime(string="Fecha y Hora", required=True, default=fields.Datetime.now)
    message = fields.Text(string="Mensaje")
    type = fields.Selection([
        ('error', 'Error'),
        ('success', 'Éxito'),
        ('duplicate', 'Duplicado'),
        ('warning', 'Advertencia'),
        ('error_file', 'Error de descarga de archivo'),
    ], string="Tipo", required=True, default="error")
    no_invoiced_id = fields.Char(string="ID de Factura", help="ID de la factura para evitar conflictos de relacionamiento")
    computer_invoice_id = fields.Many2one("account.move", string="Factura", compute="_compute_invoice_id")
    no_pos_order_id = fields.Char(string="ID de Orden de Punto de Venta", help="ID de la orden de punto de venta para evitar conflictos de relacionamiento") 
    computer_pos_order_id = fields.Many2one("pos.order", string="Orden de Punto de Venta", compute="_compute_pos_order_id")
    no_pos_order_ref = fields.Char(string="Referencia de Orden de Punto de Venta", help="Referencia de la orden de punto de venta para evitar conflictos de relacionamiento")
    invoice_origin = fields.Char(string="Origen de Factura", help="Origen de la factura ")

    company_id = fields.Many2one("res.company", string="Compañía", default=lambda self: self.env.company.id)
    json_send = fields.Text(string="Enviado")
    json_received = fields.Text(string="Recibido")
    nodocumentofiscal = fields.Char(string="Número de Documento Fiscal")
    user_id = fields.Many2one("res.users", string="Usuario", default=lambda self: self.env.user.id)

    @api.depends("no_pos_order_id")
    def _compute_pos_order_id(self):
        for record in self:
            pos_order = self.env["pos.order"].search([("id", "=", record.no_pos_order_id)], limit=1)
            if pos_order:
                record.computer_pos_order_id = pos_order
            else:
                record.computer_pos_order_id = False

    @api.depends("no_invoiced_id")
    def _compute_invoice_id(self):
        for record in self:
            invoice = self.env["account.move"].search([("id", "=", record.no_invoiced_id)], limit=1)
            if invoice:
                record.computer_invoice_id = invoice
            else:
                record.computer_invoice_id = False

