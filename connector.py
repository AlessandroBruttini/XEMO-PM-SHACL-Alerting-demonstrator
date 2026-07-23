#!/usr/bin/env python3
import hashlib
import time
from datetime import datetime, timezone
from typing import List, Dict
from rdflib import Graph, Namespace, RDF, URIRef, Literal
from rdflib.namespace import XSD
import uuid
from pyshacl import validate
from SPARQLWrapper import SPARQLWrapper, TURTLE
import requests
from requests.auth import HTTPBasicAuth

try:
    import influxdb_client
except ImportError:
    influxdb_client = None


# ---------------- CONFIG ----------------

# ---- TIME WINDOW (single source of truth) ----
TIME_WINDOW_SECONDS = 300
TIME_WINDOW_FLUX = f"-{TIME_WINDOW_SECONDS}s"
TIME_WINDOW_SPARQL = f"PT{TIME_WINDOW_SECONDS}S"

# ---- InfluxDB ----
INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "my-influxdb-token"
INFLUX_ORG = "RUB"
INFLUX_BUCKET = "xemo"

# ---- GraphDB ----
GRAPHDB_QUERY_ENDPOINT = "http://localhost:7200/repositories/xemo"
GRAPHDB_STATEMENTS_URL = "http://localhost:7200/repositories/xemo/statements"

GRAPHDB_USER = "influx_user"
GRAPHDB_PASSWORD = "influx_password"

AUTH = HTTPBasicAuth(GRAPHDB_USER, GRAPHDB_PASSWORD)

# ---- SHACL ----
SHACL_FILE = "shapes/warnings.shacl.ttl"
VALIDATION_GRAPH = "https://example.org/xemo/validation/"

# ---------------- NAMESPACES ----------------

SOSA = Namespace("http://www.w3.org/ns/sosa/")
XEMO = Namespace("https://example.org/xemo#")
XEMODATA = Namespace("https://example.org/xemo/demo#")
QUDT = Namespace("http://qudt.org/schema/qudt/")
UNIT = Namespace("http://qudt.org/vocab/unit/")
SH = Namespace("http://www.w3.org/ns/shacl#")

# ---------------- INFLUX QUERY ----------------

def build_flux_query():

    #return f'''
#from(bucket: "{INFLUX_BUCKET}")
  #|> range(start: {TIME_WINDOW_FLUX})
  #|> filter(fn: (r) => r["_measurement"] == "PM10" or r["_measurement"] == "PM2_5")
  #|> filter(fn: (r) => r["_field"] == "MicroGM-PER-M3")
  #|> filter(fn: (r) => r["area_id"] == "Area_Excavation_01" or r["area_id"] == "Area_Excavation_02" or r["area_id"] == "Area_Roadwork_01")
  #|> filter(fn: (r) => r["sensor_id"] == "Sensor_Airnode_01" or r["sensor_id"] == "Sensor_Airnode_02" or r["sensor_id"] == "Sensor_Airnode_03")
  #|> aggregateWindow(every: {TIME_WINDOW_SECONDS}s, fn: mean, createEmpty: false)
  #|> yield(name: "mean")
#'''

    return f'''
raw = from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "PM10" or r["_measurement"] == "PM2_5")
  |> filter(fn: (r) => r["_field"] == "MicroGM-PER-M3")

instant = raw
  |> range(start: {TIME_WINDOW_FLUX})
  |> aggregateWindow(every: {TIME_WINDOW_SECONDS}s, fn: mean)
  |> set(key: "aggregation", value: "instant")

hourly = raw
  |> range(start: -1h)
  |> mean()
  |> set(key: "aggregation", value: "hourly")

daily = raw
  |> range(start: -24h)
  |> mean()
  |> set(key: "aggregation", value: "daily")

union(tables: [instant, hourly, daily])
'''


# ---------------- INFLUX ACCESS ----------------

def query_influx() -> List[Dict]:

    if influxdb_client is None:
        raise RuntimeError("influxdb-client not installed")

    client = influxdb_client.InfluxDBClient(
        url=INFLUX_URL,
        token=INFLUX_TOKEN,
        org=INFLUX_ORG
    )

    query = build_flux_query()

    tables = client.query_api().query(query)

    rows = []

    for table in tables:
        for record in table.records:

            value = record.get_value()

            if value is None:
                continue

            rows.append({
                "time": datetime.now(),
                "value": value,
                "measurement": record.get_measurement(),
                "sensor": record.values["sensor_id"],
                "area": record.values["area_id"],
                "aggregation": record.values.get("aggregation", "instant")
            })
    print(rows)
    return rows


# ---------------- URI GENERATION ----------------

def make_obs_uri(sensor, prop, area, timestamp, aggr):

    key = f"{sensor}|{prop}|{area}|{timestamp}"
    digest = hashlib.sha256(key.encode()).hexdigest()

    return XEMODATA[f"Observation_{aggr}_{digest}"]


def make_result_uri(obs_uri, aggr):

    digest = hashlib.sha256(str(obs_uri).encode()).hexdigest()

    return XEMODATA[f"Result_{aggr}_{digest}"]


# ---------------- OBSERVATION CREATION ----------------

def build_observation_graph(sensor, prop, area, timestamp, value, aggregation):

    g = Graph()

    g.bind("sosa", SOSA)
    g.bind("xemo", XEMO)
    g.bind("demo", XEMODATA)
    g.bind("qudt", QUDT)
    g.bind("unit", UNIT)

    obs_uri = make_obs_uri(sensor, prop, area, timestamp, aggregation)
    result_uri = make_result_uri(obs_uri, aggregation)

    t = timestamp.astimezone(timezone.utc)

    

    # statistical metadata
    if aggregation != "instant":
    
        if aggregation == "hourly":
            g.add((obs_uri, SOSA.hasProcedure, XEMO.HourlyMean))
            g.add((obs_uri, RDF.type, SOSA.Observation))
            g.add((obs_uri, SOSA.madeBySensor, XEMODATA[sensor]))
            g.add((obs_uri, SOSA.observedProperty, XEMO[prop]))
            g.add((obs_uri, SOSA.hasFeatureOfInterest, XEMODATA[area]))
            g.add((obs_uri, SOSA.resultTime, Literal(t, datatype=XSD.dateTime)))
            g.add((obs_uri, SOSA.hasResult, result_uri))
            g.add((result_uri, RDF.type, QUDT.QuantityValue))
            g.add((result_uri, QUDT.numericValue, Literal(value)))
            g.add((result_uri, QUDT.hasUnit, UNIT["MicroGM-PER-M3"]))

        if aggregation == "daily":
            g.add((obs_uri, SOSA.hasProcedure, XEMO.DailyMean))
            g.add((obs_uri, RDF.type, SOSA.Observation))
            g.add((obs_uri, SOSA.madeBySensor, XEMODATA[sensor]))
            g.add((obs_uri, SOSA.observedProperty, XEMO[prop]))
            g.add((obs_uri, SOSA.hasFeatureOfInterest, XEMODATA[area]))
            g.add((obs_uri, SOSA.resultTime, Literal(t, datatype=XSD.dateTime)))
            g.add((obs_uri, SOSA.hasResult, result_uri))
            g.add((result_uri, RDF.type, QUDT.QuantityValue))
            g.add((result_uri, QUDT.numericValue, Literal(value)))
            g.add((result_uri, QUDT.hasUnit, UNIT["MicroGM-PER-M3"]))

    else:
        g.add((obs_uri, SOSA.hasProcedure, XEMO.Instant))
        g.add((obs_uri, RDF.type, SOSA.Observation))
        g.add((obs_uri, SOSA.madeBySensor, XEMODATA[sensor]))
        g.add((obs_uri, SOSA.observedProperty, XEMO[prop]))
        g.add((obs_uri, SOSA.hasFeatureOfInterest, XEMODATA[area]))
        g.add((obs_uri, SOSA.resultTime, Literal(t, datatype=XSD.dateTime)))
        g.add((obs_uri, SOSA.hasResult, result_uri))
        g.add((result_uri, RDF.type, QUDT.QuantityValue))
        g.add((result_uri, QUDT.numericValue, Literal(value)))
        g.add((result_uri, QUDT.hasUnit, UNIT["MicroGM-PER-M3"]))

   
    return g


# ---------------- GRAPHDB UPLOAD ----------------

def upload_graph(graph):

    ttl = graph.serialize(format="turtle")

    headers = {"Content-Type": "text/turtle"}

    r = requests.post(
        GRAPHDB_STATEMENTS_URL,
        data=ttl.encode("utf-8"),
        headers=headers,
        auth=AUTH
    )

    if r.status_code not in (200, 204):
        raise RuntimeError(r.text)


# ---------------- LOAD DATA GRAPH ----------------

def load_data_graph():

    sparql = SPARQLWrapper(GRAPHDB_QUERY_ENDPOINT)

    sparql.setCredentials(GRAPHDB_USER, GRAPHDB_PASSWORD)

    sparql.setQuery(f"""
    PREFIX sosa: <http://www.w3.org/ns/sosa/>
    PREFIX xemo: <https://example.org/xemo#>
    PREFIX qudt: <http://qudt.org/schema/qudt/>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
    
    CONSTRUCT {{ ?s ?p ?o }}
    WHERE {{
       ?s ?p ?o .
    }}
    """)

    sparql.setReturnFormat(TURTLE)

    g = Graph()

    g.parse(data=sparql.query().convert(), format="turtle")
    return g


# ---------------- SHACL VALIDATION ----------------

def run_shacl_validation(data_graph=None):

    print("Running SHACL validation...")

    if data_graph is None:
        data_graph = load_data_graph()
    
    data_graph.parse(
        "https://raw.githubusercontent.com/philhag/XEMO/refs/heads/patch-1/xemo.ttl",
        format="turtle"
    )
    shapes_graph = Graph()
    shapes_graph.parse(SHACL_FILE, format="turtle")

    conforms, results_graph, results_text = validate(
        data_graph,
        shacl_graph=shapes_graph,
        inference="rdfs"
    )

    print("Conforms:", conforms)
    print(results_text)

    return results_graph


# ---------------- VALIDATION REPORT ----------------

def upload_validation_report(results_graph):

    ttl = results_graph.serialize(format="turtle")

    url = f"{GRAPHDB_STATEMENTS_URL}?context=<{VALIDATION_GRAPH}>"

    r = requests.post(
        url,
        data=ttl.encode("utf-8"),
        headers={"Content-Type": "text/turtle"},
        auth=AUTH
    )

    if r.status_code not in (200, 204):
        raise RuntimeError(r.text)


# ---------------- ALERT GENERATION ----------------

def generate_alerts(results_graph):

    alerts = Graph()

    for result in results_graph.subjects(RDF.type, SH.ValidationResult):

        focus = results_graph.value(result, SH.focusNode)

        alert_uri = XEMODATA[f"AirQualityAlert_{uuid.uuid4()}"]

        alerts.add((alert_uri, RDF.type, XEMO.AirQualityAlert))
        alerts.add((alert_uri, XEMO.triggeredByObservation, focus))

    return alerts


def upload_alerts(alert_graph):

    ttl = alert_graph.serialize(format="turtle")

    url = f"{GRAPHDB_STATEMENTS_URL}?context=<https://example.org/xemo/alerts>"

    r = requests.post(
        url,
        data=ttl.encode("utf-8"),
        headers={"Content-Type": "text/turtle"},
        auth=AUTH
    )

    if r.status_code not in (200, 204):
        raise RuntimeError(r.text)


# ---------------- PIPELINE ----------------

def pipeline():

    rows = query_influx()

    if not rows:
        print("No data returned")
        return

    print(f"{len(rows)} records received")

    batch_graph = Graph()

    for r in rows:
        batch_graph += build_observation_graph(
            r["sensor"],
            r["measurement"],
            r["area"],
            r["time"],
            r["value"],
            r["aggregation"]
        )

    upload_graph(batch_graph)

    results_graph = run_shacl_validation(batch_graph)

    upload_validation_report(results_graph)

    alerts = generate_alerts(results_graph)

    upload_alerts(alerts)


# ---------------- SCHEDULER ----------------

def main():

    print("Connector started")
    print(f"Execution interval: {TIME_WINDOW_SECONDS} seconds")

    while True:

        start = time.time()

        try:
            pipeline()

        except Exception as e:
            print("Pipeline error:", e)

        duration = time.time() - start

        sleep_time = max(0, TIME_WINDOW_SECONDS - duration)

        print(f"Sleeping {sleep_time:.1f}s")

        time.sleep(sleep_time)


if __name__ == "__main__":
    main()