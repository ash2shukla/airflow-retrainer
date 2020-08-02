import pymongo
from time import sleep
from datetime import datetime
from random import randint


def get_documents(k=10):
    documents = []
    for i in range(k):
        sample_document = {
            "raw_query": f"query_string {i}",
            "timestamp": int(datetime.now().timestamp()),
            "bucket_tag": "commit",
            "bucket_index_in_raw_query": randint(0, 100)
        }
        sleep(0.005)
        documents.append(sample_document)
    return documents
client = pymongo.MongoClient()

documents = get_documents(10)
client.analytics_db.retrain_data.insert_many(documents, ordered=False)