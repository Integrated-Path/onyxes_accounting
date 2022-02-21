# -*- coding: utf-8 -*-

from itertools import groupby
from re import L

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_is_zero


class SaleOrder(models.Model):
    _inherit = "sale.order"

    NEW_INVOICE_STATUS = [
        ('upselling', 'Upselling Opportunity'),
        ('invoiced', 'Fully Invoiced'),
        ('to invoice', 'To Invoice'),
        ('no', 'Nothing to Invoice')
    ]
    invoicing_policy_id = fields.Many2one("account.invoicing.policy", readonly=True, states={'draft': [('readonly', False)] } )
    invoices_created_by_policy = fields.One2many(
        'account.move', 'policy_sale_order_id')

    new_invoice_status = fields.Selection(NEW_INVOICE_STATUS, 
        string='Invoice Status', compute='_get_new_invoice_status', readonly=True, copy=False, store=True)

    @api.onchange("invoicing_policy_id")
    def _handle_invoicing_policy_id_change(self):
        if self.invoicing_policy_id:
            self.payment_term_id = False
        else:
            pass
        
     def _get_invoice_grouping_keys(self):
        return ['company_id', 'partner_id', 'currency_id']

    def _create_invoices(self, grouped=False, final=False):
        """
        Create the invoice associated to the SO.
        :param grouped: if True, invoices are grouped by SO id. If False, invoices are grouped by
                        (partner_invoice_id, currency)
        :param final: if True, refunds will be generated if necessary
        :returns: list of created invoices
        """
        if not self.env['account.move'].check_access_rights('create', False):
            try:
                self.check_access_rights('write')
                self.check_access_rule('write')
            except AccessError:
                return self.env['account.move']

        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')

        # 1) Create invoices.
        invoice_vals_list = []
        for order in self:
            pending_section = None

            # Invoice values.
            invoice_vals = order._prepare_invoice()
            invoice_vals['ref'] = f"{order.name} DAC"

            # Invoice line values (keep only necessary sections).
            for line in order.order_line:
                policy_discount = False
                if order.invoicing_policy_id:
                    policy_discount = 100.00 - order.invoicing_policy_id.dac

                if line.display_type == 'line_section':
                    pending_section = line
                    continue
                if float_is_zero(line.qty_to_invoice, precision_digits=precision):
                    continue
                if line.qty_to_invoice > 0 or (line.qty_to_invoice < 0 and final):
                    if pending_section:
                        if policy_discount:
                            invoice_vals['invoice_line_ids'].append(
                                (0, 0, pending_section._prepare_invoice_line(policy_discount=policy_discount)))
                        else:
                            invoice_vals['invoice_line_ids'].append((0, 0, pending_section._prepare_invoice_line()))
                        pending_section = None
                    if policy_discount:
                        invoice_vals['invoice_line_ids'].append(
                            (0, 0, line._prepare_invoice_line(policy_discount=policy_discount)))
                    else:
                        invoice_vals['invoice_line_ids'].append((0, 0, line._prepare_invoice_line()))

            if not invoice_vals['invoice_line_ids']:
                raise UserError(_('There is no invoiceable line. If a product has a Delivered quantities invoicing policy, please make sure that a quantity has been delivered.'))

            invoice_vals_list.append(invoice_vals)

        if not invoice_vals_list:
            raise UserError(_(
                'There is no invoiceable line. If a product has a Delivered quantities invoicing policy, please make sure that a quantity has been delivered.'))

        # 2) Manage 'grouped' parameter: group by (partner_id, currency_id).
        if not grouped:
            new_invoice_vals_list = []
            invoice_grouping_keys = self._get_invoice_grouping_keys()
            for grouping_keys, invoices in groupby(invoice_vals_list, key=lambda x: [x.get(grouping_key) for grouping_key in invoice_grouping_keys]):
                origins = set()
                payment_refs = set()
                refs = set()
                ref_invoice_vals = None
                for invoice_vals in invoices:
                    if not ref_invoice_vals:
                        ref_invoice_vals = invoice_vals
                    else:
                        ref_invoice_vals['invoice_line_ids'] += invoice_vals['invoice_line_ids']
                    origins.add(invoice_vals['invoice_origin'])
                    payment_refs.add(invoice_vals['invoice_payment_ref'])
                    refs.add(invoice_vals['ref'])
                ref_invoice_vals.update({
                    'ref': ', '.join(refs)[:2000],
                    'invoice_origin': ', '.join(origins),
                    'invoice_payment_ref': len(payment_refs) == 1 and payment_refs.pop() or False,
                })
                new_invoice_vals_list.append(ref_invoice_vals)
            invoice_vals_list = new_invoice_vals_list

        # 3) Create invoices.
        # Manage the creation of invoices in sudo because a salesperson must be able to generate an invoice from a
        # sale order without "billing" access rights. However, he should not be able to create an invoice from scratch.
        moves = self.env['account.move'].sudo().with_context(default_type='out_invoice').create(invoice_vals_list)
        # 4) Some moves might actually be refunds: convert them if the total amount is negative
        # We do this after the moves have been created since we need taxes, etc. to know if the total
        # is actually negative or not
        if final:
            moves.sudo().filtered(lambda m: m.amount_total < 0).action_switch_invoice_into_refund_credit_note()
        for move in moves:
            move.message_post_with_view('mail.message_origin_link',
                values={'self': move, 'origin': move.line_ids.mapped('sale_line_ids.order_id')},
                subtype_id=self.env.ref('mail.mt_note').id
            )
        # Check if there is policy selected then this is a policy invoice DAC and create other policy invoices
        if order.invoicing_policy_id:
            order.invoices_created_by_policy += moves
            moves.invoicing_policy_id = order.invoicing_policy_id
            moves.policy_type = 'dac'

            if order.invoicing_policy_id.pac > 0:
                for order in self:
                    pac_invoice_line_vals = []
                    for line in order.order_line:
                        pac_policy_discount = 100.00 - order.invoicing_policy_id.pac
                        pac_invoice_line_vals.append(
                            (0, 0, line._prepare_invoice_line_policy(policy_discount=pac_policy_discount)))
                pac_values = [(5, 0, 0)]
                pac_values += pac_invoice_line_vals
                pac_invoice = moves.copy()
                pac_invoice.write({'ref': f'{order.name} PAC', 'invoice_line_ids': pac_values})
                order.invoices_created_by_policy += pac_invoice
                pac_invoice.invoicing_policy_id = order.invoicing_policy_id
                pac_invoice.policy_type = 'pac'

            if order.invoicing_policy_id.fac > 0:
                for order in self:
                    fac_invoice_line_vals = []
                    for line in order.order_line:
                        fac_policy_discount = 100.00 - order.invoicing_policy_id.fac
                        fac_invoice_line_vals.append(
                            (0, 0, line._prepare_invoice_line_policy(policy_discount=fac_policy_discount)))
                fac_values = [(5, 0, 0)]
                fac_values += fac_invoice_line_vals
                fac_invoice = moves.copy()
                fac_invoice.write({'ref': f'{order.name} FAC', 'invoice_line_ids': fac_values})
                order.invoices_created_by_policy += fac_invoice
                fac_invoice.invoicing_policy_id = order.invoicing_policy_id
                fac_invoice.policy_type = 'fac'

        return moves
    
    @api.constrains('invoice_status', 'invoicing_policy_id')
    def _get_new_invoice_status(self):
        for record in self:
            if record.invoicing_policy_id and record.invoices_created_by_policy:
                record.new_invoice_status = 'invoiced'
            else:
                record.new_invoice_status = record.invoice_status


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'
    

    def _prepare_invoice_line(self, policy_discount=False):
        """
        Prepare the dict of values to create the new invoice line for a sales order line.

        :param qty: float quantity to invoice
        """
        self.ensure_one()
        res = {
            'display_type': self.display_type,
            'sequence': self.sequence,
            'name': self.name,
            'product_id': self.product_id.id,
            'product_uom_id': self.product_uom.id,
            'quantity': self.qty_to_invoice,
            'discount': policy_discount if policy_discount else self.discount,
            'price_unit': self.price_unit,
            'tax_ids': [(6, 0, self.tax_id.ids)],
            'analytic_account_id': self.order_id.analytic_account_id.id,
            'analytic_tag_ids': [(6, 0, self.analytic_tag_ids.ids)],
            'sale_line_ids': [(4, self.id)],
        }
        if self.display_type:
            res['account_id'] = False
        return res

    def _prepare_invoice_line_policy(self, policy_discount=False):
        """
        Prepare the dict of values to create the new invoice line for a sales order line.

        :param qty: float quantity to invoice
        """
        self.ensure_one()
        res = {
            'display_type': self.display_type,
            'sequence': self.sequence,
            'name': self.name,
            'product_id': self.product_id.id,
            'product_uom_id': self.product_uom.id,
            'quantity': self.product_uom_qty,
            'discount': policy_discount if policy_discount else self.discount,
            'price_unit': self.price_unit,
            'tax_ids': [(6, 0, self.tax_id.ids)],
            'analytic_account_id': self.order_id.analytic_account_id.id,
            'analytic_tag_ids': [(6, 0, self.analytic_tag_ids.ids)],
            'sale_line_ids': [(4, self.id)],
        }
        if self.display_type:
            res['account_id'] = False
        return res
