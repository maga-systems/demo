from odoo import fields, models, api
from odoo.api import ondelete
from odoo.exceptions import ValidationError


# Modelo tecnico solo fiscal, no contable

class AccountMoveDgiPayment(models.Model):
    _name = 'account.move.dgi.payment'
    _description = 'Forma de Pago DGI - Panamá'

    move_id = fields.Many2one(
        'account.move',
        required=True,
        ondelete='cascade'
    )
    forma_pago_fact = fields.Selection([
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
        required=True)
    desc_forma_pago = fields.Char(
        string='Descripción (solo para Otros)',
        size=100
    )
    valor_cuota_pagada = fields.Monetary(
        string='Valor cuota pagada',
        required=True
    )
    currency_id = fields.Many2one(
        related='move_id.currency_id',
        store=True
    )
    plazo_ids = fields.One2many(
        'account.move.dgi.payment.plazo',
        'payment_id',
        string='Plazos'
    )

class AccountMoveDgiPaymentPlazo(models.Model):
    _name = 'account.move.dgi.payment.plazo'
    _description = 'Plazos de pago DGI Panamá'
    move_id = fields.Many2one(
        'account.move',
        required=True,
        ondelete='cascade',
        index=True,
    )
    currency_id = fields.Many2one(
        related='move_id.currency_id',
        store=True
    )
    payment_id = fields.Many2one(
        'account.move.dgi.payment',
        required=False,
        ondelete='cascade'
    )
    fecha_vence_cuota = fields.Date(
        string='Fecha vencimiento cuota',
    )
    valor_cuota = fields.Monetary(
        string='Valor de la cuota',
    )
    info_pago_cuota = fields.Char(
        string='Información adicional',
        size=1000
    )

    # 🔥 CAMPO PUENTE (para vistas legacy)
    fecha_pago = fields.Date(
        related="fecha_vence_cuota",
        store=True,
        readonly=True
    )

    monto_pago = fields.Monetary(
        string='Monto del pago',
        store=True,
        readonly=True
    )

# Métodos dentro de AccountMoveDgiPaymentPlazo
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('payment_id') and vals.get('move_id'):
                move = self.env['account.move'].browse(vals['move_id'])

                credit_payment = move.dgi_payment_ids.filtered(
                    lambda p: p.forma_pago_fact == '01'
                )[:1]

                if credit_payment:
                    vals['payment_id'] = credit_payment.id
                # Si no hay pago de crédito, se creará sin payment_id

        return super().create(vals_list)

    @api.onchange('payment_id')
    def _onchange_payment_id(self):
        for rec in self:
            if rec.payment_id:
                rec.move_id = rec.payment_id.move_id

    @api.constrains('fecha_vence_cuota', 'move_id')
    def _check_fecha_vencimiento(self):
        for plazo in self:
            if plazo.fecha_vence_cuota and plazo.move_id and plazo.move_id.invoice_date:
                if plazo.fecha_vence_cuota <= plazo.move_id.invoice_date:
                    raise ValidationError(
                        f"La fecha de vencimiento ({plazo.fecha_vence_cuota}) debe ser posterior "
                        f"a la fecha de emisión de la factura ({plazo.move_id.invoice_date})."
                    )

    @api.constrains('info_pago_cuota')
    def _check_info_pago_cuota_length(self):
        for plazo in self:
            if plazo.info_pago_cuota:
                length = len(plazo.info_pago_cuota.strip())
                if length > 0 and length < 15:
                    raise ValidationError(
                        "La información del pago debe tener al menos 15 caracteres. "
                        f"Actual: {length} caracteres."
                    )
                if length > 1000:
                    raise ValidationError(
                        "La información del pago no puede exceder 1000 caracteres. "
                        f"Actual: {length} caracteres."
                    )