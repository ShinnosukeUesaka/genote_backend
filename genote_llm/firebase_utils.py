from firebase_admin import credentials, firestore, initialize_app, storage
import os

if os.getenv("ENVIRONMENT") == "local":
    print("local")
    cred = credentials.Certificate("genote_llm/firebase_key.json")
    initialize_app(cred)
else:
    print("cloud")
    initialize_app()
db = firestore.client()
bucket = storage.bucket("genote.appspot.com")
