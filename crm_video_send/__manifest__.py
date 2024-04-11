
{
    'name': "CRM Video Sending",
    'description': """It allows send mass personalized videos.""",
    'version': "17.0.1.0",
    'depends': ['base', 'account', 'crm'],
    'author':"Cesar Linares Broche",
    'category': 'Sales Management',
    'installable': True,
    'application': True,
    'license': 'OPL-1',
    'data': [
            'security/ir.model.access.csv',
            'views/file_upload_form.xml',
            'views/main_view.xml',
            'views/video_act_window.xml',
        ],
    'external_dependencies': {
        'python': ['openai', 'requests', 'unidecode', 'googlesearch-python', 'openpyxl'],
    }
}
