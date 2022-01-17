# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError 


class AccountInvoicingPolicy(models.Model):
    _name = "account.invoicing.policy"
    _description = "Invoicing Policy"
    _order = "id"

    name = fields.Char(string='Policy Name', compute="_compute_policy_name")
    dac = fields.Float(string='DAC')
    pac = fields.Float(string='PAC')
    fac = fields.Float(string='FAC')

    @api.depends('dac', 'pac', 'fac')
    def _compute_policy_name(self):
        for record in self:
            record.name = f"{record.dac}, {record.pac} By {record.fac}"

    @api.constrains('dac', 'pac', 'fac')
    def check_100(self):
        for record in self:
            if record.dac + record.pac + record.fac != 100:
                raise UserError("DAC + PAC + FAC should be equal to 100%")
