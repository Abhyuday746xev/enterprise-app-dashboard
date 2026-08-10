# ==========================================
# Enterprise RAG Ingestion Pipeline
# ==========================================

from database import get_connection

from local_llm.chunker import (
    application_chunk,
    device_chunk,
    user_chunk
)

from local_llm.embeddings import create_embedding

from local_llm.vector_store import (
    add_document,
    clear_collection
)


# ==========================================
# Applications
# ==========================================

def ingest_applications(cursor):

    cursor.execute("SELECT * FROM mobile_apps")

    apps = cursor.fetchall()

    print(f"\n[1/3] Ingesting {len(apps)} Applications...")

    success = 0
    failed = 0

    for app in apps:

        try:

            chunk = application_chunk(app)

            embedding = create_embedding(chunk)

            add_document(

                document_id=f"app_{app['id']}",

                document=chunk,

                embedding=embedding,

                metadata={

                    "type": "application",

                    "name": app.get("display_name") or "Unknown",

                    "publisher": app.get("publisher") or "Unknown",

                    "platform": app.get("app_type") or "Unknown",

                    "state": app.get("publishing_state") or "Unknown"

                }

            )

            success += 1

            print(f"✓ {app.get('display_name')}")

        except Exception as e:

            failed += 1

            print(f"✗ {app.get('display_name')}")
            print(e)

    print(f"Applications Indexed : {success}")
    print(f"Applications Failed  : {failed}")

    return success


# ==========================================
# Devices
# ==========================================

def ingest_devices(cursor):

    cursor.execute("SELECT * FROM managed_devices")

    devices = cursor.fetchall()

    print(f"\n[2/3] Ingesting {len(devices)} Devices...")

    success = 0
    failed = 0

    for device in devices:

        try:

            chunk = device_chunk(device)

            embedding = create_embedding(chunk)

            add_document(

                document_id=f"device_{device['id']}",

                document=chunk,

                embedding=embedding,

                metadata={

                    "type": "device",

                    "name": device.get("device_name") or "Unknown",

                    "os": device.get("operating_system") or "Unknown",

                    "compliance": device.get("compliance_state") or "Unknown"

                }

            )

            success += 1

            print(f"✓ {device.get('device_name')}")

        except Exception as e:

            failed += 1

            print(f"✗ {device.get('device_name')}")
            print(e)

    print(f"Devices Indexed : {success}")
    print(f"Devices Failed  : {failed}")

    return success


# ==========================================
# Users
# ==========================================

def ingest_users(cursor):

    cursor.execute("SELECT * FROM users")

    users = cursor.fetchall()

    print(f"\n[3/3] Ingesting {len(users)} Users...")

    success = 0
    failed = 0

    for user in users:

        try:

            chunk = user_chunk(user)

            embedding = create_embedding(chunk)

            add_document(

                document_id=f"user_{user['id']}",

                document=chunk,

                embedding=embedding,

                metadata={

                    "type": "user",

                    "name": user.get("display_name") or "Unknown",

                    "email": (
                        user.get("mail")
                        or user.get("user_principal_name")
                        or "Unknown"
                    ),

                    "enabled": bool(
                        user.get("account_enabled", False)
                    )

                }

            )

            success += 1

            print(f"✓ {user.get('display_name')}")

        except Exception as e:

            failed += 1

            print(f"✗ {user.get('display_name')}")
            print(e)

    print(f"Users Indexed : {success}")
    print(f"Users Failed  : {failed}")

    return success


# ==========================================
# Build Enterprise Knowledge Base
# ==========================================

def build_vector_database():

    print("\n==========================================")
    print("Enterprise Knowledge Base Build Started")
    print("==========================================\n")

    print("Clearing Existing Chroma Collection...")

    clear_collection()

    print("Collection Cleared.\n")

    conn = get_connection()

    cursor = conn.cursor(dictionary=True)

    try:

        app_count = ingest_applications(cursor)

        device_count = ingest_devices(cursor)

        user_count = ingest_users(cursor)

    finally:

        cursor.close()

        conn.close()

    total = app_count + device_count + user_count

    print("\n==========================================")
    print("Knowledge Base Successfully Built")
    print("==========================================")

    print(f"Applications : {app_count}")
    print(f"Devices      : {device_count}")
    print(f"Users        : {user_count}")
    print("------------------------------------------")
    print(f"Total Chunks : {total}")
    print("==========================================\n")


# ==========================================
# Main
# ==========================================

if __name__ == "__main__":

    build_vector_database()