FORMULA_EXPRESSIONS={
    'revenue_yoy':'(R_t - R_t-1) / R_t-1',
    'gross_profit':'revenue - cost_of_sales',
    'gross_margin':'(revenue - cost_of_sales) / revenue',
    'inventory_change':'inventory_t - inventory_t-1',
    'accounts_receivable_change':'accounts_receivable_t - accounts_receivable_t-1',
    'parent_adjusted_profit_gap':'parent_net_profit - parent_adjusted_net_profit',
    'baseline-gross-profit':'GP0 = R0 - C0',
    'baseline-gross-margin':'GM0 = GP0 / R0',
    'scenario-delta-cost':'delta_C = C0 * s * x',
    'scenario-revenue':'R1 = R0 + k * delta_C',
    'scenario-cost-of-sales':'C1 = C0 + delta_C',
    'scenario-gross-profit':'GP1 = R1 - C1',
    'scenario-gross-margin':'GM1 = GP1 / R1',
    'scenario-delta-gross-profit':'delta_GP = (k - 1) * delta_C',
    'scenario-delta-gross-margin-pp':'delta_GM_pp = 100 * (GM1 - GM0)',
}


def formula_expression(formula_id):
    return FORMULA_EXPRESSIONS.get(formula_id,'未登记展示表达式；以 formula_id/version 和输入快照为准')
