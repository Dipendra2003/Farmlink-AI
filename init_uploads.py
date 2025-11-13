import os

def init_upload_directories():
    """Initialize all required upload directories"""
    directories = [
        os.path.join('static', 'uploads'),
        os.path.join('static', 'uploads', 'crops'),
        os.path.join('static', 'uploads', 'invoices'),
        os.path.join('static', 'uploads', 'kyc'),
        os.path.join('static', 'uploads', 'pest_analysis'),
        os.path.join('static', 'uploads', 'profiles'),
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
