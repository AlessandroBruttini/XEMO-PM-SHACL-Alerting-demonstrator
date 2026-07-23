# XEMO PM Emission Monitoring Pipeline

A lightweight semantic monitoring pipeline for construction-site PM emissions that combines **InfluxDB**, **RDF**, **GraphDB**, and **SHACL** to enable semantic validation and automatic alert generation.

The repository demonstrates how real-time sensor observations can be transformed into semantic knowledge graphs and validated against ontology-based rules.
This repository contains the scripts and SHACL shapes used for the PM alerting demonstrator based on the [XEMO ontology](https://github.com/AlessandroBruttini/XEMO).

---

## Repository Structure

```
.
├── connector.py                # Semantic connector and validation pipeline
├── ingestor.py                 # Air quality pm emissions simulator
├── shapes/warnings.shacl.ttl    # SHACL warning rules
└── README.md
```

---

## Components

### `ingestor.py`

A configurable simulator that generates realistic PM10 and PM2.5 measurements for multiple construction-site sensors.

Features include:

- Multiple virtual sensors
- Area-specific configurations
- Realistic daily pollution profiles
- Weekend and workday behavior
- Random construction activity spikes
- Configurable sampling interval
- Direct writing into InfluxDB

Generated measurements include:

- PM10
- PM2.5

Each observation is tagged with

- sensor ID
- area ID
- timestamp

---

### `connector.py`

The semantic integration pipeline.

The connector periodically

1. reads sensor observations from InfluxDB,
2. converts measurements into RDF observations using SOSA and QUDT,
3. uploads observations into GraphDB,
4. validates observations using SHACL,
5. stores validation reports, and
6. generates semantic air-quality alerts.

Supported aggregation levels:

- Instant observations
- Hourly mean values
- Daily mean values

The implementation uses:

- RDFLib
- PySHACL
- SPARQLWrapper
- GraphDB
- InfluxDB Client

---

### `warnings.shacl.ttl`

Contains SHACL rules used to evaluate air quality observations.

The rules define warning conditions for PM10 and PM2.5 concentrations and are executed using PySHACL during every validation cycle.

Validation results are stored as RDF and can be further processed to generate semantic alerts.

---

## Semantic Technologies

The implementation builds upon:

- RDF
- SOSA ontology
- QUDT ontology
- SHACL
- SPARQL
- GraphDB

---

## Pipeline Overview

```
InfluxDB
     │
     ▼
connector.py
     │
     ├── RDF generation
     ├── GraphDB upload
     ├── SHACL validation
     ├── Validation report
     └── Alert generation
```

---

## Requirements

Typical Python dependencies include:

```
rdflib
pyshacl
SPARQLWrapper
requests
influxdb-client
```

Install using

```bash
pip install rdflib pyshacl SPARQLWrapper requests influxdb-client
```

---

## XEMO ontology

The demonstrator uses the XEMO ontology to represent construction sites, emission sources, pollutants, sensors, observations, and regulatory thresholds.

The ontology and its documentation are maintained in a separate repository:

- [XEMO ontology repository](https://github.com/AlessandroBruttini/XEMO)

## Configuration

The scripts contain configurable parameters for:

- InfluxDB connection
- GraphDB endpoint
- authentication
- sampling interval
- aggregation interval
- validation graph
- namespaces

Adjust these settings before running the pipeline.

---

## Running the Example

Start the data simulator:

```bash
python ingestor.py
```

Start the semantic connector:

```bash
python connector.py
```

The connector will periodically

- retrieve measurements,
- create RDF observations,
- perform SHACL validation,
- upload validation reports,
- generate semantic alerts.

---

## Citation

If you use this repository in academic work, please cite the associated publication:

---

## License

This repository is licensed under the **Creative Commons Attribution 4.0 International (CC BY 4.0)** license.

You are free to:

- Share
- Adapt
- Redistribute
- Build upon the material

for any purpose, provided appropriate credit is given.

See the LICENSE file for details.
