# -*- coding: utf-8 -*-
# © 2013-2016 Akretion (Alexis de Lattre <alexis.delattre@akretion.com>)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openerp import models, fields, api, _
import openerp.addons.decimal_precision as dp
from openerp.exceptions import Warning as UserError
from openerp.tools import float_is_zero


class AccountCutoff(models.Model):
    _inherit = 'account.cutoff'

    @api.model
    def _inherit_default_cutoff_account_id(self):
        account_id = super(AccountCutoff, self).\
            _inherit_default_cutoff_account_id()
        type = self._context.get('type')
        company = self.env.user.company_id
        if type == 'accrued_expense':
            account_id = company.default_accrued_expense_account_id.id or False
        elif type == 'accrued_revenue':
            account_id = company.default_accrued_revenue_account_id.id or False
        return account_id

    @api.multi
    def generate_accrual_lines(self):
        """This method is inherited by the modules that depend on this one"""
        self.ensure_one()
        self.line_ids.unlink()
        return True

    def _get_default_journal(self, cr, uid, context=None):
        journal_id = super(AccountCutoff, self)\
            ._get_default_journal(cr, uid, context=context)
        cur_user = self.pool['res.users'].browse(cr, uid, uid, context=context)
        cutoff_type = context.get('type', False)
        default_journal_id = cur_user.company_id\
            .default_cutoff_journal_id.id or False
        if cutoff_type == 'accrued_expense':
            journal_id =\
                cur_user.company_id.default_accrual_expense_journal_id.id or\
                default_journal_id
        elif cutoff_type == 'accrued_revenue':
            journal_id = \
                cur_user.company_id.default_accrual_revenue_journal_id.id or\
                default_journal_id
        return journal_id

    @api.multi
    def _prepare_tax_lines(self, tax_compute_all_res, currency):
        res = []
        ato = self.env['account.tax']
        company_currency = self.company_id.currency_id
        cur_rprec = company_currency.rounding
        for tax_line in tax_compute_all_res['taxes']:
            tax = ato.browse(tax_line['id'])
            if float_is_zero(tax_line['amount'], precision_rounding=cur_rprec):
                continue
            if self.type == 'accrued_expense':
                tax_accrual_account_id = tax.account_accrued_expense_id.id
                tax_account_field_label = _('Accrued Expense Tax Account')
            elif self.type == 'accrued_revenue':
                tax_accrual_account_id = tax.account_accrued_revenue_id.id
                tax_account_field_label = _('Accrued Revenue Tax Account')
            if not tax_accrual_account_id:
                raise UserError(_(
                    "Missing '%s' on tax '%s'.") % (
                        tax_account_field_label, tax.display_name))
            tax_amount = currency.round(tax_line['amount'])
            tax_accrual_amount = currency.with_context(
                date=self.cutoff_date).compute(tax_amount, company_currency)
            res.append((0, 0, {
                'tax_id': tax_line['id'],
                'base': tax_line['price_unit'],  # in currency
                'amount': tax_amount,  # in currency
                'sequence': tax_line['sequence'],
                'cutoff_account_id': tax_accrual_account_id,
                'cutoff_amount': tax_accrual_amount,  # in company currency
                }))
        return res


class AccountCutoffLine(models.Model):
    _inherit = 'account.cutoff.line'

    quantity = fields.Float(
        string='Quantity', digits=dp.get_precision('Product Unit of Measure'),
        readonly=True)
    price_unit = fields.Float(
        string='Unit Price',
        digits=dp.get_precision('Product Price'), readonly=True,
        help="Price per unit without taxes (discount included)")
    price_source = fields.Selection([
        ('sale', 'Sale Order'),
        ('purchase', 'Purchase Order'),
        ('invoice', 'Invoice'),
        ], string='Price Source', readonly=True)
