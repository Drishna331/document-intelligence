import unittest
from backend.app.schemas.extraction import ExtractedData, Period, LineItem, WireReconciliation
from backend.app.services.financial_validation_service import FinancialValidationService
from .helpers import v


class FinancialTests(unittest.TestCase):
    def setUp(self):
        self.service = FinancialValidationService('0.05')

    def test_invoice(self):
        data = ExtractedData(fields={k: v(n) for k, n in {'subtotal': 100, 'tax_amount': 10, 'total_amount': 110,
            'cash_paid': 120, 'change': 10}.items()}, line_items=[LineItem(fields={'quantity': v(2), 'unit_price': v(50), 'line_total': v(100)}, amount_basis='net')],
            line_items_complete=True, tax_basis='exclusive')
        result = self.service.validate('invoice', data)
        self.assertEqual([c.status for c in result.checks], ['PASS'] * 4)

    def test_missing_is_not_applicable(self):
        result = self.service.validate('invoice', ExtractedData())
        self.assertEqual(result.overall_status, 'NOT_APPLICABLE')
        for check in result.checks:
            self.assertIsNone(check.calculated_value)

    def test_inclusive_tax_not_double_counted(self):
        data = ExtractedData(fields={'subtotal': v(110), 'tax_amount': v(10), 'total_amount': v(110)}, tax_basis='inclusive')
        check = self.service.validate('invoice', data).checks[-2]
        self.assertEqual(check.status, 'NOT_APPLICABLE')

    def test_invoice_rounding_and_discount(self):
        data = ExtractedData(fields={k: v(n) for k, n in {'subtotal': 100, 'tax_amount': 10, 'discount': 5,
            'rounding_adjustment': '-0.01', 'total_amount': '104.99'}.items()}, tax_basis='exclusive')
        self.assertEqual(self.service.validate('invoice', data).checks[-2].status, 'PASS')

    def test_incomplete_lines_not_summed(self):
        data = ExtractedData(fields={'subtotal': v(100)}, line_items=[LineItem(fields={'line_total': v(50)}, amount_basis='net')])
        self.assertEqual(self.service.validate('invoice', data).checks[-3].status, 'NOT_APPLICABLE')

    def test_balance_sheet_independent_periods(self):
        data = ExtractedData(periods=[Period(period='2025', fields={'total_assets': v(100), 'total_capital_and_liabilities': v(100)}),
                                     Period(period='2024', fields={'total_assets': v(95), 'total_capital_and_liabilities': v(90)})])
        result = self.service.validate('balance_sheet', data)
        checks = [c for c in result.checks if c.name == 'balance_sheet_equation']
        self.assertEqual([c.status for c in checks], ['PASS', 'FAIL'])
        self.assertEqual(checks[1].variance, '-5')

    def test_balance_sheet_components(self):
        data = ExtractedData(periods=[Period(period='2025', fields={'total_assets': v(100), 'cash': v(40), 'loans': v(60)})],
            reconciliations=[WireReconciliation(period='2025', total_key='total_assets', component_keys=['cash', 'loans'], complete=True)])
        checks = self.service.validate('balance_sheet', data).checks
        self.assertEqual(checks[1].status, 'PASS')

    def test_profit_and_loss(self):
        values = {'interest_earned': 100, 'other_income': 20, 'total_income': 120, 'interest_expended': 50,
            'operating_expenses': 20, 'provisions_and_contingencies': 10, 'total_expenditure': 80,
            'profit_before_minority_interest': 40, 'minority_interest': 5, 'net_profit': 35,
            'brought_forward_profit': 10, 'total_available_for_appropriation': 45}
        data = ExtractedData(periods=[Period(period='2025', fields={k: v(n) for k, n in values.items()})])
        self.assertEqual([c.status for c in self.service.validate('profit_and_loss', data).checks[:5]], ['PASS'] * 5)

    def test_cash_flow_negative_values_and_periods(self):
        values = {'operating_cash_flow': 100, 'investing_cash_flow': -50, 'financing_cash_flow': -20,
                  'fx_adjustment': -2, 'net_change_in_cash': 28, 'opening_cash': 200, 'closing_cash': 228}
        data = ExtractedData(periods=[Period(period='2025', fields={k: v(n) for k, n in values.items()})])
        self.assertEqual([c.status for c in self.service.validate('cash_flow_statement', data).checks], ['PASS', 'PASS'])

    def test_missing_fx_is_not_zero(self):
        data = ExtractedData(periods=[Period(period='2025', fields={'operating_cash_flow': v(10), 'investing_cash_flow': v(-2), 'financing_cash_flow': v(-1), 'net_change_in_cash': v(7)})])
        self.assertEqual(self.service.validate('cash_flow_statement', data).checks[0].status, 'NOT_APPLICABLE')

    def test_tolerance(self):
        for total, expected in [('100.04', 'PASS'), ('100.06', 'FAIL')]:
            data = ExtractedData(periods=[Period(period='2025', fields={'total_assets': v(total), 'total_capital_and_liabilities': v(100)})])
            self.assertEqual(self.service.validate('balance_sheet', data).checks[0].status, expected)
