from odoo import models, fields, api

class SaleAdvancePaymentInv(models.TransientModel):
	_inherit = "sale.advance.payment.inv"

	advance_payment_method = fields.Selection(default="delivered", readonly=True)