from flask import Flask, request
import pickle

app = Flask(__name__)


@app.route("/sync-model-updates/", methods=["POST"])
def method():
    print("SYNCING MODEL..")
    print("NEW MODEL PATH", request.json["model_path"])
    model = pickle.load(open(request.json["model_path"], "rb"))
    print(model)
    print("MODEL SYNC COMPLETE!")
    return ''

app.run(port=8000)