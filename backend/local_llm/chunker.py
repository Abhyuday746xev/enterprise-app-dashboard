# ==========================================
# Enterprise Data Chunker
# ==========================================


# ==========================================
# Application Chunk
# ==========================================

def application_chunk(app):

    return f"""
Application Name: {app.get('display_name')}

Publisher: {app.get('publisher')}

Platform: {app.get('app_type')}

Publishing State: {app.get('publishing_state')}

Version: {app.get('display_version')}

Developer: {app.get('developer')}

Owner: {app.get('owner')}

File Name: {app.get('file_name')}

Size: {app.get('size')}

Notes: {app.get('notes')}
""".strip()


# ==========================================
# Device Chunk
# ==========================================

def device_chunk(device):

    return f"""
Device Name: {device.get('device_name')}

User: {device.get('user_name')}

Operating System: {device.get('operating_system')}

OS Version: {device.get('os_version')}

Manufacturer: {device.get('manufacturer')}

Model: {device.get('model')}

Compliance State: {device.get('compliance_state')}
""".strip()


# ==========================================
# User Chunk
# ==========================================

def user_chunk(user):

    return f"""
User Name: {user.get('display_name')}

Email: {user.get('mail')}

Department: {user.get('department')}

Office: {user.get('office_location')}

Mobile Phone: {user.get('mobile_phone')}

Account Enabled: {user.get('account_enabled')}
""".strip()