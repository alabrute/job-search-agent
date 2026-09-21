import json
import os

import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore


def main():
    service_account = json.loads(os.environ["FIREBASE_SERVICE_ACCOUNT"])

    if not firebase_admin._apps:
        cred = credentials.Certificate(service_account)
        firebase_admin.initialize_app(cred)

    db = firestore.client()

    db.collection("system").document("test").set({
        "status": "ok",
        "message": "GitHub Actions is connected to Firebase"
    })

    print("Firebase connection OK")


if __name__ == "__main__":
    main()
