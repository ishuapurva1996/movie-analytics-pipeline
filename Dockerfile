FROM apache/airflow:3.3.2

COPY --chown=airflow:root airflow/requirements.txt /requirements.txt

RUN pip install --no-cache-dir \
    "apache-airflow==${AIRFLOW_VERSION}" \
    -r /requirements.txt

USER root

RUN python3 -m venv /opt/dbt_venv \
    && /opt/dbt_venv/bin/pip install --no-cache-dir "dbt-snowflake==1.12.0" \
    && chown -R airflow:root /opt/dbt_venv

USER airflow
