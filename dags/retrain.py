from airflow import DAG
from airflow.operators import PythonOperator
from datetime import datetime
import pymongo
import requests
from random import choice
from string import ascii_letters
from os import getenv
import spacy
from sklearn.neighbors import KNeighborsClassifier
import pickle
from pathlib import Path


DB_URI = getenv("DB_URI")

dag = DAG(
    dag_id="retrain_model", start_date=datetime(2020, 2, 8), schedule_interval=None
)
# specify schedule_interval as a crontab to schedule the job.


def check_mongo_updates():
    """Check mongodb for any updated document
    """
    db_client = pymongo.MongoClient(DB_URI)

    print("Checking for new records in mongodb:")
    cursor = (
        db_client.analytics_db.retrain_data.find()
        .sort([("timestamp", pymongo.DESCENDING)])
        .limit(1)
    )
    last_doc_timestamp = list(cursor)
    cursor = (
        db_client.analytics_db.pipeline_run.find()
        .sort([("timestamp", pymongo.DESCENDING)])
        .limit(1)
    )
    last_run_timestamp = list(cursor)
    if len(last_run_timestamp) == 0:
        # when the pipeline is run for the first time
        last_run_timestamp = 0
    else:
        last_run_timestamp = last_run_timestamp[0]["timestamp"]

    if len(last_doc_timestamp) == 0:
        # when no docs were inserted
        last_doc_timestamp = 0
    else:
        last_doc_timestamp = last_doc_timestamp[0]["timestamp"]

    print("LAST_RUN_TIMESTAMP:", last_run_timestamp)
    print("LAST_DOC_TIMESTAMP:", last_doc_timestamp)

    db_client.close()

    if last_doc_timestamp <= last_run_timestamp:
        raise RuntimeError("NO UPDATES FOUND SINCE LAST RUN ABORTING RETRAIN.")


def retrain_model_with_data():
    """Load models, raw data and retrain a KNN based on existing data to find simiarily
    """
    nlp = spacy.load("en_core_web_sm")
    knn = KNeighborsClassifier()
    input_data = []
    output_data = []

    db_client = pymongo.MongoClient(DB_URI)
    data_cursor = db_client.analytics_db.retrain_data.find()

    print("FETCHING TRAINING DATA: ..")
    count = 0
    for doc in data_cursor:
        count += 1

        print("FETCHED RECORDS: ", count)
        temp = []
        # if blank query then skip it
        if len(doc["raw_query"]) > 0:
            print("COMPUTING WORD EMBEDDINGS...")

            dc = nlp(doc["raw_query"]).vector
            temp.extend(dc)
            temp.append(doc["timestamp"])
            temp.append(doc["bucket_index_in_raw_query"])
            input_data.append(temp)
            output_data.append(doc["bucket_tag"])

    print("DATA FETCHING COMPLETE, PROCEEDING TO RETRAIN")
    print(input_data, output_data)
    knn.fit(input_data, output_data)

    print("RETRAINING COMPLETE.")
    # retrain the model and save file on file system and save path in models
    retrained_pickle_path = "".join(choice(ascii_letters) for i in range(10)) + ".pkl"

    pickle.dump(knn, open(str(Path("/usr/modeldir") / retrained_pickle_path), "wb"))

    db_client.analytics_db.pipeline_run.insert_one(
        {
            "model_path": str(Path(getenv("MODEL_DIR_HOST_PATH", ".")) / retrained_pickle_path),
            "timestamp": int(datetime.now().timestamp()),
        }
    )
    print("MODEL SAVED PROCEEDING TO SYNC BACKEND")
    db_client.close()


def ping_model_sync():
    """Ping model with latest retrained model path
    """
    db_client = pymongo.MongoClient(DB_URI)
    cursor = (
        db_client.analytics_db.pipeline_run.find()
        .sort([("timestamp", pymongo.DESCENDING)])
        .limit(1)
    )
    last_run_model = list(cursor)

    print("RETRIEVING LAST SAVED MODEL STATE")
    if last_run_model:
        latest_model_path = last_run_model[0]["model_path"]
    else:
        retrained_pickle_path = "".join(choice(ascii_letters) for i in range(10)) + ".pkl"
        latest_model_path = str(Path(getenv("MODEL_DIR_HOST_PATH", ".")) / retrained_pickle_path)

    requests.post(
        "http://docker.for.win.localhost:8000/sync-model-updates/",
        json={"model_path": latest_model_path},
    )
    print("BACKEND NUDGED FOR SYNC.")

    db_client.close()


check_for_updates = PythonOperator(
    task_id="check_for_updates", python_callable=check_mongo_updates, dag=dag
)

main_model_retrain_task = PythonOperator(
    task_id="model_retrain_main", python_callable=retrain_model_with_data, dag=dag
)

ping_model_sync_task = PythonOperator(
    task_id="ping_model_sync_to_backend", python_callable=ping_model_sync, dag=dag
)

check_for_updates >> main_model_retrain_task >> ping_model_sync_task
