FROM puckel/docker-airflow:1.10.9

RUN pip install pymongo
RUN pip install spacy
RUN pip install scikit-learn==0.23.1
RUN python -m spacy download en_core_web_sm