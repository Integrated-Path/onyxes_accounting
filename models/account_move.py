# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AccountMove(models.Model):
    _inherit = "account.move"

    POLICY_TYPE = [
        ('dac', 'DAC'),
        ('pac', 'PAC'),
        ('fac', 'FAC'),
    ]

    policy_sale_order_id = fields.Many2one('sale.order', string='Policy Sale Order')
    invoicing_policy_id = fields.Many2one("account.invoicing.policy", readonly=True)
    policy_type = fields.Selection(POLICY_TYPE, readonly=True)
