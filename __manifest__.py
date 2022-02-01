# -*- coding: utf-8 -*-
{
    'name': "Onyxes Accounting",

    'summary': """
        Accounting Customization for Onyxes""",

    'author': "Integrated Path",
    'website': "https://www.int-path.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/13.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Accounting',
    'version': '13.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'account_accountant', 'sale_management'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/views.xml',
        'views/account_invoicing_policy_views.xml',
        'views/sale_order_views.xml',
        'views/account_move_views.xml',
    ],
}
