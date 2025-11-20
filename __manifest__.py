# -*- coding: utf-8 -*-
{
    'name': "Maya | Students",
    'version': '17.0.1.0',

    'summary': """
         Extensión de Maya | Core para la gestión de estudiantes""",

    'description': """
        Permite:
         - el control de las anulaciones de matrícula de oficio por inactividad
    """,

    'author': "Alfredo Oltra",
    'website': "https://portal.edu.gva.es/ceedcv/",
    'maintainer': 'Alfredo Oltra <alfredo.ptcf@gmail.com>',

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/14.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Productivity',

    'license': 'AGPL-3',
    'price': 0,

    # any module necessary for this one to work correctly
    'depends': ['base', 'mail', 'maya_core'],
    
    'assets': {
        'web.assets_backend': [
            'maya_core/static/src/js/tab_switcher.js',
        ],
    },
    # always loaded
    'data': [
        # seguridad
        'security/ir.model.access.csv',
        # vistas
        'views/views.xml',
        'views/mail_templates/mail_risk1.xml',
        'views/mail_templates/mail_risk2.xml',
        'views/mail_templates/notification_cancellation_teacher_task.xml',
        #'views/assets.xml',
        # datos de modelos
        'data/registered_notification_module.xml',
        'data/registered_cron_jobs.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
    'installable': True,
    'application': False,
}
