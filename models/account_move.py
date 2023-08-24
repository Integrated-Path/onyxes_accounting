# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AccountMove(models.Model):
    _inherit = "account.move"

    POLICY_TYPE = [
        ('dac', 'DAC'),
        ('pac', 'PAC'),
        ('fac', 'FAC'),
    ]
    policy_sale_order_id = fields.Many2one('sale.order', string='Sale Order')
    invoicing_policy_id = fields.Many2one("account.invoicing.policy", readonly=True)
    policy_type = fields.Selection(POLICY_TYPE, readonly=True)

    @api.constrains('project_id')
    def _get_analytic_account(self):
        for record in self:
            if record.project_id:
                for line in record.invoice_line_ids:
                    line.analytic_account_id = record.project_id.analytic_account_id

    # OVERIDE
    def _stock_account_prepare_anglo_saxon_out_lines_vals(self):
        stock_account_move_lines = super(AccountMove, self)._stock_account_prepare_anglo_saxon_out_lines_vals()
        for line in stock_account_move_lines:
            move_id = self.env['account.move'].browse(line['move_id'])
            if move_id.invoicing_policy_id:
                product_id = self.env['product.product'].browse(line['product_id'])
                charged_precent = move_id.invoicing_policy_id[move_id.policy_type]
                cost_to_charge = (0.01 * charged_precent) * product_id.standard_price
                if line.get('debit', 0) > 0:
                    line['debit'] = cost_to_charge
                if line.get('credit', 0) > 0:
                    line['credit'] = cost_to_charge
        return stock_account_move_lines
